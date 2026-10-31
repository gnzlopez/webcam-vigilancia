// WPF media windows; native VLC video output avoids secondary-monitor stalls.
using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

internal static class MediaPlayerApp
{
    [STAThread]
    private static int Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        try
        {
            AppContext.SetSwitch("Switch.System.Windows.DoNotScaleForDpiChanges", false);
            AppContext.SetSwitch("Switch.System.Windows.DoNotUsePresentationDpiCapabilityTier2OrGreater", false);
            if (args.Length != 8) throw new ArgumentException("Invalid player arguments.");
            string kind = args[0];
            string path = Path.GetFullPath(args[1]);
            double duration = double.Parse(args[2], CultureInfo.InvariantCulture);
            int parentId = int.Parse(args[3], CultureInfo.InvariantCulture);
            bool loop = bool.Parse(args[4]);
            bool keepOpen = bool.Parse(args[5]);
            string monitor = args[6];
            bool fullscreen = bool.Parse(args[7]);
            if (!File.Exists(path)) throw new FileNotFoundException("El archivo no existe.");
            if (kind != "audio" && kind != "video" && kind != "image")
                throw new ArgumentException("Tipo de archivo desconocido.");
            if ((kind == "image" && loop) || (kind != "image" && keepOpen))
                throw new ArgumentException("Opciones de reproducción inválidas.");
            if (double.IsNaN(duration) || double.IsInfinity(duration) || duration < 1 || duration > 86400)
                throw new ArgumentException("Duración inválida.");

            var window = new Window {
                Title = Path.GetFileName(path) + (loop ? " (en bucle)" : keepOpen ? " (sin cierre automático)" : ""), Width = 900, Height = 600,
                WindowStartupLocation = WindowStartupLocation.CenterScreen,
                Background = Brushes.Black
            };
            var layout = new DockPanel();
            window.Content = layout;
            var close = new Button { Content = "Cerrar", Height = 34 };
            DockPanel.SetDock(close, Dock.Bottom);
            layout.Children.Add(close);
            close.Click += delegate { window.Close(); };
            var watchdog = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
            watchdog.Tick += delegate {
                try {
                    using (var parent = Process.GetProcessById(parentId)) {
                        if (parent.HasExited) window.Close();
                    }
                } catch (ArgumentException) { window.Close(); }
            };
            window.Closed += delegate { watchdog.Stop(); };
            watchdog.Start();
            string failure = null;
            Action onWindowReady = null;
            VlcVideo video = null;

            if (kind == "image")
            {
                var bitmap = new BitmapImage();
                bitmap.BeginInit();
                bitmap.CacheOption = BitmapCacheOption.OnLoad;
                bitmap.UriSource = new Uri(path, UriKind.Absolute);
                bitmap.EndInit();
                layout.Children.Add(new Image { Source = bitmap, Stretch = Stretch.Uniform });
                if (!keepOpen)
                {
                    var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(duration) };
                    timer.Tick += delegate { window.Close(); };
                    onWindowReady = delegate { timer.Start(); };
                    window.Closed += delegate { timer.Stop(); };
                }
            }
            else if (kind == "video")
            {
                video = new VlcVideo(path, loop);
                layout.Children.Add(video.View);
                video.Ended += delegate { window.Close(); };
                video.Failed += delegate(string error) { failure = error; window.Close(); };
                onWindowReady = video.Start;
                window.Closed += delegate { video.Dispose(); };
            }
            else
            {
                var media = new MediaElement {
                    LoadedBehavior = MediaState.Manual, UnloadedBehavior = MediaState.Close,
                    Stretch = Stretch.Uniform, Volume = 1, ScrubbingEnabled = true
                };
                layout.Children.Add(media);
                if (kind == "audio")
                {
                    window.Width = 440;
                    window.Height = 150;
                    window.Background = Brushes.White;
                    var label = new TextBlock {
                        Text = loop ? "Reproduciendo audio en bucle…" : "Reproduciendo audio…", Margin = new Thickness(16), FontSize = 16
                    };
                    DockPanel.SetDock(label, Dock.Top);
                    layout.Children.Insert(1, label);
                }
                var openingTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(20) };
                openingTimer.Tick += delegate {
                    failure = "No se pudo abrir el archivo en 20 segundos.";
                    window.Close();
                };
                bool closed = false;
                bool started = false;
                media.MediaOpened += delegate {
                    openingTimer.Stop();
                    // Preroll in Pause so audio cannot advance while the first
                    // video frame and its rendering surface are being prepared.
                    window.Dispatcher.BeginInvoke(DispatcherPriority.ContextIdle, new Action(delegate {
                        if (closed || started) return;
                        started = true;
                        media.Position = TimeSpan.Zero;
                        media.Play();
                    }));
                };
                media.MediaEnded += delegate {
                    if (loop)
                    {
                        media.Position = TimeSpan.Zero;
                        media.Play();
                    }
                    else window.Close();
                };
                media.MediaFailed += delegate(object sender, ExceptionRoutedEventArgs e) {
                    failure = e.ErrorException.Message;
                    window.Close();
                };
                onWindowReady = delegate {
                    if (closed) return;
                    openingTimer.Start();
                    media.Source = new Uri(path, UriKind.Absolute);
                    media.Pause();
                };
                window.Closed += delegate { closed = true; openingTimer.Stop(); media.Close(); };
            }
            var placement = new WindowPlacement(window, close, monitor, fullscreen);
            if (video != null) video.KeyPressed += delegate(System.Windows.Input.Key key) { placement.HandleKey(key); };
            if (onWindowReady != null) placement.Ready += onWindowReady;
            new Application().Run(window);
            if (failure != null) throw new InvalidOperationException(failure);
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.Message);
            return 1;
        }
    }
}
