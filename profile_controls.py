"""Named-profile controls; configuration is never activated just by loading it."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

class ProfileControls(ttk.Frame):
    def __init__(self, parent, owner, store):
        super().__init__(parent, padding=(12, 0, 12, 8))
        self.owner = owner
        self.store = store
        self.selected = tk.StringVar(value=store.active)
        self.notice = tk.StringVar(value=store.warning or 'Los cambios se guardan al cerrar o cambiar de perfil.')
        row = ttk.Frame(self)
        row.pack(fill='x')
        ttk.Label(row, text='Perfil:').pack(side='left')
        self.combo = ttk.Combobox(row, textvariable=self.selected, state='readonly', width=25)
        self.combo.pack(side='left', fill='x', expand=True, padx=6)
        self.combo.bind('<<ComboboxSelected>>', self.switch)
        self.buttons = []
        for text, command in [('Nuevo', self.new), ('Duplicar', self.duplicate), ('Renombrar', self.rename), ('Eliminar', self.delete)]:
            button = ttk.Button(row, text=text, command=command)
            button.pack(side='left', padx=2)
            self.buttons.append(button)
        ttk.Button(row, text='Guardar', command=self.save).pack(side='left', padx=(6, 0))
        ttk.Label(self, textvariable=self.notice, wraplength=940).pack(anchor='w', pady=(3, 0))
        self.refresh()
        owner.apply_profile(store.settings())

    def refresh(self):
        self.combo.configure(values=self.store.names)
        self.selected.set(self.store.active)
        self.set_active(self.owner.armed.get())

    def set_active(self, active):
        self.combo.configure(state='disabled' if active else 'readonly')
        for button in self.buttons:
            button.configure(state='disabled' if active else 'normal')
        if len(self.store.names) == 1:
            self.buttons[-1].configure(state='disabled')

    def save_current(self):
        self.store.save(self.owner.profile_settings())
        self.notice.set(f'Perfil «{self.store.active}» guardado.')

    def save(self):
        try:
            self.save_current()
        except (ValueError, OSError, tk.TclError) as exc:
            self.show_error(exc)

    def show_error(self, exc):
        self.selected.set(self.store.active)
        self.notice.set('No se guardaron los cambios. Revisá el mensaje de error.')
        messagebox.showerror('Perfiles', str(exc), parent=self)

    def change(self, operation):
        if self.owner.armed.get() or self.owner.closing:
            self.selected.set(self.store.active)
            return
        try:
            operation()
            self.owner.apply_profile(self.store.settings())
            self.refresh()
            self.notice.set(f'Perfil «{self.store.active}» cargado. La vigilancia está detenida.')
        except (ValueError, OSError, tk.TclError) as exc:
            self.show_error(exc)

    def switch(self, *_):
        selected = self.selected.get()
        if selected != self.store.active:
            self.change(lambda: self.store.switch(selected, self.owner.profile_settings()))

    def new(self):
        self.create(False)

    def duplicate(self):
        self.create(True)

    def create(self, duplicate):
        if self.owner.armed.get():
            return
        name = simpledialog.askstring('Duplicar perfil' if duplicate else 'Nuevo perfil',
                                      'Nombre del perfil:', parent=self,
                                      initialvalue=f'{self.store.active} (copia)' if duplicate else '')
        if name is not None:
            self.change(lambda: self.store.create(name, self.owner.profile_settings(), duplicate))

    def rename(self):
        if self.owner.armed.get():
            return
        name = simpledialog.askstring('Renombrar perfil', 'Nuevo nombre:', parent=self, initialvalue=self.store.active)
        if name is not None:
            self.change(lambda: self.store.rename(name, self.owner.profile_settings()))

    def delete(self):
        if self.owner.armed.get() or len(self.store.names) == 1:
            return
        if messagebox.askyesno('Eliminar perfil', f'¿Eliminar el perfil «{self.store.active}» y sus ajustes?\nLos videos, audios e imágenes no se borran.', parent=self):
            self.change(self.store.delete)
