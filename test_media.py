import unittest
from unittest.mock import Mock
from media import MediaHandle


class MediaHandleTests(unittest.TestCase):
    def test_stop_after_manual_close_does_not_read_closed_pipes(self):
        process = Mock()
        process.poll.return_value = 0
        process.communicate.return_value = (None, b'')
        handle = MediaHandle(process)
        self.assertEqual(handle.poll(), 0)
        handle.stop()
        process.communicate.assert_called_once()
        process.terminate.assert_not_called()

    def test_stop_is_idempotent(self):
        process = Mock()
        process.poll.return_value = None
        handle = MediaHandle(process)
        handle.stop()
        handle.stop()
        process.terminate.assert_called_once()
        process.communicate.assert_called_once()


if __name__ == '__main__':
    unittest.main()
