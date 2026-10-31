"""Configuration widgets for actions and their shared repeat policy."""
from dataclasses import replace
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from actions import ACTION_NAMES, REPEAT_NAMES, Action, ActionSequence, RepeatGate
from media import launch_media
from monitors import list_monitors, monitor_name


class ActionDialog(tk.Toplevel):
    def __init__(self, parent, on_save, action=None):
        super().__init__(parent)
        self.title('Editar acción' if action else 'Agregar acción')
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.on_save = on_save
        self.kind = tk.StringVar(value=ACTION_NAMES[action.kind if action else 'audio'])
        self.path = tk.StringVar(value=action.path if action else '')
        self.delay = tk.StringVar(value=f'{action.delay:g}' if action else '0')
        self.duration = tk.StringVar(value=f'{action.duration:g}' if action else '10')
        self.loop = tk.BooleanVar(value=action.loop if action else False)
        self.keep_open = tk.BooleanVar(value=action.keep_open if action else True)
        self.monitor_id = action.monitor if action else 'primary'
        self.monitor_choice = tk.StringVar()
        self.monitor_choices = {}
        self.fullscreen = tk.BooleanVar(value=action.fullscreen if action else False)
        self.test_status = tk.StringVar(value='La prueba reproduce inmediatamente, sin la espera configurada.')
        self.tester = ActionSequence(launch_media, self.test_status.set)
        self.timer = None
        body = ttk.Frame(self, padding=16)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Tipo de acción').grid(row=0, column=0, sticky='w', pady=6)
        combo = ttk.Combobox(body, textvariable=self.kind, values=list(ACTION_NAMES.values()), state='readonly', width=30)
        combo.grid(row=0, column=1, columnspan=2, sticky='ew')
        combo.bind('<<ComboboxSelected>>', self.type_changed)
        ttk.Label(body, text='Archivo').grid(row=1, column=0, sticky='w', pady=6)
        ttk.Entry(body, textvariable=self.path, width=48).grid(row=1, column=1, sticky='ew')
        ttk.Button(body, text='Examinar…', command=self.browse).grid(row=1, column=2, padx=(8, 0))
        ttk.Label(body, text='Espera desde la detección (s)').grid(row=2, column=0, sticky='w', pady=6)
        ttk.Spinbox(body, from_=0, to=86400, textvariable=self.delay, width=10).grid(row=2, column=1, sticky='w')
        self.loop_input = ttk.Checkbutton(body, text='Repetir en bucle hasta detener', variable=self.loop)
        self.loop_input.grid(row=3, column=0, columnspan=3, sticky='w', pady=6)
        self.keep_open_input = ttk.Checkbutton(body, text='Mantener la imagen abierta sin cierre automático', variable=self.keep_open, command=self.type_changed)
        self.keep_open_input.grid(row=3, column=0, columnspan=3, sticky='w', pady=6)
        self.duration_label = ttk.Label(body, text='Mostrar la imagen durante (s)')
        self.duration_label.grid(row=4, column=0, sticky='w', pady=6)
        self.duration_input = ttk.Spinbox(body, from_=1, to=86400, textvariable=self.duration, width=10)
        self.duration_input.grid(row=4, column=1, sticky='w')
        ttk.Label(body, text='Abrir en el monitor').grid(row=5, column=0, sticky='w', pady=6)
        self.monitor_input = ttk.Combobox(body, textvariable=self.monitor_choice, state='readonly', width=38)
        self.monitor_input.grid(row=5, column=1, sticky='ew')
        ttk.Button(body, text='Actualizar', command=self.refresh_monitors).grid(row=5, column=2, padx=(8, 0))
        ttk.Checkbutton(body, text='Abrir en pantalla completa (Esc vuelve a ventana)', variable=self.fullscreen).grid(row=6, column=0, columnspan=3, sticky='w', pady=6)
        ttk.Label(body, text='El monitor ubica la ventana. El audio usa la salida de sonido predeterminada de Windows.', wraplength=600).grid(row=7, column=0, columnspan=3, sticky='w', pady=6)
        ttk.Label(body, text='Los bucles y las imágenes sin cierre automático permanecen abiertos sin duplicarse. Las demás acciones pueden repetirse según el modo elegido. Detener vigilancia cierra todas.', wraplength=600).grid(row=8, column=0, columnspan=3, sticky='w', pady=6)
        ttk.Label(body, textvariable=self.test_status, wraplength=600).grid(row=9, column=0, columnspan=3, sticky='w', pady=12)
        buttons = ttk.Frame(body)
        buttons.grid(row=10, column=0, columnspan=3, sticky='ew')
        ttk.Button(buttons, text='Probar ahora', command=self.test).pack(side='left')
        ttk.Button(buttons, text='Detener prueba', command=self.tester.stop).pack(side='left', padx=6)
        ttk.Button(buttons, text='Guardar acción', command=self.save).pack(side='right')
        ttk.Button(buttons, text='Cancelar', command=self.close).pack(side='right', padx=6)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh_monitors()
        self.type_changed()
        self.grab_set()

    def kind_key(self):
        return next(key for key, label in ACTION_NAMES.items() if label == self.kind.get())

    def refresh_monitors(self):
        selected = self.monitor_choices.get(self.monitor_choice.get(), self.monitor_id)
        choices = {monitor_name('primary'): 'primary'}
        try:
            displays = list_monitors()
        except OSError as exc:
            displays = []
            self.test_status.set(f'No se pudieron consultar los monitores: {exc}')
        choices.update({display.label: display.device for display in displays})
        if selected not in choices.values():
            choices[f'{monitor_name(selected)} · No conectado (usará el principal)'] = selected
        self.monitor_choices = choices
        self.monitor_input.configure(values=list(choices))
        self.monitor_choice.set(next(label for label, device in choices.items() if device == selected))

    def type_changed(self, *_):
        is_image = self.kind_key() == 'image'
        if is_image:
            self.loop_input.grid_remove()
            self.keep_open_input.grid()
        else:
            self.keep_open_input.grid_remove()
            self.loop_input.grid()
        for widget in (self.duration_label, self.duration_input):
            if is_image:
                widget.grid()
            else:
                widget.grid_remove()
        self.duration_input.configure(state='disabled' if self.keep_open.get() else 'normal')

    def browse(self):
        patterns = {'audio': '*.wav *.mp3 *.wma', 'video': '*.mp4 *.wmv *.avi', 'image': '*.png *.jpg *.jpeg *.bmp'}
        path = filedialog.askopenfilename(parent=self, title='Elegí un archivo local', filetypes=[('Archivos multimedia', patterns[self.kind_key()]), ('Todos los archivos', '*.*')])
        if path:
            self.path.set(path)

    def read_action(self):
        try:
            kind = self.kind_key()
            keep_open = kind == 'image' and self.keep_open.get()
            duration = float(self.duration.get().replace(',', '.')) if kind == 'image' and not keep_open else 10
            action = Action(kind, self.path.get().strip(), float(self.delay.get().replace(',', '.')),
                            duration, loop=kind != 'image' and self.loop.get(), keep_open=keep_open,
                            monitor=self.monitor_choices.get(self.monitor_choice.get(), 'primary'),
                            fullscreen=self.fullscreen.get())
        except ValueError as exc:
            raise ValueError(f'Revisá el archivo y los tiempos. {exc}') from exc
        if not Path(action.path).is_file():
            raise ValueError('El archivo seleccionado no existe.')
        return action

    def test(self):
        try:
            action = self.read_action()
        except ValueError as exc:
            messagebox.showerror('Acción', str(exc), parent=self)
            return
        self.tester.stop()
        self.tester.start([replace(action, delay=0)], time.monotonic())
        if self.timer is None:
            self.tick()

    def tick(self):
        self.tester.tick(time.monotonic())
        self.timer = self.after(100, self.tick)

    def save(self):
        try:
            action = self.read_action()
        except ValueError as exc:
            messagebox.showerror('Acción', str(exc), parent=self)
            return
        self.on_save(action)
        self.close()

    def close(self):
        if self.timer is not None:
            self.after_cancel(self.timer)
        self.tester.stop()
        self.grab_release()
        self.destroy()


class ActionSettings(ttk.LabelFrame):
    def __init__(self, parent):
        super().__init__(parent, text='Acciones al detectar movimiento', padding=8)
        self.actions = []
        self.mode = tk.StringVar(value=REPEAT_NAMES['episode'])
        self.quiet_seconds = tk.StringVar(value='10')
        self.interval_seconds = tk.StringVar(value='60')
        self.help = tk.StringVar()
        row = ttk.Frame(self)
        row.pack(fill='x')
        ttk.Button(row, text='Agregar acción', command=self.add).pack(side='left')
        ttk.Button(row, text='Editar', command=self.edit).pack(side='left', padx=6)
        ttk.Button(row, text='Eliminar', command=self.remove).pack(side='left')
        listing = ttk.Frame(self)
        listing.pack(fill='x', pady=6)
        self.table = ttk.Treeview(listing, columns=('kind', 'path', 'delay', 'playback', 'destination'), show='headings', height=3, selectmode='browse')
        for name, title, width in [('kind', 'Acción', 125), ('path', 'Archivo', 200), ('delay', 'Espera (s)', 75), ('playback', 'Reproducción', 150), ('destination', 'Monitor / modo', 210)]:
            self.table.heading(name, text=title)
            self.table.column(name, width=width, minwidth=60, stretch=name == 'path')
        scroll = ttk.Scrollbar(listing, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.table.pack(side='left', fill='x', expand=True)
        self.table.bind('<Double-1>', lambda _: self.edit())
        repeat = ttk.Frame(self)
        repeat.pack(fill='x')
        ttk.Label(repeat, text='Volver a ejecutar:').pack(side='left')
        combo = ttk.Combobox(repeat, values=list(REPEAT_NAMES.values()), textvariable=self.mode, state='readonly', width=36)
        combo.pack(side='left', padx=6)
        combo.bind('<<ComboboxSelected>>', self.mode_changed)
        self.time_input = ttk.Spinbox(repeat, from_=1, to=86400, width=7, textvariable=self.quiet_seconds)
        self.time_label = ttk.Label(repeat, text='segundos')
        ttk.Label(self, textvariable=self.help, wraplength=850).pack(anchor='w', pady=(6, 0))
        self.mode_changed()

    def mode_key(self):
        return next(key for key, label in REPEAT_NAMES.items() if label == self.mode.get())

    def mode_changed(self, *_):
        mode = self.mode_key()
        self.time_input.pack_forget()
        self.time_label.pack_forget()
        if mode != 'once':
            self.time_input.configure(textvariable=self.quiet_seconds if mode == 'episode' else self.interval_seconds)
            self.time_input.pack(side='left')
            self.time_label.pack(side='left', padx=4)
        self.help.set({
            'episode': 'Espera ese tiempo sin movimiento; el siguiente movimiento vuelve a ejecutar la lista.',
            'once': 'Ejecuta la lista una sola vez, hasta que detengas y actives la vigilancia nuevamente.',
            'interval': 'Exige ese intervalo entre activaciones. Puede repetir mientras siga habiendo movimiento.',
        }[mode])

    def rule(self):
        mode = self.mode_key()
        text = self.quiet_seconds.get() if mode == 'episode' else self.interval_seconds.get()
        try:
            return RepeatGate(mode, 1 if mode == 'once' else float(text.replace(',', '.')))
        except ValueError as exc:
            raise ValueError('Ingresá un tiempo de repetición entre 1 y 86400 segundos.') from exc

    def refresh(self):
        for item in self.table.get_children():
            self.table.delete(item)
        for index, action in enumerate(self.actions):
            self.table.insert('', 'end', iid=str(index), values=(ACTION_NAMES[action.kind], action.path, f'{action.delay:g}', action.playback, action.destination))

    def add(self):
        def save(action):
            self.actions.append(action)
            self.refresh()
        ActionDialog(self, save)

    def edit(self):
        selected = self.table.selection()
        if not selected:
            return
        index = int(selected[0])
        def save(action):
            self.actions[index] = action
            self.refresh()
        ActionDialog(self, save, self.actions[index])

    def remove(self):
        selected = self.table.selection()
        if selected:
            self.actions.pop(int(selected[0]))
            self.refresh()
