"""Repeat policy and cancellable action scheduling, independent of the UI."""
from dataclasses import dataclass
import math
from pathlib import Path
from monitors import monitor_name


ACTION_NAMES = {'audio': 'Reproducir audio', 'video': 'Reproducir video', 'image': 'Mostrar imagen'}
REPEAT_NAMES = {
    'episode': 'Cuando vuelva a haber movimiento',
    'once': 'Una vez hasta detener y reactivar',
    'interval': 'Como máximo cada cierto tiempo',
}


@dataclass(frozen=True)
class Action:
    kind: str
    path: str
    delay: float = 0
    duration: float = 10
    loop: bool = False
    keep_open: bool = False
    monitor: str = 'primary'
    fullscreen: bool = False

    def __post_init__(self):
        if self.kind not in ACTION_NAMES:
            raise ValueError('Elegí un tipo de acción válido.')
        if not isinstance(self.path, str) or not self.path.strip():
            raise ValueError('Elegí un archivo.')
        if not math.isfinite(self.delay) or not 0 <= self.delay <= 86400:
            raise ValueError('La espera debe estar entre 0 y 86400 segundos.')
        if not math.isfinite(self.duration) or not 1 <= self.duration <= 86400:
            raise ValueError('La duración debe estar entre 1 y 86400 segundos.')
        if not isinstance(self.loop, bool) or not isinstance(self.keep_open, bool):
            raise ValueError('Las opciones de reproducción deben ser booleanas.')
        if self.kind == 'image' and self.loop:
            raise ValueError('Para imágenes, usá la opción de mantener abierta.')
        if self.kind != 'image' and self.keep_open:
            raise ValueError('Para audio y video, usá la opción de repetir en bucle.')
        if not isinstance(self.monitor, str) or not self.monitor.strip() or len(self.monitor) > 128 or any(ord(c) < 32 for c in self.monitor):
            raise ValueError('Elegí un monitor válido.')
        if not isinstance(self.fullscreen, bool):
            raise ValueError('La opción de pantalla completa debe ser booleana.')

    @property
    def destination(self):
        mode = 'Completa' if self.fullscreen else 'Ventana'
        return f'{monitor_name(self.monitor)} · {mode}'

    @property
    def indefinite(self):
        return self.loop or self.keep_open

    @property
    def playback(self):
        if self.loop:
            return 'En bucle'
        if self.keep_open:
            return 'Sin cierre automático'
        return f'{self.duration:g} segundos' if self.kind == 'image' else 'Una vez'

    @property
    def label(self):
        return f'{ACTION_NAMES[self.kind]}: {Path(self.path).name} ({self.playback})'


class RepeatGate:
    def __init__(self, mode='episode', seconds=10):
        if mode not in REPEAT_NAMES:
            raise ValueError('Modo de repetición inválido.')
        if not math.isfinite(seconds) or not 1 <= seconds <= 86400:
            raise ValueError('El tiempo de repetición debe estar entre 1 y 86400 segundos.')
        self.mode = mode
        self.seconds = seconds
        self.last_activation = None
        self.quiet_since = None
        self.ready = True

    def update(self, now, moving, confirmed, busy=False):
        if self.quiet_since is not None and now - self.quiet_since >= self.seconds:
            self.ready = True
        if moving:
            self.quiet_since = None
        elif self.quiet_since is None:
            self.quiet_since = now
        if busy:
            # An episode that starts during playback is discarded, not queued.
            if moving:
                self.ready = False
            return False
        if not moving or not confirmed:
            return False
        if self.last_activation is not None:
            if self.mode == 'once':
                return False
            if self.mode == 'episode' and not self.ready:
                return False
            if self.mode == 'interval' and now - self.last_activation < self.seconds:
                return False
        self.last_activation = now
        self.ready = False
        return True


@dataclass
class RunningAction:
    index: int
    action: Action
    handle: object


class ActionSequence:
    def __init__(self, launch, report):
        self.launch = launch
        self.report = report
        self.pending = []
        self.running = []

    @property
    def busy(self):
        return bool(self.pending or self.running)

    @property
    def repeat_blocked(self):
        """Only finite actions block the next activation of the list."""
        return (any(not action.indefinite for _, _, action in self.pending)
                or any(not item.action.indefinite for item in self.running))

    def available_actions(self, actions):
        # Identify configured rows, not file paths: two intentional actions for
        # the same file (e.g. on different monitors) must remain independent.
        occupied = {index for _, index, action in self.pending if action.indefinite}
        occupied.update(item.index for item in self.running if item.action.indefinite)
        return [(index, action) for index, action in enumerate(actions)
                if not action.indefinite or index not in occupied]

    def can_start(self, actions):
        return not self.repeat_blocked and bool(self.available_actions(actions))

    def start(self, actions, now):
        if self.repeat_blocked:
            return False
        available = self.available_actions(actions)
        if not available:
            return False
        # Keep existing indefinite timers intact across repeat activations.
        self.pending.extend((now + action.delay, index, action) for index, action in available)
        self.pending.sort(key=lambda item: (item[0], item[1]))
        return True

    def tick(self, now):
        remaining = []
        for item in self.running:
            action, handle = item.action, item.handle
            code = handle.poll()
            if code is None:
                remaining.append(item)
            elif code:
                self.report(f'Error en {action.label}: {handle.error or "no se pudo reproducir el archivo"}')
            else:
                self.report(f'Finalizó {action.label}')
        self.running = remaining
        while self.pending and self.pending[0][0] <= now:
            _, index, action = self.pending.pop(0)
            try:
                handle = self.launch(action)
            except Exception as exc:
                self.report(f'Error en {action.label}: {exc}')
            else:
                self.running.append(RunningAction(index, action, handle))
                self.report(f'Inició {action.label}')

    def stop(self):
        had_work = self.busy
        self.pending.clear()
        for item in self.running:
            action, handle = item.action, item.handle
            try:
                handle.stop()
            except OSError as exc:
                self.report(f'No se pudo cerrar {action.label}: {exc}')
        self.running.clear()
        if had_work:
            self.report('Acciones detenidas; esperas pendientes canceladas.')
