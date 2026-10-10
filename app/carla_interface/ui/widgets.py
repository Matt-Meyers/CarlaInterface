"""Touch-oriented Qt widgets used by the kiosk window."""

from math import floor

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QColorConstants,
    QFont,
    QIcon,
    QPainter,
)
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabBar,
    QTabWidget,
    QWidget,
)


def set_style_property(widget, name, value):
    """Restyle after a dynamic Qt property change (stylesheets cache selectors)."""
    widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class TouchStepper(QWidget):
    """Horizontal − value + control. Same chrome as the header buttons."""

    valueChanged = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        # Patch/tab shortcuts live on CarlaInterface; don't steal 1-9 / 0 / arrows.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # QWidget ignores stylesheet fills unless this is set.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName('TouchStepper')
        self._value = 0
        self._minimum = 0
        self._maximum = 99

        self._down = QPushButton()
        self._down.setObjectName('stepDown')
        self._down.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._down.setIcon(QIcon('icons:dn_arrow_sml.png'))
        self._down.setIconSize(QSize(28, 28))
        self._down.setAutoRepeat(True)
        self._down.setAutoRepeatDelay(400)
        self._down.setAutoRepeatInterval(80)
        self._down.clicked.connect(self._step_down)

        self._up = QPushButton()
        self._up.setObjectName('stepUp')
        self._up.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._up.setIcon(QIcon('icons:up_arrow_sml.png'))
        self._up.setIconSize(QSize(28, 28))
        self._up.setAutoRepeat(True)
        self._up.setAutoRepeatDelay(400)
        self._up.setAutoRepeatInterval(80)
        self._up.clicked.connect(self._step_up)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._down, 0)
        layout.addWidget(self._label, 1)
        layout.addWidget(self._up, 0)
        self._refresh_label()

    def textFromValue(self, value):
        return str(value)

    def value(self):
        return self._value

    def setValue(self, value):
        value = max(self._minimum, min(self._maximum, int(value)))
        changed = value != self._value
        self._value = value
        self._refresh_label()
        if changed:
            self.valueChanged.emit(value)

    def setMinimum(self, value):
        self._minimum = int(value)
        self.setValue(self._value)

    def setMaximum(self, value):
        self._maximum = int(value)
        self.setValue(self._value)

    def setAlignment(self, alignment):
        self._label.setAlignment(alignment)

    def _step_down(self):
        self.setValue(self._value - 1)

    def _step_up(self):
        self.setValue(self._value + 1)

    def _refresh_label(self):
        self._label.setText(self.textFromValue(self._value))


class NoteSpinBox(TouchStepper):
    """Stepper that shows MIDI note numbers as names (e.g. 60 -> C4)."""

    NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F',
             'F#', 'G', 'G#', 'A', 'A#', 'B']

    def textFromValue(self, value):
        # MIDI octave: middle C (60) is C4, so divide by 12 then subtract 1.
        if value > -1:
            octave = floor(value / len(self.NOTES)) - 1
            note = (value % len(self.NOTES))
            return str(self.NOTES[note]) + str(octave)
        return ''


class OctaveSpinBox(TouchStepper):
    """Octave offset stepper; same no-focus behavior as NoteSpinBox."""


class TouchTabWidget(QTabWidget):
    """Category tabs stretched to the full window width."""

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setTabBar(TouchTabBar())

    def resizeEvent(self, event):
        self.tabBar().setFixedWidth(self.width())
        super().resizeEvent(event)


class TouchTabBar(QTabBar):
    """Tab bar with large hit targets for fingers."""

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setDrawBase(False)
        font = QFont()
        font.setPointSize(14)
        self.setFont(font)

    def tabSizeHint(self, index):
        width = QTabBar.tabSizeHint(self, index).width()
        if width < 80:
            width = 80
        return QSize(width + 25, 70)


class RecordButton(QPushButton):
    """Transport mark instead of Record/Stop text: circle idle, square armed."""

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._recording = False

    def set_recording(self, recording):
        self._recording = recording
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        side = min(self.width(), self.height()) * 0.52
        cx = self.width() / 2
        cy = self.height() / 2
        if self._recording:
            painter.setBrush(QColor(220, 36, 36))
            half = side * 0.42
            painter.drawRect(QRectF(cx - half, cy - half, half * 2, half * 2))
        else:
            painter.setBrush(QColorConstants.White)
            painter.drawEllipse(QRectF(cx - side / 2, cy - side / 2, side, side))


class TouchButton(QPushButton):
    """Preset button. Idle/active fills come from stylesheet.css."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_active(self, active):
        set_style_property(self, 'active', active)
