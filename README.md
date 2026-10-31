# Vigilancia con webcam

Aplicación local para Windows con vista previa, detección de movimiento, encendido de monitores, grabación opcional de clips con audio y acciones de audio, video e imagen. La grabación se habilita desde la configuración y guarda archivos en la carpeta elegida.

## Ejecutable para Windows

Abrí `VigilanciaWebcam.exe` con doble clic. Incluye Python y la interfaz gráfica, así que no necesitás una consola ni instalar Python para usarlo. La primera apertura puede tardar unos segundos mientras prepara sus componentes temporales.

Para las acciones de video necesita VLC de 64 bits instalado en `C:\Program Files\VideoLAN\VLC`; no está incluido dentro del ejecutable. Las ventanas multimedia utilizan .NET Framework de Windows. Las configuraciones y acciones se guardan en perfiles y se recuperan al volver a abrir la aplicación.

## Instalación desde el código

Necesitás Python con Tcl/Tk. Esta instalación se verificó con Python 3.15.2. Desde PowerShell, en esta carpeta (si ya existe `.venv` con las dependencias, pasá directamente al último comando):

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## Uso

1. Iniciá la cámara con índice 0. Si corresponde a otra cámara, detenela y probá 1 o 2.
2. Configurá la sensibilidad y la opción de evitar suspensión. Debajo de esas opciones, presioná **Activar vigilancia** y dejá la escena quieta durante tres segundos para calibrar. Si la cámara estaba detenida, el botón también la inicia. La configuración se reemplaza por el registro de movimientos, con el estado y los mensajes de calibración encima. El botón queda amarillo y muestra **Preparando vigilancia…** mientras abre y calibra la cámara; al terminar la calibración cambia a rojo con **Detener vigilancia**. Podés presionarlo durante la preparación para cancelar o durante la vigilancia para detenerla: vuelve la configuración y queda la vista previa.
3. Movete frente a la cámara: se dibujarán rectángulos y aparecerán eventos en el registro.
4. Para reajustar la sensibilidad, detené la vigilancia: un valor más alto admite áreas de movimiento más pequeñas. Se requiere movimiento sostenido durante 0,3 segundos y se generan eventos como máximo cada tres segundos. Las opciones y los eventos registrados se conservan al alternar entre configuración y vigilancia.
5. Con vigilancia activa y la opción de evitar suspensión marcada, la aplicación pide a Windows mantener la PC despierta. Las pantallas pueden apagarse según la configuración de energía de Windows. La aplicación no cambia esa configuración permanentemente.
6. Al detener la vigilancia, se libera la solicitud de mantener la PC despierta. **Detener cámara** o cerrar la aplicación también libera la webcam.

### Perfiles de configuración

La barra **Perfil** permite mantener distintas configuraciones, por ejemplo **Casa**, **Noche** u **Oficina**. La primera vez se utiliza **Predeterminado**. Cada perfil conserva el índice de cámara, la sensibilidad, las opciones de suspensión y encendido de monitores, la grabación y su carpeta, el micrófono, las reglas de repetición y todas las acciones con sus archivos, demoras, bucles, monitores y modos de pantalla.

- **Nuevo:** pedí un nombre y comenzá con los ajustes iniciales y la lista de acciones vacía.
- **Duplicar:** creá una copia del perfil actual para modificarla sin cambiar el original.
- **Guardar:** guardá los cambios del perfil seleccionado inmediatamente.
- **Renombrar:** cambiá el nombre del perfil actual.
- **Eliminar:** borrá el perfil después de confirmar. Debe quedar al menos uno; los archivos multimedia y las grabaciones no se eliminan.

Los cambios se guardan automáticamente al **cerrar normalmente la aplicación** y antes de **cambiar, crear o duplicar un perfil**. Al volver a abrir se recupera el último perfil utilizado. La cámara, el micrófono y la vigilancia quedan detenidos hasta que los actives. Mientras la vigilancia esté activa, el selector y los botones que cambian de perfil quedan deshabilitados; **Guardar** sigue disponible. Si cambiás de perfil con la vista previa funcionando, la cámara se detiene para poder aplicar el índice del nuevo perfil.

Los perfiles se almacenan en `%LOCALAPPDATA%\VigilanciaWebcam\profiles.json`, fuera de la carpeta del ejecutable. Reemplazar el `.exe` o usar la versión desde Python conserva los mismos perfiles del usuario de Windows. Solo se guardan los ajustes y las rutas de los archivos; los videos, audios e imágenes no se copian dentro del perfil. Un archivo multimedia que ya no esté disponible permanece en la lista para poder corregir su ruta.

El micrófono se guarda por su nombre e interfaz de audio, no por un índice que Windows pueda reasignar. Si no está disponible al abrir, se muestra como **No conectado** y se pide seleccionar uno antes de grabar con audio. Los monitores desconectados conservan el comportamiento de usar el principal.

El guardado reemplaza el archivo completo de forma atómica y conserva una copia anterior en `profiles.json.bak`. Si se detecta un archivo dañado, se intenta recuperar esa copia y se informa en la barra de perfiles. Si no se puede guardar, se muestra el error; al cerrar podés cancelar el cierre para corregirlo o elegir cerrar sin guardar. Un cierre forzado o corte de energía conserva el último guardado completado, no necesariamente los cambios más recientes.

### Grabar cuando hay movimiento

1. Antes de activar la vigilancia, marcá **Grabar al detectar movimiento**. **Incluir audio del micrófono** viene activado; podés elegir el micrófono de la webcam, el de tus auriculares o el predeterminado de Windows. Desmarcalo únicamente si querés un video sin sonido.
2. Elegí la carpeta de destino. Por defecto se propone `Videos\VigilanciaWebcam` dentro de tu carpeta de usuario. **Abrir carpeta** permite acceder a los archivos.
3. Configurá cuántos segundos sin movimiento esperar antes de terminar el clip: **5 segundos** por defecto, entre 1 y 60.
4. Activá la vigilancia. Una vez terminada la calibración, el movimiento confirmado inicia la grabación. El indicador rojo **Grabando movimiento…** aparece sobre el registro.

Mientras siga habiendo movimiento se mantiene el mismo clip. Si vuelve a moverse algo durante la espera, esa espera comienza nuevamente. Después de guardar, otro movimiento confirmado genera un archivo nuevo. La grabación funciona aunque no haya acciones configuradas y es independiente de la opción **Volver a ejecutar**.

Los archivos son videos **AVI/MJPEG de 640 × 480, a 10 fotogramas por segundo, con audio mono del micrófono seleccionado**, con fecha y hora local en el nombre. Se guardan sin los recuadros del detector y empiezan al confirmar el movimiento; no incluyen los segundos anteriores. La cadencia se ajusta al tiempo transcurrido para evitar reproducir los clips acelerados si cambia la velocidad de captura. La escritura utiliza [VideoWriter de OpenCV](https://docs.opencv.org/4.x/dd/d9e/classcv_1_1VideoWriter.html).

El micrófono se abre al activar la vigilancia y se libera al detenerla. Mientras espera movimiento, mantiene un pequeño búfer en memoria, sin guardar audio en disco. Al grabar, se toma el tramo de sonido correspondiente al video. La captura usa [sounddevice/PortAudio](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html); cuando el controlador no proporciona tiempos de captura, se estima el inicio con su latencia declarada. No se captura directamente el sonido interno de la PC.

Al finalizar, FFmpeg une video y audio en segundo plano, manteniendo la detección activa. El registro indica **Guardando clip con audio** y después **Clip con audio guardado**. El ejecutable incluye los componentes necesarios; no necesitás instalar FFmpeg ni configurar una consola. Si Windows bloquea el micrófono, revisá **Configuración → Privacidad y seguridad → Micrófono → Permitir que las aplicaciones de escritorio accedan al micrófono**.

Un movimiento prolongado se divide en clips de hasta **5 minutos**. Detener la vigilancia, detener la cámara o cerrar normalmente la aplicación finaliza y guarda el clip actual. Los inicios, los archivos guardados y los errores aparecen en el registro. Durante la vigilancia también está disponible **Abrir grabaciones**.

Si falla la escritura, se pierde el micrófono o quedan menos de 100 MB libres, se detiene la grabación y se muestra el error; la detección y las acciones continúan. Después de resolverlo, detené y reactivá la vigilancia para reintentar. Un error de audio no se presenta como una grabación exitosa sin sonido. Si falla la unión de un clip, se conservan el video y el WAV por separado y se informa el error. Los clips no se borran automáticamente: revisá periódicamente el espacio disponible. Archivos con terminación `.grabando.avi`, `.grabando.wav` o `.uniendo.avi` están en curso o quedaron incompletos; un corte de energía o cierre forzado puede impedir finalizarlos.

La grabación está desmarcada en los perfiles nuevos. Al recuperar un perfil se conserva la selección guardada, pero no se empieza a grabar hasta activar la vigilancia y detectar movimiento. La versión ejecutable también puede grabar sin instalar Python; VLC solo es necesario para las acciones de reproducción de video.

### Acciones al detectar movimiento

En la configuración, usá **Agregar acción** para elegir audio, video o imagen y seleccionar un archivo local. Cada acción tiene una espera en segundos desde la misma detección: por ejemplo, un audio a los 0 segundos y una imagen a los 5 segundos.

- **Audio y video:** se reproducen una vez por defecto. Marcá **Repetir en bucle hasta detener** para que vuelvan al comienzo al finalizar y continúen reproduciéndose.
- **Imagen:** las nuevas acciones tienen marcada **Mantener la imagen abierta sin cierre automático**. Desmarcala para elegir una duración en segundos; las imágenes con duración configurada previamente mantienen su comportamiento al editarlas.
- La columna **Reproducción** muestra si cada archivo se reproduce una vez, en bucle, por un tiempo determinado o sin cierre automático.

Cada acción también tiene **Abrir en el monitor** y **Abrir en pantalla completa**. Podés elegir **Principal (automático)** o una pantalla concreta, identificada por su número y resolución. **Actualizar** vuelve a consultar las pantallas conectadas. El monitor y el modo elegidos aparecen en la columna **Monitor / modo**, y **Probar ahora** utiliza esa misma selección.

En modo ventana, el reproductor se centra en el área disponible del monitor elegido. En pantalla completa ocupa todo ese monitor, sin bordes ni botón de cierre, manteniendo la proporción del video o imagen. **Esc** vuelve al modo ventana para acceder a **Cerrar**; **F11** alterna entre ambos modos. Detener la vigilancia sigue cerrando todos los reproductores, también los que están en pantalla completa.

Si el monitor elegido no está conectado al abrir el archivo, se usa el principal. El editor conserva la selección original y la muestra como no conectada, para que puedas volver a usarla cuando reconectes la pantalla. Si cambia la disposición de pantallas durante la reproducción, se ajusta la ubicación y se usa el principal si la pantalla seleccionada ya no está disponible.

La selección de monitor determina dónde aparece la ventana, también para las acciones de audio. El sonido utiliza la salida predeterminada de Windows; esta opción no elige altavoces ni envía el sonido por el HDMI de ese monitor.

Los bucles y las imágenes sin cierre automático permanecen activos hasta cerrar su ventana con **Cerrar** o detener la vigilancia. No bloquean la repetición de las acciones temporales ni se duplican al volver a activar la lista. Por ejemplo, una imagen puede quedar abierta mientras un video se reproduce, finaliza y vuelve a ejecutarse según el intervalo configurado. Si una acción permanente todavía está esperando su demora inicial, conserva esa espera sin reiniciarla ni acumular copias. Detener la cámara, cerrar la aplicación o un error de cámara también detiene todas las reproducciones.

**Probar ahora** abre el archivo inmediatamente, ignorando su espera, para comprobar que se pueda reproducir. **Detener prueba**, guardar o cerrar el editor detiene esa prueba. En la lista principal podés seleccionar una acción para editarla o eliminarla. Si la lista está vacía, la vigilancia funciona y registra movimiento igualmente.

Las tres opciones de repetición controlan las activaciones de la lista. En cada activación se ejecutan las acciones temporales y las permanentes que no estén ya abiertas o programadas:

| Modo | Comportamiento |
| --- | --- |
| Cuando vuelva a haber movimiento (predeterminado) | Después de una activación, espera 10 segundos sin movimiento (configurables). El siguiente movimiento sostenido vuelve a ejecutar la lista. |
| Una vez hasta detener y reactivar | Ejecuta la lista una sola vez durante esa sesión de vigilancia, aunque sigan apareciendo registros de movimiento. |
| Como máximo cada cierto tiempo | Deja al menos 60 segundos entre activaciones (configurables), contados desde el inicio de cada lista. Si sigue habiendo movimiento, puede repetir al cumplirse el intervalo. |

Solo las acciones temporales (audio/video sin bucle e imágenes con duración) bloquean una nueva activación mientras esperan su demora o se reproducen; así se evita superponer nuevas copias. Los bucles y las imágenes sin cierre no se cuentan como ocupación para volver a ejecutar. En el modo de nuevo movimiento, un episodio que empieza mientras las acciones temporales están ocupadas se descarta: hace falta otro período sin movimiento y un nuevo episodio. En el modo de intervalo, puede repetirse al terminar las acciones temporales si el tiempo mínimo desde la última activación ya pasó y sigue habiendo movimiento. Si cerrás manualmente una acción permanente, podrá volver a abrirse en una próxima activación permitida. El modo **Una vez** sigue ejecutando cada acción una sola vez por sesión, hasta detener y reactivar la vigilancia.

Los registros del detector (como máximo uno cada tres segundos) son independientes de las activaciones de la lista. Arriba del log se muestra si las acciones están preparadas, esperando o reproduciéndose. Al detener la vigilancia, detener la cámara, perder la cámara o cerrar la aplicación, se cancelan las demoras y se cierran los reproductores iniciados por la aplicación. Al reactivar, empieza una sesión nueva y vuelve a estar disponible el modo de una sola vez.

Las acciones y los ajustes se guardan con el perfil al cerrar o cambiar de perfil. El registro de movimientos se conserva solo durante la ejecución y muestra hasta aproximadamente los últimos 1000 mensajes.

El reproductor usa ventanas WPF de Windows. Los videos se reproducen mediante VLC de 64 bits, con salida de video nativa y decodificación por software para evitar las pausas de imagen observadas al iniciar en monitores secundarios. Requiere VLC instalado en `C:\Program Files\VideoLAN\VLC`. Audio e imágenes usan WPF; sus formatos dependen de los códecs de Windows. Probá tus archivos con **Probar ahora**. Al ejecutar desde el código, el reproductor se prepara automáticamente en `.build` con el compilador de .NET Framework del sistema; el ejecutable distribuido ya lo incluye compilado. No se modifica la política de PowerShell.

### Encender monitores al detectar movimiento

La opción **Encender monitores al detectar movimiento** viene marcada. Después de la calibración, un movimiento confirmado solicita a Windows encender todas las pantallas, incluso si no hay acciones configuradas. También se solicita antes de abrir cada acción, para cubrir las acciones con demora. La solicitud no depende del modo de repetición de las acciones: puede encender las pantallas aunque ya haya una imagen abierta o un video en bucle.

Mientras continúa el movimiento, la solicitud se limita a una cada cinco segundos. En el registro aparece **Se solicitó encender los monitores**; si Windows rechaza la solicitud, se muestra el error y las acciones continúan. Esto confirma el envío de la orden, no permite verificar físicamente el estado de cada pantalla.

Funciona con pantallas apagadas por ahorro de energía de Windows. No puede encender un monitor apagado con su botón físico o sin alimentación, despertar una PC suspendida ni desbloquear una sesión de Windows. No mueve el mouse ni modifica permanentemente los tiempos de apagado. Cuando deja de haber movimiento y no se abren nuevas acciones, Windows vuelve a aplicar su tiempo de inactividad habitual. Se utilizan [las solicitudes de actividad de Windows](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate) y [SC_MONITORPOWER](https://learn.microsoft.com/en-us/windows/win32/menurc/wm-syscommand).

### Evitar suspensión automática mientras vigila

Cuando está marcada y la vigilancia está activa, la aplicación pide a Windows que no suspenda la PC por inactividad. Así la cámara puede seguir detectando movimiento aunque no uses el teclado o el mouse. Por ejemplo, si Windows está configurado para suspender la PC después de 15 minutos sin uso, la solicitud evita esa suspensión mientras vigila.

Los monitores pueden apagarse por ahorro de energía: apagar una pantalla no es suspender la PC. **Evitar suspensión** solo mantiene despierta la computadora; **Encender monitores al detectar movimiento** controla el encendido de las pantallas por separado. Si desmarcás la opción de evitar suspensión, detenés la vigilancia o cerrás la aplicación, Windows vuelve a aplicar sus tiempos habituales de suspensión, salvo que otra aplicación también esté solicitando mantener la PC despierta. No se modifica permanentemente tu plan de energía.

La opción no impide que suspendas la PC manualmente desde Windows o con el cierre de tapa configurado para suspender. Si se suspende, la detección se interrumpe.

Podés probar dejando que Windows apague las pantallas y moviéndote frente a la webcam una vez calibrada. Con ambas opciones marcadas, la PC sigue detectando y solicita encender las pantallas. La suspensión manual, hibernación, cierre de tapa o políticas de energía pueden interrumpir la vigilancia; esta versión no despierta una PC suspendida.

La cámara necesita algo de luz. Sombras, reflejos y cambios de iluminación pueden generar eventos. El sistema detecta cambios visuales, no identifica personas. El registro se conserva solo durante la ejecución. El fondo se adapta lentamente, por lo que un objeto inmóvil deja de considerarse movimiento.

Si no abre la cámara, revisá Configuración → Privacidad y seguridad → Cámara → Permitir que las aplicaciones de escritorio accedan a la cámara, y cerrá otras aplicaciones que la estén usando.

## Generar el ejecutable

Desde PowerShell, en la carpeta del proyecto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build_exe.py
```

El script ejecuta las pruebas, compila el reproductor e incluye FFmpeg y PortAudio en `dist\VigilanciaWebcam.exe` con PyInstaller. Se necesitan Windows de 64 bits, Python con Tcl/Tk y el compilador de .NET Framework. FFmpeg se obtiene mediante `imageio-ffmpeg`, instalado con las dependencias. VLC se instala por separado en la PC donde se utilizarán las acciones de video.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

Incluyen escena estática, calibración, movimiento sostenido, las tres reglas de repetición, demoras independientes, prevención de ejecuciones superpuestas, cancelación de acciones y validación de opciones de reproducción y monitor. Las pruebas de grabación generan y vuelven a leer videos sintéticos: comprueban duración, quietud, nuevos episodios, división de clips, cierre, errores de escritura y poco espacio. Las pruebas de audio verifican las dos pistas del AVI, la coincidencia temporal entre un tono y una señal visual, pérdidas de audio, errores del micrófono y de FFmpeg, y la liberación de recursos. Las pruebas automatizadas no utilizan el micrófono real. La cámara física y el comportamiento de energía requieren una prueba en la PC.
