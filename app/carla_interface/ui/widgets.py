from math import floor

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QFocusEvent, QFont, QPalette
from PyQt6.QtWidgets import QPushButton, QSpinBox, QTabBar, QTabWidget


class NoteSpinBox(QSpinBox):
    def __init__(self):
        super().__init__()
        self.NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F',
                      'F#', 'G', 'G#', 'A', 'A#', 'B']

    def textFromValue(self, value):
        if value > -1:
            octave = floor(value / len(self.NOTES)) - 1
            note = (value % len(self.NOTES))
            return str(self.NOTES[note]) + str(octave)

    def focusInEvent(self, e: QFocusEvent) -> None:
        self.clearFocus()


class OctaveSpinBox(QSpinBox):
    def focusInEvent(self, e: QFocusEvent) -> None:
        self.clearFocus()


class TouchTabWidget(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setTabBar(TouchTabBar())
        # QTabWidget sets bg as Button. Set here and override in child buttons.
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Button, QColor(42, 42, 42))
        self.setPalette(palette)

    def resizeEvent(self, event):
        self.tabBar().setFixedWidth(self.width())
        super().resizeEvent(event)


class TouchTabBar(QTabBar):
    def __init__(self):
        super().__init__()
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
        self.setPalette(palette)
