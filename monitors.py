"""Enumerate Windows monitors without changing the application's DPI mode."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os


def monitor_name(device):
    if device == 'primary':
        return 'Principal (automático)'
    prefix = '\\\\.\\DISPLAY'
    return f'Monitor {device[len(prefix):]}' if device.startswith(prefix) else device


@dataclass(frozen=True)
class Display:
    device: str
    bounds: tuple
    work_area: tuple
    primary: bool

    @property
    def label(self):
        left, top, right, bottom = self.bounds
        primary = ' · Principal' if self.primary else ''
        return f'{monitor_name(self.device)} · {right-left} × {bottom-top}{primary}'


def list_monitors():
    if os.name != 'nt':
        return []
    user32 = ctypes.WinDLL('user32', use_last_error=True)

    class MonitorInfo(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                    ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD),
                    ('szDevice', wintypes.WCHAR * 32)]

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                      ctypes.POINTER(wintypes.RECT), ctypes.c_ssize_t)
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), callback_type, ctypes.c_ssize_t]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    monitors = []
    errors = []

    @callback_type
    def collect(handle, _dc, _rect, _data):
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            errors.append(ctypes.get_last_error())
            return False
        def rectangle(rect):
            return (rect.left, rect.top, rect.right, rect.bottom)
        monitors.append(Display(info.szDevice, rectangle(info.rcMonitor), rectangle(info.rcWork), bool(info.dwFlags & 1)))
        return True

    previous_dpi = None
    change_dpi = getattr(user32, 'SetThreadDpiAwarenessContext', None)
    if change_dpi is not None:
        change_dpi.argtypes = [wintypes.HANDLE]
        change_dpi.restype = wintypes.HANDLE
        previous_dpi = change_dpi(ctypes.c_void_p(-4))
    try:
        if not user32.EnumDisplayMonitors(None, None, collect, 0):
            raise ctypes.WinError(errors[0] if errors else ctypes.get_last_error())
    finally:
        if previous_dpi:
            change_dpi(previous_dpi)
    return sorted(monitors, key=lambda display: display.device)
