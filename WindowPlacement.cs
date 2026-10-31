// Place the player in native monitor coordinates, including negative origins.
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Threading;
using Microsoft.Win32;
using Screen = System.Windows.Forms.Screen;

internal sealed class WindowPlacement
{
    [StructLayout(LayoutKind.Sequential)]
    private struct NativePoint { public int X; public int Y; }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(IntPtr window, IntPtr insertAfter, int x, int y, int width, int height, uint flags);
    [DllImport("user32.dll")]
    private static extern IntPtr MonitorFromPoint(NativePoint point, uint flags);
    [DllImport("shcore.dll")]
    private static extern int GetDpiForMonitor(IntPtr monitor, int type, out uint x, out uint y);

    private readonly Window window;
    private readonly Button close;
    private readonly string device;
    private readonly double preferredWidth;
    private readonly double preferredHeight;
    private bool fullscreen;
    private bool closed;
    internal event Action Ready;

    internal WindowPlacement(Window window, Button close, string device, bool fullscreen)
    {
        this.window = window;
        this.close = close;
        this.device = device;
        this.fullscreen = fullscreen;
        preferredWidth = window.Width;
        preferredHeight = window.Height;
        window.WindowStartupLocation = WindowStartupLocation.Manual;
        window.SourceInitialized += delegate { Apply(); };
        bool positioned = false;
        window.ContentRendered += delegate {
            if (!positioned)
            {
                positioned = true;
                Apply();
                // Let monitor/DPI changes and the resulting layout/render pass
                // settle before a decoder starts its playback clock.
                window.Dispatcher.BeginInvoke(DispatcherPriority.ContextIdle, new Action(delegate {
                    if (closed) return;
                    window.UpdateLayout();
                    if (Ready != null) Ready();
                }));
            }
        };
        window.PreviewKeyDown += delegate(object sender, KeyEventArgs e) {
            if (HandleKey(e.Key)) e.Handled = true;
        };
        SystemEvents.DisplaySettingsChanged += OnDisplayChanged;
        window.Closed += delegate {
            closed = true;
            SystemEvents.DisplaySettingsChanged -= OnDisplayChanged;
        };
    }

    internal bool HandleKey(Key key)
    {
        if (key == Key.Escape && fullscreen) fullscreen = false;
        else if (key == Key.F11) fullscreen = !fullscreen;
        else return false;
        Apply();
        return true;
    }

    private void OnDisplayChanged(object sender, EventArgs e)
    {
        if (closed || window.Dispatcher.HasShutdownStarted) return;
        window.Dispatcher.BeginInvoke(new Action(delegate { if (!closed) Apply(); }));
    }

    private Screen SelectedScreen()
    {
        foreach (Screen screen in Screen.AllScreens)
            if (string.Equals(screen.DeviceName, device, StringComparison.OrdinalIgnoreCase)) return screen;
        return Screen.PrimaryScreen ?? Screen.AllScreens[0];
    }

    private static double ScaleFor(Screen screen)
    {
        try
        {
            uint x, y;
            var point = new NativePoint { X = screen.Bounds.Left + 1, Y = screen.Bounds.Top + 1 };
            IntPtr monitor = MonitorFromPoint(point, 2);
            if (GetDpiForMonitor(monitor, 0, out x, out y) == 0) return x / 96.0;
        }
        catch (DllNotFoundException) { }
        catch (EntryPointNotFoundException) { }
        return 1;
    }

    private void Apply()
    {
        var screen = SelectedScreen();
        window.WindowState = WindowState.Normal;
        window.WindowStyle = fullscreen ? WindowStyle.None : WindowStyle.SingleBorderWindow;
        window.ResizeMode = fullscreen ? ResizeMode.NoResize : ResizeMode.CanResize;
        window.Topmost = fullscreen;
        close.Visibility = fullscreen ? Visibility.Collapsed : Visibility.Visible;
        var area = fullscreen ? screen.Bounds : screen.WorkingArea;
        double scale = ScaleFor(screen);
        int width = fullscreen ? area.Width : Math.Min((int)Math.Round(preferredWidth * scale), area.Width);
        int height = fullscreen ? area.Height : Math.Min((int)Math.Round(preferredHeight * scale), area.Height);
        int x = area.Left + (area.Width - width) / 2;
        int y = area.Top + (area.Height - height) / 2;
        IntPtr handle = new WindowInteropHelper(window).Handle;
        if (handle != IntPtr.Zero && !SetWindowPos(handle, IntPtr.Zero, x, y, width, height, 0x0004 | 0x0020))
            throw new Win32Exception(Marshal.GetLastWin32Error());
    }
}
