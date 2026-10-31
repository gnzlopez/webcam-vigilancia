// Native video output avoids WPF MediaElement's secondary-monitor frame stalls.
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms.Integration;
using System.Windows.Input;
using System.Windows.Threading;
using Forms = System.Windows.Forms;

internal sealed class VlcVideo : IDisposable
{
    private const CallingConvention Cdecl = CallingConvention.Cdecl;
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibraryEx(string path, IntPtr file, uint flags);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern IntPtr libvlc_new(int count, IntPtr args);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern void libvlc_release(IntPtr instance);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern IntPtr libvlc_media_new_path(IntPtr instance, IntPtr path);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern void libvlc_media_release(IntPtr media);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern IntPtr libvlc_media_player_new_from_media(IntPtr media);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern void libvlc_media_player_release(IntPtr player);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern void libvlc_media_player_set_hwnd(IntPtr player, IntPtr hwnd);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern int libvlc_media_player_play(IntPtr player);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern void libvlc_media_player_stop(IntPtr player);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern int libvlc_media_player_get_state(IntPtr player);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern long libvlc_media_player_get_time(IntPtr player);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern int libvlc_audio_get_track_count(IntPtr player);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern void libvlc_video_set_key_input(IntPtr player, uint enabled);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern void libvlc_video_set_mouse_input(IntPtr player, uint enabled);
    [DllImport("libvlc.dll", CallingConvention = Cdecl)] private static extern int libvlc_video_take_snapshot(IntPtr player, uint number, IntPtr path, uint width, uint height);

    private IntPtr instance;
    private IntPtr player;
    private readonly bool loop;
    private readonly VideoPanel panel;
    private readonly DispatcherTimer timer;
    private readonly Stopwatch opening = new Stopwatch();
    private bool disposed;
    private bool started;
    internal WindowsFormsHost View { get; private set; }
    internal event Action Ended;
    internal event Action<string> Failed;
    internal event Action<Key> KeyPressed;

    private sealed class VideoPanel : Forms.Panel
    {
        internal Action<Key> ForwardKey;
        internal VideoPanel()
        {
            SetStyle(Forms.ControlStyles.Selectable, true);
            TabStop = true;
            MouseDown += delegate { Focus(); };
        }
        protected override bool ProcessCmdKey(ref Forms.Message message, Forms.Keys key)
        {
            if (key == Forms.Keys.Escape || key == Forms.Keys.F11)
            {
                if (ForwardKey != null) ForwardKey(key == Forms.Keys.Escape ? Key.Escape : Key.F11);
                return true;
            }
            return base.ProcessCmdKey(ref message, key);
        }
    }

    internal VlcVideo(string path, bool loop)
    {
        this.loop = loop;
        panel = new VideoPanel { BackColor = System.Drawing.Color.Black, Dock = Forms.DockStyle.Fill };
        panel.ForwardKey = delegate(Key key) { if (KeyPressed != null) KeyPressed(key); };
        View = new WindowsFormsHost { Child = panel };
        timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(100) };
        timer.Tick += Poll;
        try
        {
            string directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "VideoLAN", "VLC");
            if (!File.Exists(Path.Combine(directory, "libvlc.dll")))
                throw new FileNotFoundException("Para reproducir videos se necesita VLC de " + (Environment.Is64BitProcess ? "64" : "32") + " bits en " + directory);
            Environment.SetEnvironmentVariable("VLC_PLUGIN_PATH", Path.Combine(directory, "plugins"));
            foreach (string name in new[] { "libvlccore.dll", "libvlc.dll" })
                if (LoadLibraryEx(Path.Combine(directory, name), IntPtr.Zero, 8) == IntPtr.Zero)
                    throw new Win32Exception(Marshal.GetLastWin32Error());
            string[] options = { "--quiet", "--no-video-title-show", "--no-osd", "--no-snapshot-preview", "--avcodec-hw=none", "--no-sub-autodetect-file" };
            var values = new IntPtr[options.Length];
            IntPtr arguments = Marshal.AllocHGlobal(IntPtr.Size * values.Length);
            try
            {
                for (int i = 0; i < values.Length; i++) values[i] = Utf8(options[i]);
                Marshal.Copy(values, 0, arguments, values.Length);
                instance = libvlc_new(values.Length, arguments);
            }
            finally
            {
                foreach (IntPtr value in values) if (value != IntPtr.Zero) Marshal.FreeHGlobal(value);
                Marshal.FreeHGlobal(arguments);
            }
            if (instance == IntPtr.Zero) throw new InvalidOperationException("No se pudo iniciar el motor de video VLC.");
            IntPtr file = Utf8(path);
            IntPtr media;
            try { media = libvlc_media_new_path(instance, file); }
            finally { Marshal.FreeHGlobal(file); }
            if (media == IntPtr.Zero) throw new InvalidOperationException("No se pudo abrir el video.");
            try { player = libvlc_media_player_new_from_media(media); }
            finally { libvlc_media_release(media); }
            if (player == IntPtr.Zero) throw new InvalidOperationException("No se pudo crear el reproductor de video.");
        }
        catch { Dispose(); throw; }
    }

    private static IntPtr Utf8(string value)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(value + "\0");
        IntPtr result = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, result, bytes.Length);
        return result;
    }

    internal void Start()
    {
        if (disposed || started) return;
        started = true;
        libvlc_media_player_set_hwnd(player, panel.Handle);
        libvlc_video_set_key_input(player, 0);
        libvlc_video_set_mouse_input(player, 0);
        if (libvlc_media_player_play(player) != 0) { Fail("VLC no pudo iniciar el video."); return; }
        opening.Restart();
        timer.Start();
    }

    private void Poll(object sender, EventArgs args)
    {
        if (disposed) return;
        int state = libvlc_media_player_get_state(player);
        if (state == 3) opening.Stop(); // Playing
        else if (state == 6) // Ended
        {
            if (loop)
            {
                libvlc_media_player_stop(player);
                if (libvlc_media_player_play(player) != 0) { Fail("No se pudo repetir el video."); return; }
                opening.Restart();
            }
            else { timer.Stop(); if (Ended != null) Ended(); }
        }
        else if (state == 7) Fail("VLC no pudo decodificar el archivo de video.");
        else if (opening.IsRunning && opening.Elapsed.TotalSeconds > 20)
            Fail("No se pudo abrir el video en 20 segundos.");
    }

    private void Fail(string error)
    {
        timer.Stop();
        if (Failed != null) Failed(error);
    }

    // Used by the local diagnostic harness to verify decoded frame progression.
    internal long PositionMilliseconds { get { return disposed ? 0 : libvlc_media_player_get_time(player); } }
    internal bool HasAudio { get { return !disposed && libvlc_audio_get_track_count(player) > 0; } }
    internal bool Snapshot(string path)
    {
        if (disposed || !started) return false;
        IntPtr file = Utf8(path);
        try { return libvlc_video_take_snapshot(player, 0, file, 192, 108) == 0; }
        finally { Marshal.FreeHGlobal(file); }
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        timer.Stop();
        if (player != IntPtr.Zero)
        {
            libvlc_media_player_stop(player);
            libvlc_media_player_release(player);
            player = IntPtr.Zero;
        }
        if (instance != IntPtr.Zero) { libvlc_release(instance); instance = IntPtr.Zero; }
        View.Dispose();
    }
}
