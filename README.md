# Vigilancia con webcam

Aplicación local para Windows con vista previa, detección de movimiento, registro de eventos y acciones de audio, video e imagen. No graba ni transmite imágenes de la webcam. El encendido de monitores queda para una etapa posterior.

## Ejecutable para Windows

Abrí `VigilanciaWebcam.exe` con doble clic. Incluye Python y la interfaz gráfica, así que no necesitás una consola ni instalar Python para usarlo. La primera apertura puede tardar unos segundos mientras prepara sus componentes temporales.

Para las acciones de video necesita VLC de 64 bits instalado en `C:\Program Files\VideoLAN\VLC`; no está incluido dentro del ejecutable. Las ventanas multimedia utilizan .NET Framework de Windows. Las acciones y configuraciones todavía se conservan solo hasta cerrar la aplicación.

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

Las acciones y los ajustes se conservan durante la ejecución de la aplicación; por ahora no se guardan al cerrarla. El registro muestra hasta aproximadamente los últimos 1000 mensajes.

El reproductor usa ventanas WPF de Windows. Los videos se reproducen mediante VLC de 64 bits, con salida de video nativa y decodificación por software para evitar las pausas de imagen observadas al iniciar en monitores secundarios. Requiere VLC instalado en `C:\Program Files\VideoLAN\VLC`. Audio e imágenes usan WPF; sus formatos dependen de los códecs de Windows. Probá tus archivos con **Probar ahora**. Al ejecutar desde el código, el reproductor se prepara automáticamente en `.build` con el compilador de .NET Framework del sistema; el ejecutable distribuido ya lo incluye compilado. No se modifica la política de PowerShell.

### Evitar suspensión automática mientras vigila

Cuando está marcada y la vigilancia está activa, la aplicación pide a Windows que no suspenda la PC por inactividad. Así la cámara puede seguir detectando movimiento aunque no uses el teclado o el mouse. Por ejemplo, si Windows está configurado para suspender la PC después de 15 minutos sin uso, la solicitud evita esa suspensión mientras vigila.

Los monitores pueden apagarse por ahorro de energía: apagar una pantalla no es suspender la PC. Esta opción no enciende ni apaga las pantallas. Si la desmarcás, detenés la vigilancia o cerrás la aplicación, Windows vuelve a aplicar sus tiempos habituales de suspensión, salvo que otra aplicación también esté solicitando mantener la PC despierta. No se modifica permanentemente tu plan de energía.

La opción no impide que suspendas la PC manualmente desde Windows o con el cierre de tapa configurado para suspender. Si se suspende, la detección se interrumpe.

Probá primero que la detección siga sumando eventos al apagar las pantallas por ahorro de energía y volver a encenderlas. La suspensión manual, hibernación, cierre de tapa o políticas de energía pueden interrumpir la vigilancia. Esta versión no despierta la PC ni enciende los monitores al detectar movimiento.

La cámara necesita algo de luz. Sombras, reflejos y cambios de iluminación pueden generar eventos. El sistema detecta cambios visuales, no identifica personas. El registro se conserva solo durante la ejecución. El fondo se adapta lentamente, por lo que un objeto inmóvil deja de considerarse movimiento.

Si no abre la cámara, revisá Configuración → Privacidad y seguridad → Cámara → Permitir que las aplicaciones de escritorio accedan a la cámara, y cerrá otras aplicaciones que la estén usando.

## Generar el ejecutable

Desde PowerShell, en la carpeta del proyecto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build_exe.py
```

El script ejecuta las pruebas, compila el reproductor y genera `dist\VigilanciaWebcam.exe` con PyInstaller. Se necesitan Windows de 64 bits, Python con Tcl/Tk y el compilador de .NET Framework. VLC se instala por separado en la PC donde se utilizarán las acciones de video.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

Incluyen escena estática, calibración, movimiento sostenido, las tres reglas de repetición, demoras independientes, prevención de ejecuciones superpuestas, cancelación de acciones y validación de opciones de reproducción y monitor. La cámara física y el comportamiento de energía requieren una prueba en la PC.
