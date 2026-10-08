import os
from math import floor
from PyQt6.QtWidgets import QSpinBox, QTabWidget, QTabBar, QWidget, QStyleOption, QStyle, QPushButton
from PyQt6.QtGui import QFocusEvent, QFont, QPalette, QColor, QPainter
from PyQt6.QtCore import Qt, QSize


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
    def __init__(self):
        super().__init__()

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
        super(TouchTabWidget, self).resizeEvent(event)


class TouchTabBar(QTabBar):
    def __init__(self):
        super().__init__()
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
        # palette.setColor(QPalette.ColorRole.WindowText, QColor(200, 200, 250))
        self.setPalette(palette)
        self.setDrawBase(False)
        self.font = QFont()
        self.font.setPointSize(14)
        self.setFont(self.font)

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
