"""Local webcam monitor. Run with python app.py."""
import ctypes
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

import cv2
from detector import MotionDetector
from actions import ActionSequence, RepeatGate
from action_editor import ActionSettings
from media import launch_media


class Monitor:
    def __init__(self, root):
        self.root = root
        root.title('Vigilancia con webcam')
        root.geometry(f'1000x{min(920, root.winfo_screenheight() - 100)}')
        root.minsize(860, 680)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.messages = queue.Queue(maxsize=2)
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.worker = None
        self.closing = False
        self.generation = 0
        self.options = (50, True, False, self.generation)
        self.gate = RepeatGate()
        self.session_actions = ()
        self.sequence = ActionSequence(launch_media, self.append_log)
        self.camera = tk.IntVar(value=0)
        self.sensitivity = tk.IntVar(value=50)
        self.awake = tk.BooleanVar(value=True)
        self.armed = tk.BooleanVar(value=False)
        self.preparing = False
        self.status = tk.StringVar(value='Cámara detenida')
        self.action_status = tk.StringVar()
        self.count = 0
        bar = ttk.Frame(root, padding=12)
        bar.pack(fill='x')
        ttk.Label(bar, text='Índice de cámara:').pack(side='left')
        ttk.Spinbox(bar, from_=0, to=20, width=4, textvariable=self.camera).pack(side='left', padx=8)
        self.start_button = ttk.Button(bar, text='Iniciar cámara', command=self.start)
        self.start_button.pack(side='left', padx=4)
        self.stop_button = ttk.Button(bar, text='Detener cámara', command=self.stop_camera, state='disabled')
        self.stop_button.pack(side='left', padx=4)
        self.preview = tk.Label(root, bg='#18212b', fg='white', text='La vista previa aparecerá aquí', width=1, height=1)
        controls = ttk.Frame(root, padding=12)
        controls.pack(side='bottom', fill='x')
        self.preview.pack(fill='both', expand=True, padx=12)
        panel = ttk.Frame(controls)
        panel.pack(fill='x')
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, minsize=140)

        self.settings_panel = ttk.Frame(panel)
        self.settings_panel.grid(row=0, column=0, sticky='nsew')
        ttk.Checkbutton(self.settings_panel, text='Evitar suspensión automática mientras vigila (permite apagar pantallas)', variable=self.awake, command=self.configure).pack(anchor='w')
        ttk.Label(self.settings_panel, text='Sensibilidad: baja ← → alta').pack(anchor='w', pady=(8, 0))
        ttk.Scale(self.settings_panel, from_=1, to=100, variable=self.sensitivity, command=self.configure).pack(fill='x')
        self.action_settings = ActionSettings(self.settings_panel)
        self.action_settings.pack(fill='x', pady=(8, 0))

        self.activity_panel = ttk.Frame(panel)
        self.activity_panel.grid(row=0, column=0, sticky='nsew')
        ttk.Label(self.activity_panel, textvariable=self.status, wraplength=880).pack(anchor='w', pady=(0, 6))
        ttk.Label(self.activity_panel, textvariable=self.action_status, wraplength=880).pack(anchor='w', pady=(0, 6))
        self.log = tk.Text(self.activity_panel, height=6, state='disabled')
        self.log.pack(fill='both', expand=True)
        self.activity_panel.grid_remove()

        self.vigilance_button = tk.Button(
            controls, text='Activar vigilancia', command=self.toggle_vigilance,
            font=('Segoe UI', 14, 'bold'), width=25, pady=12,
            bg='#15803d', fg='white', activebackground='#166534',
            activeforeground='white', relief='flat', cursor='hand2',
        )
        self.vigilance_button.pack(pady=(12, 0))
        self.root.after(50, self.poll)

    def configure(self, *_):
        self.options = (int(self.sensitivity.get()), self.awake.get(), self.armed.get(), self.generation)

    def set_vigilance(self, active):
        was_active = self.armed.get()
        if active != was_active:
            self.generation += 1
        self.armed.set(active)
        self.configure()
        if active:
            self.settings_panel.grid_remove()
            self.activity_panel.grid()
            if not was_active:
                self.preparing = True
                self.count = 0
                self.status.set('Preparando vigilancia…')
                self.append_log('Preparando vigilancia; esperando la calibración de la cámara.')
        else:
            self.preparing = False
            self.sequence.stop()
            if was_active:
                self.append_log('Vigilancia detenida.')
            self.activity_panel.grid_remove()
            self.settings_panel.grid()
        self.update_vigilance_button()

    def update_vigilance_button(self):
        if not self.armed.get():
            text, background, pressed, foreground = 'Activar vigilancia', '#15803d', '#166534', 'white'
        elif self.preparing:
            text, background, pressed, foreground = 'Preparando vigilancia…', '#facc15', '#eab308', '#1f2937'
        else:
            text, background, pressed, foreground = 'Detener vigilancia', '#b91c1c', '#991b1b', 'white'
        self.vigilance_button.configure(text=text, bg=background, activebackground=pressed,
                                       fg=foreground, activeforeground=foreground)

    def toggle_vigilance(self):
        if self.armed.get():
            self.set_vigilance(False)
        else:
            try:
                gate = self.action_settings.rule()
            except ValueError as exc:
                messagebox.showerror('Repetición', str(exc))
                return
            if self.start():
                self.gate = gate
                self.session_actions = tuple(self.action_settings.actions)
                self.set_vigilance(True)

    def stop_camera(self):
        self.set_vigilance(False)
        self.stop.set()

    def start(self):
        if self.closing:
            return False
        if self.worker is not None:
            return self.worker.is_alive() and not self.stop.is_set()
        try:
            index = self.camera.get()
            if index < 0:
                raise ValueError()
        except (ValueError, tk.TclError):
            messagebox.showerror('Cámara', 'Ingresá un índice de cámara válido: 0, 1, 2…')
            return False
        self.stop.clear()
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.status.set('Abriendo cámara…')
        self.worker = threading.Thread(target=self.capture, args=(index,), daemon=True)
        self.worker.start()
        return True

    def publish(self, item):
        try:
            self.messages.put_nowait(item)
        except queue.Full:
            try:
                self.messages.get_nowait()
            except queue.Empty:
                pass
            self.messages.put_nowait(item)

    def capture(self, index):
        camera = None
        try:
            camera = cv2.VideoCapture(index, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
            if not camera.isOpened():
                raise RuntimeError('No se pudo abrir la cámara. Probá otro índice y revisá los permisos de cámara de Windows o si otra aplicación la está usando.')
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            detector = MotionDetector()
            previous_generation = None
            power_active = False
            while not self.stop.is_set():
                ok, frame = camera.read()
                if not ok:
                    raise RuntimeError('Se perdió la conexión con la cámara. Detené e iniciá la cámara para reconectar.')
                frame = cv2.resize(frame, (640, 480))
                sensitivity, keep_awake, armed, generation = self.options
                requested_power = keep_awake and armed
                if os.name == 'nt' and requested_power != power_active:
                    result = ctypes.windll.kernel32.SetThreadExecutionState(0x80000001 if requested_power else 0x80000000)
                    if not result:
                        raise RuntimeError('Windows no pudo aplicar el control de suspensión.')
                    power_active = requested_power
                if armed and generation != previous_generation:
                    detector = MotionDetector()
                previous_generation = generation
                if armed:
                    now = time.monotonic()
                    boxes, moving, event, calibrating = detector.update(frame, now, sensitivity)
                    for x, y, w, h in boxes:
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 190, 255), 2)
                    state = 'Calibrando: dejá la escena quieta durante 3 segundos…' if calibrating else ('Movimiento detectado' if moving else 'Vigilando · sin movimiento')
                    self.events.put(('motion', generation, now, moving, detector.confirmed_motion, event, calibrating, state, datetime.now().strftime('%H:%M:%S')))
                self.publish(frame)
                self.stop.wait(0.06)
        except Exception as exc:
            self.events.put(('error', str(exc)))
        finally:
            if camera is not None:
                camera.release()
            if os.name == 'nt':
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    def poll(self):
        try:
            for _ in range(250):
                item = self.events.get_nowait()
                if item[0] == 'error':
                    self.set_vigilance(False)
                    self.status.set(item[1])
                    if not self.closing:
                        messagebox.showerror('Cámara', item[1])
                else:
                    self.handle_motion(item)
        except queue.Empty:
            pass
        self.sequence.tick(time.monotonic())
        self.update_action_status()
        frame = None
        try:
            while True:
                frame = self.messages.get_nowait()
        except queue.Empty:
            pass
        if frame is not None:
            ratio = min(max(1, self.preview.winfo_width()) / 640, max(1, self.preview.winfo_height()) / 480, 1)
            displayed = cv2.resize(frame, (max(1, int(640 * ratio)), max(1, int(480 * ratio))))
            ok, encoded = cv2.imencode('.png', displayed)
            if ok:
                self.photo = tk.PhotoImage(data=encoded.tobytes())
                self.preview.configure(image=self.photo, text='')
        if self.worker and not self.worker.is_alive():
            self.set_vigilance(False)
            self.start_button.configure(state='normal')
            self.stop_button.configure(state='disabled')
            self.worker = None
            self.count = 0
            if self.stop.is_set():
                self.status.set('Cámara detenida · webcam liberada')
        if self.closing and self.worker is None:
            self.root.destroy()
            return
        self.root.after(50, self.poll)

    def handle_motion(self, item):
        _, generation, now, moving, confirmed, event, calibrating, state, timestamp = item
        if generation != self.generation or not self.armed.get():
            return
        if self.preparing != calibrating:
            self.preparing = calibrating
            self.update_vigilance_button()
            if not calibrating:
                self.append_log('Calibración completada; vigilancia lista.', timestamp)
        if event:
            self.count += 1
            self.append_log(f'Movimiento detectado (registro {self.count})', timestamp)
        self.status.set(f'{state} · Registros de esta sesión: {self.count}')
        if not calibrating and self.session_actions:
            blocked = not self.sequence.can_start(self.session_actions)
            if self.gate.update(now, moving, confirmed, blocked):
                if self.sequence.start(self.session_actions, now):
                    self.append_log('Acciones disponibles activadas; se mantienen las que siguen abiertas.', timestamp)

    def append_log(self, text, timestamp=None):
        timestamp = timestamp or datetime.now().strftime('%H:%M:%S')
        self.log.configure(state='normal')
        self.log.insert('end', f'{timestamp} — {text}\n')
        if int(self.log.index('end-1c').split('.')[0]) > 1000:
            self.log.delete('1.0', '101.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def update_action_status(self):
        if not self.armed.get():
            return
        if self.preparing:
            text = 'Preparando la cámara. Podés presionar el botón amarillo para cancelar.'
        elif not self.session_actions:
            text = 'Sin acciones configuradas; se registran los movimientos.'
        elif self.sequence.repeat_blocked:
            pending = sum(not action.indefinite for _, _, action in self.sequence.pending)
            running = sum(not item.action.indefinite for item in self.sequence.running)
            text = f'Acciones temporales: {pending} en espera · {running} en reproducción'
        elif self.gate.last_activation is None:
            text = 'Acciones preparadas para el primer movimiento.'
        elif self.gate.mode == 'once':
            text = 'Modo una vez: las acciones ya se activaron. Para repetir, detené y reactivá la vigilancia.'
        elif not self.sequence.can_start(self.session_actions):
            text = 'Las acciones en bucle o sin cierre automático ya están abiertas o programadas; no se duplican.'
        elif self.gate.mode == 'episode':
            text = 'Acciones preparadas para un nuevo movimiento.' if self.gate.ready else f'Esperando {self.gate.seconds:g} segundos sin movimiento para habilitar otra activación.'
        else:
            seconds = max(0, self.gate.seconds - (time.monotonic() - self.gate.last_activation))
            text = f'Próxima activación disponible en {seconds:.0f} s, si hay movimiento.' if seconds else 'Acciones preparadas; se ejecutarán si hay movimiento.'
        persistent_pending = sum(action.indefinite for _, _, action in self.sequence.pending)
        persistent_running = sum(item.action.indefinite for item in self.sequence.running)
        if persistent_pending or persistent_running:
            text += f' · En bucle/sin cierre: {persistent_running} abiertas, {persistent_pending} pendientes.'
        self.action_status.set(text)

    def close(self):
        self.closing = True
        self.stop_camera()
        self.vigilance_button.configure(state='disabled')
        self.status.set('Cerrando cámara…')


if __name__ == '__main__':
    Monitor(tk.Tk())
    tk.mainloop()
