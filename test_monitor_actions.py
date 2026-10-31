"""Exercise motion dispatch through the app without opening a camera or GUI."""
import unittest
from unittest.mock import Mock

from actions import Action, ActionSequence, RepeatGate
from app import Monitor
from test_actions import FakePlayer


class MonitorActionTests(unittest.TestCase):
    def setUp(self):
        self.monitor = Monitor.__new__(Monitor)
        self.monitor.armed = Mock()
        self.monitor.armed.get.return_value = True
        self.monitor.preparing = False
        self.monitor.generation = 1
        self.monitor.count = 0
        self.monitor.status = Mock()
        self.monitor.action_status = Mock()
        self.monitor.append_log = Mock()
        self.monitor.wake_monitors = Mock()
        self.monitor.wake_monitors.get.return_value = True
        self.monitor.display_wake = Mock()
        self.monitor.display_wake.request.return_value = False
        self.video = Action('video', 'a.mp4')
        self.image = Action('image', 'a.png', keep_open=True)
        self.monitor.session_actions = (self.video, self.image)
        self.monitor.gate = RepeatGate('interval', 5)
        self.launched = []
        def launch(action):
            player = FakePlayer()
            self.launched.append((action, player))
            return player
        self.monitor.sequence = ActionSequence(launch, self.monitor.append_log)

    def sample(self, now, moving=True):
        self.monitor.handle_motion(('motion', 1, now, moving, moving, moving, False, 'Prueba', '12:00:00'))
        self.monitor.sequence.tick(now)

    def finish_video(self):
        self.launched[0][1].code = 0
        self.monitor.sequence.tick(1)

    def test_interval_repeats_video_while_the_same_image_stays_open(self):
        self.sample(0)
        self.finish_video()
        self.sample(4)
        self.assertEqual(len(self.launched), 2)
        self.sample(5)
        self.assertEqual([a for a, _ in self.launched], [self.video, self.image, self.video])
        self.assertFalse(self.launched[1][1].stopped)
        self.monitor.update_action_status()
        self.assertIn('1 abiertas', self.monitor.action_status.set.call_args.args[0])

    def test_episode_rearms_without_waiting_for_persistent_image_to_close(self):
        self.monitor.gate = RepeatGate('episode', 5)
        self.sample(0)
        self.finish_video()
        self.sample(1, moving=False)
        self.sample(6, moving=False)
        self.sample(6.5)
        self.assertEqual([a for a, _ in self.launched], [self.video, self.image, self.video])

    def test_once_still_does_not_repeat_even_if_image_is_closed(self):
        self.monitor.gate = RepeatGate('once')
        self.sample(0)
        self.finish_video()
        self.sample(10)
        self.launched[1][1].code = 0
        self.monitor.sequence.tick(11)
        self.sample(20)
        self.assertEqual(len(self.launched), 2)

    def test_only_persistent_actions_do_not_generate_empty_activations(self):
        self.monitor.session_actions = (self.image,)
        self.sample(0)
        self.sample(5)
        self.sample(10)
        self.assertEqual(len(self.launched), 1)
        self.assertEqual(self.monitor.gate.last_activation, 0)
        self.monitor.update_action_status()
        self.assertIn('no se duplican', self.monitor.action_status.set.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
