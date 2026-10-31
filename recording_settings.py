"""Recording settings, kept separate from playback actions."""
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from recording import RecordingConfig


class RecordingSettings(ttk.LabelFrame):
    def __init__(self, parent):
        super().__init__(parent, text='Grabación de movimiento', padding=8)
        self.enabled = tk.BooleanVar(value=False)
        self.folder = tk.StringVar(value=str(Path.home() / 'Videos' / 'VigilanciaWebcam'))
        self.seconds = tk.StringVar(value='5')
        ttk.Checkbutton(self, text='Grabar video al detectar movimiento (sin audio)',
                        variable=self.enabled, command=self.refresh).pack(anchor='w')
        row = ttk.Frame(self)
        row.pack(fill='x', pady=4)
        ttk.Label(row, text='Guardar en:').pack(side='left')
        self.folder_entry = ttk.Entry(row, textvariable=self.folder)
        self.folder_entry.pack(side='left', fill='x', expand=True, padx=6)
        self.choose_button = ttk.Button(row, text='Elegir…', command=self.choose)
        self.choose_button.pack(side='left')
        ttk.Button(row, text='Abrir carpeta', command=self.open_folder).pack(side='left', padx=(6, 0))
        row = ttk.Frame(self)
        row.pack(fill='x')
        ttk.Label(row, text='Terminar tras').pack(side='left')
        self.seconds_input = ttk.Spinbox(row, from_=1, to=60, width=5, textvariable=self.seconds)
        self.seconds_input.pack(side='left', padx=6)
        ttk.Label(row, text='segundos sin movimiento · clips de hasta 5 minutos').pack(side='left')
        self.refresh()

    def refresh(self):
        state = 'normal' if self.enabled.get() else 'disabled'
        for widget in (self.folder_entry, self.choose_button, self.seconds_input):
            widget.configure(state=state)

    def choose(self):
        selected = filedialog.askdirectory(parent=self, title='Carpeta para las grabaciones',
                                            initialdir=self.folder.get(), mustexist=True)
        if selected:
            self.folder.set(selected)

    def get_config(self):
        if not self.enabled.get():
            return None
        if not self.folder.get().strip():
            raise ValueError('Elegí una carpeta para guardar las grabaciones.')
        try:
            seconds = float(self.seconds.get().replace(',', '.'))
        except ValueError:
            raise ValueError('Ingresá un tiempo sin movimiento entre 1 y 60 segundos.') from None
        config = RecordingConfig(Path(self.folder.get().strip()), seconds)
        config.prepare()
        return config

    def open_folder(self):
        try:
            if not self.folder.get().strip():
                raise ValueError('Elegí una carpeta para las grabaciones.')
            folder = Path(self.folder.get().strip()).expanduser().resolve()
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))
        except (OSError, ValueError) as exc:
            messagebox.showerror('Grabaciones', str(exc), parent=self)
