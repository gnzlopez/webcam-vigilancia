import unittest
from actions import Action, ActionSequence, RepeatGate


class RepeatTests(unittest.TestCase):
    def test_once_requires_a_new_gate_to_rearm(self):
        gate = RepeatGate('once')
        self.assertTrue(gate.update(0, True, True))
        gate.update(1, False, False)
        self.assertFalse(gate.update(100, True, True))
        self.assertTrue(RepeatGate('once').update(100, True, True))

    def test_episode_waits_for_a_complete_quiet_period(self):
        gate = RepeatGate('episode', 10)
        self.assertTrue(gate.update(0, True, True))
        self.assertFalse(gate.update(30, True, True))
        gate.update(31, False, False)
        self.assertFalse(gate.update(40, True, True))
        gate.update(41, False, False)
        self.assertTrue(gate.update(51, True, True))

    def test_interval_can_repeat_during_continuous_motion(self):
        gate = RepeatGate('interval', 60)
        self.assertTrue(gate.update(10, True, True))
        self.assertFalse(gate.update(69, True, True))
        self.assertTrue(gate.update(70, True, True))
        self.assertFalse(gate.update(140, False, False))

    def test_unconfirmed_motion_never_triggers(self):
        for mode in ('once', 'episode', 'interval'):
            self.assertFalse(RepeatGate(mode).update(0, True, False))

    def test_motion_during_playback_does_not_queue_an_episode(self):
        gate = RepeatGate('episode', 10)
        self.assertTrue(gate.update(0, True, True))
        gate.update(1, False, False, busy=True)
        self.assertFalse(gate.update(12, True, True, busy=True))
        self.assertFalse(gate.update(13, True, True))
        gate.update(14, False, False)
        self.assertTrue(gate.update(24, True, True))

    def test_interval_does_not_overlap_a_running_list(self):
        gate = RepeatGate('interval', 2)
        gate.update(0, True, True)
        self.assertFalse(gate.update(10, True, True, busy=True))
        self.assertTrue(gate.update(11, True, True))

    def test_invalid_numbers_are_rejected(self):
        for seconds in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                RepeatGate(seconds=seconds)
        for delay in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                Action('audio', 'test.wav', delay)


class FakePlayer:
    def __init__(self):
        self.code = None
        self.error = ''
        self.stopped = False

    def poll(self):
        return self.code

    def stop(self):
        self.stopped = True
        self.code = 0


class PlaybackOptionsTests(unittest.TestCase):
    def test_monitor_and_fullscreen_are_per_action(self):
        primary = Action('audio', 'file')
        secondary = Action('video', 'file', monitor=r'\\.\DISPLAY3', fullscreen=True)
        self.assertEqual(primary.monitor, 'primary')
        self.assertFalse(primary.fullscreen)
        self.assertIn('Monitor 3', secondary.destination)
        self.assertIn('Completa', secondary.destination)
        self.assertEqual(secondary.monitor, r'\\.\DISPLAY3')

    def test_invalid_monitor_options_are_rejected(self):
        for device in ('', '\n', None):
            with self.assertRaises(ValueError):
                Action('video', 'file', monitor=device)
        with self.assertRaises(ValueError):
            Action('image', 'file', fullscreen='true')

    def test_loop_and_persistent_image_are_distinct(self):
        for kind in ('audio', 'video'):
            action = Action(kind, 'file', loop=True)
            self.assertTrue(action.indefinite)
            self.assertEqual(action.playback, 'En bucle')
        action = Action('image', 'file', keep_open=True)
        self.assertTrue(action.indefinite)
        self.assertEqual(action.playback, 'Sin cierre automático')

    def test_invalid_options_are_rejected(self):
        with self.assertRaises(ValueError):
            Action('image', 'file', loop=True)
        for kind in ('audio', 'video'):
            with self.assertRaises(ValueError):
                Action(kind, 'file', keep_open=True)


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.launched = []
        self.reports = []
        def launch(action):
            handle = FakePlayer()
            self.launched.append((action, handle))
            return handle
        self.sequence = ActionSequence(launch, self.reports.append)

    def test_delays_share_the_same_detection_time(self):
        audio = Action('audio', 'a.wav', 0)
        image = Action('image', 'a.png', 5)
        self.sequence.start([image, audio], 100)
        self.sequence.tick(100)
        self.assertEqual([a for a, _ in self.launched], [audio])
        self.sequence.tick(104.9)
        self.assertEqual(len(self.launched), 1)
        self.sequence.tick(105)
        self.assertEqual([a for a, _ in self.launched], [audio, image])

    def test_pending_or_playing_list_cannot_be_started_again(self):
        actions = [Action('audio', 'a.wav', 5)]
        self.assertTrue(self.sequence.start(actions, 0))
        self.assertFalse(self.sequence.start(actions, 1))
        self.sequence.tick(5)
        self.assertFalse(self.sequence.start(actions, 6))
        self.launched[0][1].code = 0
        self.sequence.tick(7)
        self.assertTrue(self.sequence.start(actions, 7))

    def test_stop_cancels_delayed_actions_and_closes_owned_players(self):
        self.sequence.start([Action('audio', 'a.wav'), Action('video', 'a.mp4', 10)], 0)
        self.sequence.tick(0)
        self.sequence.stop()
        self.sequence.tick(100)
        self.assertEqual(len(self.launched), 1)
        self.assertTrue(self.launched[0][1].stopped)
        self.assertFalse(self.sequence.busy)

    def test_failed_file_does_not_block_other_actions(self):
        def failing(action):
            raise FileNotFoundError('archivo eliminado')
        self.sequence.launch = failing
        self.sequence.start([Action('audio', 'missing.wav')], 0)
        self.sequence.tick(0)
        self.assertFalse(self.sequence.busy)
        self.assertIn('archivo eliminado', self.reports[-1])

    def test_permanent_actions_stay_open_without_duplicating(self):
        loop = Action('audio', 'a.wav', loop=True)
        image = Action('image', 'a.png', delay=5, keep_open=True)
        self.sequence.start([loop, image], 0)
        self.sequence.tick(0)
        self.sequence.tick(5)
        self.assertEqual([a for a, _ in self.launched], [loop, image])
        self.sequence.tick(10000)
        self.assertTrue(self.sequence.busy)
        self.assertFalse(self.sequence.repeat_blocked)
        self.assertFalse(self.sequence.start([loop, image], 10000))
        self.sequence.stop()
        self.assertTrue(all(player.stopped for _, player in self.launched))
        self.assertFalse(self.sequence.busy)

    def test_video_repeats_without_reopening_persistent_image(self):
        video = Action('video', 'a.mp4')
        image = Action('image', 'a.png', keep_open=True)
        actions = [video, image]
        self.sequence.start(actions, 0)
        self.sequence.tick(0)
        image_handle = self.launched[1][1]
        self.launched[0][1].code = 0
        self.sequence.tick(1)
        self.assertTrue(self.sequence.can_start(actions))
        self.sequence.start(actions, 10)
        self.sequence.tick(10)
        self.assertEqual([a for a, _ in self.launched], [video, image, video])
        self.assertFalse(image_handle.stopped)
        self.assertTrue(self.sequence.repeat_blocked)
        self.sequence.stop()
        self.assertTrue(image_handle.stopped)
        self.assertTrue(self.launched[-1][1].stopped)

    def test_audio_loop_does_not_block_video_repetition(self):
        loop = Action('audio', 'a.wav', loop=True)
        video = Action('video', 'a.mp4')
        actions = [loop, video]
        self.sequence.start(actions, 0)
        self.sequence.tick(0)
        self.launched[1][1].code = 0
        self.sequence.tick(1)
        self.assertTrue(self.sequence.start(actions, 10))
        self.sequence.tick(10)
        self.assertEqual([a for a, _ in self.launched], [loop, video, video])

    def test_delayed_permanent_action_preserves_its_original_deadline(self):
        video = Action('video', 'a.mp4')
        image = Action('image', 'a.png', delay=30, keep_open=True)
        actions = [video, image]
        self.sequence.start(actions, 0)
        self.sequence.tick(0)
        self.launched[-1][1].code = 0
        self.sequence.tick(1)
        self.assertFalse(self.sequence.repeat_blocked)
        self.sequence.start(actions, 10)
        self.sequence.tick(10)
        self.assertEqual(self.sequence.pending, [(30, 1, image)])
        self.launched[-1][1].code = 0
        self.sequence.tick(11)
        self.sequence.start(actions, 20)
        self.sequence.tick(20)
        self.assertEqual(self.sequence.pending, [(30, 1, image)])
        self.sequence.tick(30)
        self.assertEqual([a for a, _ in self.launched], [video, video, video, image])

    def test_identical_configured_rows_are_independent(self):
        image = Action('image', 'a.png', keep_open=True)
        self.sequence.start([image, image], 0)
        self.sequence.tick(0)
        self.assertEqual(len(self.launched), 2)
        self.assertFalse(self.sequence.start([image, image], 10))
        self.launched[0][1].code = 0
        self.sequence.tick(11)
        self.assertTrue(self.sequence.start([image, image], 20))
        self.sequence.tick(20)
        self.assertEqual(len(self.launched), 3)
        self.assertFalse(self.launched[1][1].stopped)

    def test_stop_clears_permanent_rows_so_a_new_session_can_start(self):
        actions = [Action('audio', 'a.wav', loop=True), Action('image', 'a.png', delay=10, keep_open=True)]
        self.sequence.start(actions, 0)
        self.sequence.tick(0)
        self.sequence.stop()
        self.assertTrue(self.sequence.can_start(actions))
        self.sequence.start(actions, 20)
        self.sequence.tick(20)
        self.assertEqual(self.sequence.pending, [(30, 1, actions[1])])
        self.assertEqual(len(self.launched), 2)


if __name__ == '__main__':
    unittest.main()
