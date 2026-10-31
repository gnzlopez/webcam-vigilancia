"""Wake Windows displays without mouse injection or permanent power-plan changes."""
import ctypes
import os


def wake_displays():
    if os.name != 'nt':
        raise RuntimeError('El encendido de monitores requiere Windows.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel.SetThreadExecutionState.argtypes = [ctypes.c_uint]
    kernel.SetThreadExecutionState.restype = ctypes.c_uint
    user.SendNotifyMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    user.SendNotifyMessageW.restype = ctypes.c_int
    # A one-shot request resets the idle timers; ES_CONTINUOUS is intentionally absent.
    awake = kernel.SetThreadExecutionState(0x00000003)  # DISPLAY_REQUIRED | SYSTEM_REQUIRED
    # Async delivery avoids waiting on unrelated applications with hung windows.
    notified = user.SendNotifyMessageW(0xFFFF, 0x0112, 0xF170, -1)
    if not awake or not notified:
        raise RuntimeError(f'Windows no pudo completar la solicitud de encendido (error {ctypes.get_last_error()}).')


class DisplayWake:
    def __init__(self, wake=wake_displays):
        self.wake = wake
        self.reset()

    def reset(self):
        self.last_request = float('-inf')

    def request(self, now):
        if now - self.last_request < 5:
            return False
        self.last_request = now
        self.wake()
        return True
