"""Touch-oriented Qt widgets used by the kiosk window."""

from math import floor

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QColorConstants,
    QFont,
    QIcon,
    QPainter,
    QPolygonF,
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
    # Wider than the 56px arrow widgets so a finger can miss the icon.
    _ZONE = 0.4
    _REPEAT_DELAY_MS = 400
    _REPEAT_INTERVAL_MS = 80

    def __init__(self):
        super().__init__()
        # Patch/tab shortcuts live on CarlaInterface; don't steal 1-9 / 0 / arrows.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # QWidget ignores stylesheet fills unless this is set.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName('TouchStepper')
        self.setMouseTracking(True)
        self._value = 0
        self._minimum = 0
        self._maximum = 99
        self._press_zone = 0
        self._repeat_ready = False

        self._down = QPushButton()
        self._down.setObjectName('stepDown')
        self._down.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._down.setIcon(QIcon('icons:dn_arrow_sml.png'))
        self._down.setIconSize(QSize(28, 28))

        self._up = QPushButton()
        self._up.setObjectName('stepUp')
        self._up.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._up.setIcon(QIcon('icons:up_arrow_sml.png'))
        self._up.setIconSize(QSize(28, 28))

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Layout size stays 56px; this widget hit-tests the wider end zones.
        for child in (self._down, self._up, self._label):
            child.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._down, 0)
        layout.addWidget(self._label, 1)
        layout.addWidget(self._up, 0)
        self._repeat = QTimer(self)
        self._repeat.timeout.connect(self._on_repeat)
        self._refresh_label()
        self._sync_disabled_chrome()

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

    def _sync_disabled_chrome(self):
        # Playback locks the value; hide steppers instead of dimming the chrome.
        shown = self.isEnabled()
        self._down.setVisible(shown)
        self._up.setVisible(shown)
        set_style_property(self._label, 'locked', not shown)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.EnabledChange:
            self._sync_disabled_chrome()
        super().changeEvent(event)

    def _zone_at(self, pos):
        width = self.width()
        if width <= 0:
            return 0
        if pos.x() < width * self._ZONE:
            return -1
        if pos.x() > width * (1.0 - self._ZONE):
            return 1
        return 0

    def _set_hot(self, zone):
        set_style_property(self._down, 'hot', zone < 0)
        set_style_property(self._up, 'hot', zone > 0)

    def _apply_zone(self, zone):
        if zone < 0:
            self._step_down()
        elif zone > 0:
            self._step_up()

    def _stop_repeat(self):
        self._repeat.stop()
        self._repeat_ready = False
        self._press_zone = 0

    def _on_repeat(self):
        if not self._repeat_ready:
            self._repeat_ready = True
            self._repeat.start(self._REPEAT_INTERVAL_MS)
        self._apply_zone(self._press_zone)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        zone = self._zone_at(event.position())
        if not zone:
            return
        self.grabMouse()
        self._press_zone = zone
        self._repeat_ready = False
        self._set_hot(zone)
        self._apply_zone(zone)
        self._repeat.start(self._REPEAT_DELAY_MS)

    def mouseMoveEvent(self, event):
        zone = self._zone_at(event.position())
        if event.buttons() & Qt.MouseButton.LeftButton:
            if zone == self._press_zone:
                return
            self._press_zone = zone
            self._set_hot(zone)
            if not zone:
                self._repeat.stop()
                self._repeat_ready = False
                return
            if not self._repeat.isActive():
                self._apply_zone(zone)
                self._repeat_ready = False
                self._repeat.start(self._REPEAT_DELAY_MS)
            return
        self._set_hot(zone)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()
        self._stop_repeat()
        if self.rect().contains(event.position().toPoint()):
            self._set_hot(self._zone_at(event.position()))
        else:
            self._set_hot(0)

    def leaveEvent(self, event):
        if QWidget.mouseGrabber() is not self:
            self._set_hot(0)
        super().leaveEvent(event)


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


class ChoiceStepper(TouchStepper):
    """Stepper whose center label is one of a list of strings."""

    def __init__(self):
        self._items = []
        self._full_text = ''
        super().__init__()

    def set_items(self, items):
        self._items = [str(item) for item in items]
        if not self._items:
            self.setMinimum(0)
            self.setMaximum(0)
            self.setEnabled(False)
            self._refresh_label()
            return
        self.setEnabled(True)
        self.setMinimum(0)
        self.setMaximum(len(self._items) - 1)
        self._refresh_label()

    def textFromValue(self, value):
        if not self._items:
            return ''
        index = max(0, min(int(value), len(self._items) - 1))
        return self._items[index]

    def _refresh_label(self):
        self._full_text = self.textFromValue(self._value)
        self._apply_elide()

    def _apply_elide(self):
        text = self._full_text
        width = self._label.width()
        if width < 8:
            self._label.setText(text)
            return
        self._label.setText(
            self._label.fontMetrics().elidedText(
                text, Qt.TextElideMode.ElideRight, max(1, width - 4)
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()


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
            painter.setBrush(
                QColor(120, 120, 120)
                if not self.isEnabled()
                else QColorConstants.White
            )
            painter.drawEllipse(QRectF(cx - side / 2, cy - side / 2, side, side))


class PlayButton(QPushButton):
    """Transport mark: white triangle idle, green while looping.

    A short press emits clicked. A hold emits held and swallows that click
    so opening the take browser does not also start or stop the loop.
    """

    held = pyqtSignal()
    _HOLD_MS = 600

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._playing = False
        self._suppress_click = False
        self._hold_enabled = True
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.timeout.connect(self._emit_held)

    def set_hold_enabled(self, enabled):
        self._hold_enabled = bool(enabled)
        if not self._hold_enabled:
            self._hold.stop()

    def set_playing(self, playing):
        self._playing = playing
        self.update()

    def _emit_held(self):
        self._suppress_click = True
        # setDown can release the button; block so that does not emit clicked.
        self.blockSignals(True)
        self.setDown(False)
        self.blockSignals(False)
        self.held.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._suppress_click = False
            if self._hold_enabled:
                self._hold.start(self._HOLD_MS)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._hold.isActive() and not self.rect().contains(
            event.position().toPoint()
        ):
            self._hold.stop()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._hold.stop()
        if self._suppress_click:
            self._suppress_click = False
            self.blockSignals(True)
            self.setDown(False)
            self.blockSignals(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        side = min(self.width(), self.height()) * 0.52
        cx = self.width() / 2
        cy = self.height() / 2
        if not self.isEnabled():
            painter.setBrush(QColor(120, 120, 120))
        elif self._playing:
            painter.setBrush(QColor(36, 180, 72))
        else:
            painter.setBrush(QColorConstants.White)
        triangle = QPolygonF(
            [
                QPointF(cx - side * 0.32, cy - side * 0.38),
                QPointF(cx - side * 0.32, cy + side * 0.38),
                QPointF(cx + side * 0.42, cy),
            ]
        )
        painter.drawPolygon(triangle)


class TouchButton(QPushButton):
    """Preset button. Idle/active fills come from stylesheet.css."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_active(self, active):
        set_style_property(self, 'active', active)
