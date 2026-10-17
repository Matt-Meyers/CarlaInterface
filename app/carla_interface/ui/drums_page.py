"""Drums tab: kit buttons, loop category, loop file, play, and link."""

from functools import partial
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from carla_interface.ui.widgets import (
    ChoiceStepper,
    PlayButton,
    TouchButton,
    set_style_property,
)


class DrumsPage(QWidget):
    """Kits on top, loop steppers along the bottom. Not a patch grid."""

    kitClicked = pyqtSignal(object)
    playClicked = pyqtSignal()
    linkClicked = pyqtSignal()
    fileSelected = pyqtSignal(object)

    def __init__(self, drums, cols, catalog):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._catalog = list(catalog)
        self._memory = {}
        self.bank = []

        cols = max(1, int(cols))
        visible = drums.kits[: drums.rows * cols]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(15, 20, 15, 10)
        grid.setHorizontalSpacing(15)
        grid.setVerticalSpacing(15)
        for index, kit in enumerate(visible):
            row, column = divmod(index, cols)
            btn = TouchButton(kit.name)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            btn.clicked.connect(partial(self._emit_kit, kit))
            grid.addWidget(btn, row, column)
            self.bank.append((btn, kit))
        rows = max(drums.rows, 1)
        for row in range(rows):
            grid.setRowStretch(row, 1)
        for column in range(cols):
            grid.setColumnStretch(column, 1)
        outer.addWidget(grid_host, 1)

        bar = QHBoxLayout()
        bar.setContentsMargins(15, 0, 15, 15)
        bar.setSpacing(12)

        self.category = ChoiceStepper()
        self.file = ChoiceStepper()
        for stepper in (self.category, self.file):
            stepper.setMinimumHeight(70)
            set_style_property(stepper, 'large', True)

        self.play = PlayButton()
        self.play.set_hold_enabled(False)
        self.play.setFixedSize(88, 70)
        self.play.clicked.connect(lambda _checked=False: self.playClicked.emit())

        self.link = QPushButton('Link')
        self.link.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.link.setMinimumHeight(70)
        self.link.setMinimumWidth(120)
        self.link.clicked.connect(lambda _checked=False: self.linkClicked.emit())

        bar.addWidget(self.category, 2)
        bar.addWidget(self.file, 5)
        bar.addWidget(self.play, 0)
        bar.addWidget(self.link, 0)
        outer.addLayout(bar)

        names = [name for name, _files in self._catalog]
        self.category.set_items(names)
        if self._catalog:
            self._show_category(0, emit=False)
        else:
            self.file.set_items([])
        self.category.valueChanged.connect(self._on_category)
        self.file.valueChanged.connect(self._on_file)
        self.play.setEnabled(self.selected_path() is not None)

    def _emit_kit(self, kit, _checked=False):
        self.kitClicked.emit(kit)

    def _category_name(self):
        index = self.category.value()
        if not self._catalog or not (0 <= index < len(self._catalog)):
            return None
        return self._catalog[index][0]

    def _current_files(self):
        index = self.category.value()
        if not self._catalog or not (0 <= index < len(self._catalog)):
            return []
        return self._catalog[index][1]

    def selected_path(self):
        files = self._current_files()
        index = self.file.value()
        if not files or not (0 <= index < len(files)):
            return None
        return files[index]

    def _on_category(self, index):
        self._show_category(index, emit=True)

    def _on_file(self, index):
        name = self._category_name()
        if name is not None:
            self._memory[name] = index
        self._emit_file()

    def _show_category(self, index, emit):
        if not self._catalog or not (0 <= index < len(self._catalog)):
            self.file.blockSignals(True)
            self.file.set_items([])
            self.file.blockSignals(False)
            return
        name, files = self._catalog[index]
        remembered = self._memory.get(name, 0)
        if remembered >= len(files):
            remembered = 0
        self.file.blockSignals(True)
        self.file.set_items([path.stem for path in files])
        self.file.setValue(remembered)
        self.file.blockSignals(False)
        if emit:
            self._emit_file()

    def _emit_file(self):
        path = self.selected_path()
        if path is not None:
            self.fileSelected.emit(path)

    def show_path(self, path):
        """Move the steppers to this file without emitting fileSelected."""
        path = Path(path)
        for cat_index, (name, files) in enumerate(self._catalog):
            for file_index, candidate in enumerate(files):
                if Path(candidate) != path:
                    try:
                        same = candidate.resolve() == path.resolve()
                    except OSError:
                        same = False
                    if not same:
                        continue
                self._memory[name] = file_index
                self.category.blockSignals(True)
                self.file.blockSignals(True)
                self.category.setValue(cat_index)
                self.file.set_items([item.stem for item in files])
                self.file.setValue(file_index)
                self.category.blockSignals(False)
                self.file.blockSignals(False)
                return

    def highlight(self, kit):
        for btn, candidate in self.bank:
            btn.set_active(
                candidate is kit or candidate.carla_idx == kit.carla_idx
            )

    def set_playing(self, playing):
        self.play.set_playing(bool(playing))

    def set_linked(self, linked):
        set_style_property(self.link, 'altActive', bool(linked))

    def set_files_locked(self, locked):
        # Same treatment as the split stepper during playback: hide the arrows.
        self.category.setEnabled(not locked and bool(self._catalog))
        self.file.setEnabled(not locked and bool(self._current_files()))

    def set_play_enabled(self, enabled):
        self.play.setEnabled(bool(enabled))
