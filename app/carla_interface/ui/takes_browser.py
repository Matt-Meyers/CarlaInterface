"""Paged grid of saved MIDI takes. Layout only; playback stays in the controller."""

from functools import partial
from math import ceil

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from carla_interface.ui.widgets import TouchButton, set_style_property


# Three columns fit a 5-inch screen with finger-sized cells.
_COLS = 4
_ROWS = 3
_TITLE_WIDTH = 22
_MAX_LINES = 3


def _pieces(word):
    if len(word) <= _TITLE_WIDTH:
        return [word]
    return [word[i:i + _TITLE_WIDTH] for i in range(0, len(word), _TITLE_WIDTH)]


def _cell_text(title, detail, reserved=0):
    extra = [line for line in (detail or '').split('\n') if line]
    words = (title or '').split() or ['']
    lines = ['']
    for word in words:
        for part in _pieces(word):
            trial = part if not lines[-1] else f'{lines[-1]} {part}'
            if lines[-1] and len(trial) > _TITLE_WIDTH:
                lines.append(part)
            else:
                lines[-1] = trial
    room = max(1, _MAX_LINES - len(extra) - reserved)
    if len(lines) > room:
        lines = lines[:room]
        lines[-1] = lines[-1].rstrip(' .') + '…'
    lines.extend(extra)
    return '\n'.join(lines)


class TakeButton(TouchButton):
    """Patch-style cell; stamp line is a child label so CSS can grey it."""

    def __init__(self):
        super().__init__()
        self.setObjectName('takeCell')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)
        layout.addStretch(1)
        self._body = QLabel()
        self._body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._stamp = QLabel()
        self._stamp.setObjectName('takeStamp')
        self._stamp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stamp.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for label in (self._body, self._stamp):
            label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
            layout.addWidget(label)
        layout.addStretch(1)

    def set_take_text(self, body, stamp=''):
        self._body.setText(body)
        self._stamp.setText(stamp)
        self._stamp.setVisible(bool(stamp))


class TakesBrowser(QWidget):
    """Newest Recording plus saved takes, paged, with a corner close button."""

    closed = pyqtSignal()
    chosen = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setObjectName('TakesBrowser')
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._items = []
        self._page = 0
        self._selected = None

        root = QVBoxLayout(self)
        root.setContentsMargins(15, 8, 15, 12)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addStretch(1)
        close = TouchButton('X')
        close.setObjectName('takeClose')
        close.setFixedSize(84, 76)
        close.clicked.connect(self.closed.emit)
        top.addWidget(close)
        root.addLayout(top)

        grid_host = QWidget()
        grid_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._grid = QGridLayout(grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(15)
        self._grid.setVerticalSpacing(15)
        self._buttons = []
        for slot in range(self.page_size):
            btn = TakeButton()
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            btn.clicked.connect(partial(self._on_slot, slot))
            row, col = divmod(slot, _COLS)
            self._grid.addWidget(btn, row, col)
            self._buttons.append(btn)
        for col in range(_COLS):
            self._grid.setColumnStretch(col, 1)
        for row in range(_ROWS):
            self._grid.setRowStretch(row, 1)
        root.addWidget(grid_host, 1)

        pager = QHBoxLayout()
        pager.setSpacing(15)
        self._prev = TouchButton('Prev')
        self._prev.setObjectName('takePage')
        self._prev.setMinimumHeight(72)
        self._prev.clicked.connect(lambda: self.step_page(-1))
        self._page_label = QLabel('1 / 1')
        self._page_label.setObjectName('takePageLabel')
        self._page_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setMinimumWidth(110)
        self._next = TouchButton('Next')
        self._next.setObjectName('takePage')
        self._next.setMinimumHeight(72)
        self._next.clicked.connect(lambda: self.step_page(1))
        pager.addWidget(self._prev, 2)
        pager.addWidget(self._page_label, 1)
        pager.addWidget(self._next, 2)
        root.addLayout(pager)

    @property
    def page_size(self):
        return _COLS * _ROWS

    def set_catalog(self, takes, selected_path):
        """takes are (path, title, detail). selected_path None highlights Newest."""
        self._items = [(None, 'Newest Recording', 'Latest file')]
        self._items.extend(takes)
        self._selected = self._normalize(selected_path)
        self._page = self._selected_index() // self.page_size
        self._render()

    def step_page(self, delta):
        pages = self._page_count()
        page = min(max(self._page + delta, 0), pages - 1)
        if page == self._page:
            return
        self._page = page
        self._render()

    def activate_slot(self, slot):
        index = self._page * self.page_size + slot
        if slot < 0 or slot >= self.page_size or index >= len(self._items):
            return
        if self._buttons[slot].property('empty'):
            return
        self._choose(self._items[index][0])

    def step_item(self, delta):
        if not self._items:
            return
        index = (self._selected_index() + delta) % len(self._items)
        self._choose(self._items[index][0])

    def _on_slot(self, slot):
        self.activate_slot(slot)

    def _choose(self, path):
        self._selected = path
        page = self._selected_index() // self.page_size
        if page != self._page:
            self._page = page
        self._render()
        self.chosen.emit(path)

    def _normalize(self, path):
        if path is None:
            return None
        for item_path, _title, _detail in self._items:
            if item_path is not None and item_path == path:
                return item_path
        return None

    def _selected_index(self):
        for index, (path, _title, _detail) in enumerate(self._items):
            if path == self._selected:
                return index
        return 0

    def _page_count(self):
        if not self._items:
            return 1
        return max(1, ceil(len(self._items) / self.page_size))

    def _render(self):
        start = self._page * self.page_size
        for slot, btn in enumerate(self._buttons):
            index = start + slot
            if index >= len(self._items):
                btn.set_take_text('')
                btn.set_active(False)
                set_style_property(btn, 'empty', True)
                continue
            path, title, detail = self._items[index]
            extras = [line for line in (detail or '').split('\n') if line]
            stamp = extras.pop() if path is not None and extras else ''
            btn.set_take_text(
                _cell_text(title, '\n'.join(extras), reserved=1 if stamp else 0),
                stamp,
            )
            btn.set_active(path == self._selected)
            set_style_property(btn, 'empty', False)
        pages = self._page_count()
        self._page_label.setText(f'{self._page + 1} / {pages}')
        self._prev.setEnabled(self._page > 0)
        self._next.setEnabled(self._page + 1 < pages)
