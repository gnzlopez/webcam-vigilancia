import unittest
from unittest.mock import Mock, patch

from app import Monitor
from display_power import DisplayWake, wake_displays
import test_monitor_actions as monitor_tests


class DisplayPowerTests(unittest.TestCase):
    def test_wake_uses_display_idle_reset_and_async_power_on(self):
        kernel, user = Mock(), Mock()
        kernel.SetThreadExecutionState.return_value = 0x80000000
        user.SendNotifyMessageW.return_value = 1
        with patch('display_power.ctypes.WinDLL', side_effect=[kernel, user]), patch('display_power.os.name', 'nt'):
            wake_displays()
        kernel.SetThreadExecutionState.assert_called_once_with(3)
        user.SendNotifyMessageW.assert_called_once_with(0xFFFF, 0x0112, 0xF170, -1)

    def test_requests_are_throttled_and_new_session_resets_them(self):
        wake = Mock()
        control = DisplayWake(wake)
        self.assertTrue(control.request(0))
        self.assertFalse(control.request(.1))
        self.assertFalse(control.request(4.9))
        self.assertTrue(control.request(5))
        control.reset()
        self.assertTrue(control.request(5.1))
        self.assertEqual(wake.call_count, 3)


class MotionWakeTests(unittest.TestCase):
    def setUp(self):
        fixture = monitor_tests.MonitorActionTests()
        fixture.setUp()
        self.monitor = fixture.monitor

    def motion(self, generation=1, confirmed=True, calibrating=False):
        self.monitor.handle_motion(('motion', generation, 0, confirmed, confirmed, False,
                                    calibrating, 'Prueba', '12:00:00'))

    def test_confirmed_motion_wakes_even_without_configured_actions(self):
        self.monitor.session_actions = ()
        self.motion()
        self.monitor.display_wake.request.assert_called_once()

    def test_calibration_unconfirmed_and_old_session_events_do_not_wake(self):
        self.motion(confirmed=False)
        self.monitor.preparing = True
        self.motion(calibrating=True)
        self.motion(generation=0)
        self.monitor.display_wake.request.assert_not_called()

    def test_disabled_option_does_not_wake(self):
        self.monitor.wake_monitors.get.return_value = False
        self.motion()
        self.monitor.display_wake.request.assert_not_called()

    def test_actions_request_wake_before_their_actual_launch(self):
        order = []
        self.monitor.display_wake.request.side_effect = lambda _: order.append('wake')
        with patch('app.launch_media', side_effect=lambda action: order.append('play')):
            self.monitor.launch_action(Mock())
        self.assertEqual(order, ['wake', 'play'])

    def test_wake_failure_does_not_prevent_playback(self):
        self.monitor.display_wake.request.side_effect = RuntimeError('Prueba de error')
        with patch('app.launch_media') as launch:
            self.monitor.launch_action(Mock())
            launch.assert_called_once()
        self.assertIn('No se pudieron encender', self.monitor.append_log.call_args.args[0])
