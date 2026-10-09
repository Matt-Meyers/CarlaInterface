"""Touch-oriented Qt widgets used by the kiosk window."""

from math import floor

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QFocusEvent, QFont, QPalette
from PyQt6.QtWidgets import QPushButton, QSpinBox, QTabBar, QTabWidget


class NoteSpinBox(QSpinBox):
    """Spinbox that shows MIDI note numbers as names (e.g. 60 -> C4)."""

    def __init__(self):
        super().__init__()
        # Patch/tab shortcuts live on CarlaInterface; don't steal 1-8 / arrows.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F',
                      'F#', 'G', 'G#', 'A', 'A#', 'B']

    def textFromValue(self, value):
        # MIDI octave: middle C (60) is C4, so divide by 12 then subtract 1.
        if value > -1:
            octave = floor(value / len(self.NOTES)) - 1
            note = (value % len(self.NOTES))
            return str(self.NOTES[note]) + str(octave)

    def focusInEvent(self, e: QFocusEvent) -> None:
        # Touchscreen: reject keyboard focus so taps don't pop an OSK.
        self.clearFocus()


class OctaveSpinBox(QSpinBox):
    """Octave offset spinner; same no-focus behavior as NoteSpinBox."""

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def focusInEvent(self, e: QFocusEvent) -> None:
        self.clearFocus()


class TouchTabWidget(QTabWidget):
    """Category tabs stretched to the full window width."""

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setTabBar(TouchTabBar())
        # QTabWidget paints its pane with ColorRole.Button; keep it slightly
        # darker than the tab buttons themselves.
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Button, QColor(42, 42, 42))
        self.setPalette(palette)

    def resizeEvent(self, event):
        self.tabBar().setFixedWidth(self.width())
        super().resizeEvent(event)


class TouchTabBar(QTabBar):
    """Tab bar with large hit targets for fingers."""

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
        self.setPalette(palette)
        self.setDrawBase(False)
        font = QFont()
        font.setPointSize(14)
        self.setFont(font)

    def tabSizeHint(self, index):
        width = QTabBar.tabSizeHint(self, index).width()
        if width < 80:
            width = 80
        return QSize(width + 25, 70)


class TouchButton(QPushButton):
    """Preset button. Idle palette here; the window applies the active one."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
        self.setPalette(palette)
