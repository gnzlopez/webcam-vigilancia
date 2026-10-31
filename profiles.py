"""Versioned JSON profiles with atomic saves and recovery of the last good copy."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from actions import Action, REPEAT_NAMES


class ProfileError(ValueError):
    pass


def profile_path():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share'))
    return base / 'VigilanciaWebcam' / 'profiles.json'


def default_settings():
    return {
        'camera': 0, 'sensitivity': 50, 'prevent_sleep': True, 'wake_monitors': True,
        'repeat_mode': 'episode', 'quiet_seconds': 10, 'interval_seconds': 60,
        'recording_enabled': False, 'recording_folder': str(Path.home() / 'Videos' / 'VigilanciaWebcam'),
        'recording_quiet_seconds': 5, 'recording_audio': True, 'microphone': None, 'actions': [],
    }


def valid_name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80 or any(ord(c) < 32 for c in value):
        raise ProfileError('El nombre del perfil debe tener entre 1 y 80 caracteres, sin saltos de línea.')
    return value.strip()


def validate_settings(raw):
    if not isinstance(raw, dict):
        raise ProfileError('La configuración del perfil no es válida.')
    settings = default_settings()
    settings.update({key: deepcopy(value) for key, value in raw.items() if key in settings})
    for key, low, high, label in (
        ('camera', 0, 20, 'índice de cámara'), ('sensitivity', 1, 100, 'sensibilidad'),
        ('quiet_seconds', 1, 86400, 'tiempo sin movimiento para repetir'),
        ('interval_seconds', 1, 86400, 'intervalo de repetición'),
        ('recording_quiet_seconds', 1, 60, 'tiempo sin movimiento para grabar'),
    ):
        value = settings[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ProfileError(f'Revisá el {label}: debe estar entre {low} y {high}.')
    if type(settings['camera']) is not int:
        raise ProfileError('El índice de cámara debe ser un número entero.')
    for key in ('prevent_sleep', 'wake_monitors', 'recording_enabled', 'recording_audio'):
        if type(settings[key]) is not bool:
            raise ProfileError('Una de las opciones del perfil no es válida.')
    if settings['repeat_mode'] not in REPEAT_NAMES:
        raise ProfileError('El modo de repetición del perfil no es válido.')
    if not isinstance(settings['recording_folder'], str) or not settings['recording_folder'].strip():
        raise ProfileError('Ingresá una carpeta de grabación.')
    microphone = settings['microphone']
    if microphone is not None and (not isinstance(microphone, dict) or
            any(not isinstance(microphone.get(key), str) or not microphone[key].strip()
                for key in ('name', 'host_api'))):
        raise ProfileError('El micrófono guardado en el perfil no es válido.')
    actions = settings['actions']
    if not isinstance(actions, list) or len(actions) > 1000:
        raise ProfileError('La lista de acciones no es válida.')
    for raw_action in actions:
        try:
            if not isinstance(raw_action, dict):
                raise ValueError()
            Action(**raw_action)
        except (ValueError, TypeError) as exc:
            raise ProfileError(f'Una acción del perfil no es válida: {exc}') from exc
    return settings


def decode_profiles(data):
    try:
        document = json.loads(data)
        if not isinstance(document, dict) or type(document.get('version')) is not int or document['version'] != 1:
            raise ProfileError('La versión del archivo de perfiles no es compatible.')
        raw_profiles = document['profiles']
        if not isinstance(raw_profiles, dict) or not 1 <= len(raw_profiles) <= 1000:
            raise ProfileError('La lista de perfiles no es válida.')
        profiles = {}
        for name, settings in raw_profiles.items():
            if valid_name(name) != name or name.casefold() in {key.casefold() for key in profiles}:
                raise ProfileError('Hay nombres de perfil duplicados o inválidos.')
            profiles[name] = validate_settings(settings)
        if document['active'] not in profiles:
            raise ProfileError('No se encontró el último perfil utilizado.')
        return {'version': 1, 'active': document['active'], 'profiles': profiles}
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProfileError('El archivo de perfiles está incompleto o dañado.') from exc


def fingerprint(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class ProfileStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else profile_path()
        self.backup = self.path.with_suffix('.json.bak')
        self.warning = ''
        self.read_only = False
        self.corrupt = False
        self.document = {'version': 1, 'active': 'Predeterminado', 'profiles': {'Predeterminado': default_settings()}}
        try:
            raw = self.path.read_bytes() if self.path.exists() else None
        except OSError as exc:
            self.read_only = True
            self.warning = f'No se pudieron leer los perfiles: {exc}'
            raw = None
        self.revision = fingerprint(raw)
        if raw is not None:
            try:
                # Never replace a file written by an incompatible newer application.
                header = json.loads(raw)
                if isinstance(header, dict) and type(header.get('version')) is int and header['version'] != 1:
                    self.read_only = True
                    self.warning = 'El archivo de perfiles pertenece a una versión incompatible; no se sobrescribirá.'
                    return
                self.document = decode_profiles(raw)
            except (ProfileError, ValueError, UnicodeDecodeError):
                self.corrupt = True
                try:
                    self.document = decode_profiles(self.backup.read_bytes())
                    self.warning = 'Se recuperó la copia anterior de los perfiles. Revisá los ajustes antes de guardar.'
                except (OSError, ProfileError):
                    self.warning = 'No se pudieron recuperar los perfiles. Se cargaron los valores iniciales; el archivo dañado se conservará al guardar.'

    @property
    def active(self):
        return self.document['active']

    @property
    def names(self):
        return sorted(self.document['profiles'], key=str.casefold)

    def settings(self, name=None):
        return deepcopy(self.document['profiles'][name or self.active])

    def _commit(self, document):
        if self.read_only:
            raise ProfileError(self.warning)
        checked = decode_profiles(json.dumps(document, ensure_ascii=False, allow_nan=False))
        current = self.path.read_bytes() if self.path.exists() else None
        if fingerprint(current) != self.revision:
            raise ProfileError('Otra ventana modificó los perfiles. Para evitar perder esos cambios, cerrá esta ventana sin guardar y volvé a abrir la aplicación.')
        if current is not None:
            if self.corrupt:
                stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
                atomic_write(self.path.with_name(f'profiles-danado-{stamp}.json'), current)
            else:
                atomic_write(self.backup, current)
        payload = json.dumps(checked, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
        atomic_write(self.path, payload)
        self.document = checked
        self.revision = fingerprint(payload)
        self.corrupt = False
        self.warning = ''

    def save(self, settings):
        document = deepcopy(self.document)
        document['profiles'][self.active] = validate_settings(settings)
        self._commit(document)

    def switch(self, name, current):
        if name not in self.document['profiles']:
            raise ProfileError('El perfil seleccionado ya no existe.')
        document = deepcopy(self.document)
        document['profiles'][self.active] = validate_settings(current)
        document['active'] = name
        self._commit(document)

    def create(self, name, current, duplicate=False):
        name = valid_name(name)
        if name.casefold() in {key.casefold() for key in self.names}:
            raise ProfileError('Ya existe un perfil con ese nombre.')
        document = deepcopy(self.document)
        current = validate_settings(current)
        document['profiles'][self.active] = current
        document['profiles'][name] = deepcopy(current) if duplicate else default_settings()
        document['active'] = name
        self._commit(document)

    def rename(self, name, current):
        name = valid_name(name)
        if name.casefold() in {key.casefold() for key in self.names if key != self.active}:
            raise ProfileError('Ya existe un perfil con ese nombre.')
        document = deepcopy(self.document)
        document['profiles'][self.active] = validate_settings(current)
        document['profiles'] = {name if key == self.active else key: value
                                for key, value in document['profiles'].items()}
        document['active'] = name
        self._commit(document)

    def delete(self):
        if len(self.names) == 1:
            raise ProfileError('Debe quedar al menos un perfil. Creá otro antes de eliminar este.')
        document = deepcopy(self.document)
        del document['profiles'][self.active]
        document['active'] = sorted(document['profiles'], key=str.casefold)[0]
        self._commit(document)
