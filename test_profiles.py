from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from actions import Action
from profiles import ProfileError, ProfileStore, default_settings


class ProfileStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config' / 'profiles.json'
        self.store = ProfileStore(self.path)

    def customized(self):
        value = default_settings()
        value.update(camera=2, sensitivity=78, prevent_sleep=False, wake_monitors=False,
                     repeat_mode='interval', quiet_seconds=14, interval_seconds=120,
                     recording_enabled=True, recording_audio=True, recording_quiet_seconds=8,
                     recording_folder=str(Path(self.temp.name) / 'clips'),
                     microphone={'name': 'Micrófono USB', 'host_api': 'Windows WASAPI'},
                     actions=[asdict(Action('video', 'archivo desconectado.mp4', delay=3, loop=True,
                                            monitor=r'\\.\DISPLAY3', fullscreen=True)),
                              asdict(Action('image', 'imagen.png', keep_open=True))])
        return value

    def test_round_trip_preserves_all_settings_without_opening_devices_or_media(self):
        settings = self.customized()
        self.store.save(settings)
        loaded = ProfileStore(self.path)
        self.assertEqual(loaded.settings(), settings)
        self.assertEqual(loaded.active, 'Predeterminado')
        self.assertFalse(Path(settings['recording_folder']).exists())

    def test_new_profile_saves_current_and_starts_with_defaults(self):
        self.store.create('Noche', self.customized())
        self.assertEqual(self.store.settings(), default_settings())
        loaded = ProfileStore(self.path)
        self.assertEqual(loaded.active, 'Noche')
        self.assertEqual(loaded.settings('Predeterminado'), self.customized())

    def test_duplicate_and_profile_edits_are_independent(self):
        settings = self.customized()
        self.store.create('Copia', settings, duplicate=True)
        edited = self.store.settings()
        edited['actions'][0]['path'] = 'otro.mp4'
        self.store.save(edited)
        self.assertEqual(self.store.settings('Predeterminado'), settings)
        self.assertEqual(self.store.settings('Copia'), edited)

    def test_switch_saves_outgoing_settings_and_last_selection(self):
        self.store.create('Noche', self.customized())
        outgoing = default_settings()
        outgoing['sensitivity'] = 20
        self.store.switch('Predeterminado', outgoing)
        loaded = ProfileStore(self.path)
        self.assertEqual(loaded.active, 'Predeterminado')
        self.assertEqual(loaded.settings('Noche'), outgoing)
        self.assertEqual(loaded.settings(), self.customized())

    def test_rename_preserves_edits_and_delete_keeps_other_profiles(self):
        self.store.create('Noche', default_settings())
        self.store.rename('Oficina', self.customized())
        self.assertEqual(self.store.settings('Oficina'), self.customized())
        self.assertNotIn('Noche', self.store.names)
        self.store.delete()
        self.assertEqual(self.store.names, ['Predeterminado'])
        with self.assertRaises(ProfileError):
            self.store.delete()

    def test_duplicate_names_and_invalid_values_do_not_change_disk(self):
        self.store.save(default_settings())
        original = self.path.read_bytes()
        for name in ('', ' ', 'Predeterminado', 'predeterminado', 'a' * 81, 'a\nb'):
            with self.assertRaises(ProfileError):
                self.store.create(name, default_settings())
        for key, value in [('camera', True), ('sensitivity', float('nan')),
                           ('recording_quiet_seconds', 0), ('prevent_sleep', 'false')]:
            settings = default_settings()
            settings[key] = value
            with self.assertRaises(ProfileError):
                self.store.save(settings)
        self.assertEqual(self.path.read_bytes(), original)

    def test_failed_replace_keeps_original_and_memory_and_removes_temp_file(self):
        self.store.save(default_settings())
        original = self.path.read_bytes()
        import os
        replace = os.replace

        def fail_main(source, destination):
            if Path(destination) == self.path:
                raise OSError('Disco de prueba no disponible')
            return replace(source, destination)

        with patch('profiles.os.replace', side_effect=fail_main):
            with self.assertRaises(OSError):
                self.store.save(self.customized())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.store.settings(), default_settings())
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_corrupt_file_recovers_backup_and_retains_damaged_copy(self):
        self.store.save(self.customized())
        self.store.create('Noche', self.customized())
        self.path.write_bytes(b'broken json')
        recovered = ProfileStore(self.path)
        self.assertIn('recuperó', recovered.warning)
        self.assertEqual(recovered.settings(), self.customized())
        recovered.save(recovered.settings())
        backups = list(self.path.parent.glob('profiles-danado-*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'broken json')
        self.assertEqual(ProfileStore(self.path).settings(), self.customized())

    def test_corrupt_without_backup_preserves_original_when_creating_new_profiles(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'broken json')
        recovered = ProfileStore(self.path)
        self.assertTrue(recovered.warning)
        recovered.save(default_settings())
        self.assertEqual(len(list(self.path.parent.glob('profiles-danado-*.json'))), 1)

    def test_future_version_is_never_overwritten(self):
        self.path.parent.mkdir(parents=True)
        original = b'{"version": 99, "future_data": "retain"}'
        self.path.write_bytes(original)
        future = ProfileStore(self.path)
        self.assertTrue(future.read_only)
        with self.assertRaises(ProfileError):
            future.save(default_settings())
        self.assertEqual(self.path.read_bytes(), original)

    def test_incomplete_json_header_recovers_the_valid_backup(self):
        self.store.save(self.customized())
        self.store.save(default_settings())
        self.path.write_bytes(b'{}')
        recovered = ProfileStore(self.path)
        self.assertFalse(recovered.read_only)
        self.assertEqual(recovered.settings(), self.customized())

    def test_stale_window_does_not_overwrite_newer_saved_profiles(self):
        self.store.save(default_settings())
        stale = ProfileStore(self.path)
        self.store.create('Noche', self.customized())
        original = self.path.read_bytes()
        with self.assertRaisesRegex(ProfileError, 'Otra ventana'):
            stale.save(default_settings())
        self.assertEqual(self.path.read_bytes(), original)

    def test_json_does_not_persist_runtime_surveillance_state(self):
        settings = self.customized()
        settings['armed'] = True
        self.store.save(settings)
        self.assertNotIn('armed', json.loads(self.path.read_text(encoding='utf-8'))['profiles']['Predeterminado'])
        self.assertEqual(self.store.settings(), self.customized())

    def test_settings_snapshot_cannot_mutate_the_store(self):
        self.store.save(self.customized())
        changed = self.store.settings()
        changed['actions'].clear()
        self.assertEqual(len(self.store.settings()['actions']), 2)


if __name__ == '__main__':
    unittest.main()
