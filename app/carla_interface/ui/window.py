"""Main kiosk window: layout and signal wiring only (no OSC/MIDI strings)."""

from functools import partial

from PyQt6.QtCore import QDir, Qt
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QGridLayout,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QWidget,
)

from carla_interface.services.controller import PatchController
from carla_interface.services.midi import MidiService
from carla_interface.services.osc import CarlaOsc
from carla_interface.ui import palettes
from carla_interface.ui.widgets import (
    NoteSpinBox,
    OctaveSpinBox,
    TouchButton,
    TouchTabWidget,
)


class CarlaInterface(QWidget):
    """
    Touch UI for the Carla rack.

    Each category tab has two stacked grids: main presets (index 0) and the
    split-bank copy (index 1). Clicks go to PatchController; this class only
    updates palettes and which grid is visible.
    """

    def __init__(self, patches, categories, config):
        super().__init__()
        self.patches = patches
        self.categories = categories
        self.config = config
        self.controller = PatchController(
            patches,
            config,
            CarlaOsc(config.osc_port, config.osc_host),
            MidiService(config.sendmidi_path, config.midi_port),
        )

        # stylesheet.css uses url(icons:up_arrow_sml.png) etc.
        QDir.addSearchPath('icons', str(config.assets_dir))
        self.setWindowIcon(QIcon(str(config.logo_path)))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)  # kiosk

        # Buttons use QPalette (Linux). Spinboxes get the CSS below.
        self.palette = palettes.set_full_dark()
        self.palette_active = palettes.set_active(palettes.set_full_dark())
        self.palette_alt_active = palettes.set_alt_active(
            palettes.set_full_dark()
        )
        self.setPalette(self.palette)
        self.custom_css = config.stylesheet_path.read_text(encoding='utf-8')

        self.policy = QSizePolicy.Policy.Expanding
        font = QFont()
        font.setPointSize(12)
        self.setFont(font)

        # Header: Split toggle, split-note spinner, octave spinner.
        self.outer_layout = QGridLayout(self)
        self.header_container = QWidget()
        self.header_layout = QGridLayout(self.header_container)
        self.header_layout.setHorizontalSpacing(70)
        self.header_layout.setContentsMargins(30, 15, 30, 10)

        self.splitter_btn = QPushButton('Split')
        self.splitter_btn.setMinimumHeight(46)
        self.splitter_btn.clicked.connect(self._on_splitter_clicked)

        self.split_key_box = NoteSpinBox()
        self.split_key_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.split_key_box.setStyleSheet(self.custom_css)
        self.split_key_box.setMaximum(127)
        self.split_key_box.setValue(config.split_key_idx)
        self.split_key_box.valueChanged.connect(self._on_split_key_changed)

        self.octave_box = OctaveSpinBox()
        self.octave_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.octave_box.setStyleSheet(self.custom_css)
        self.octave_box.setMinimum(-4)
        self.octave_box.setMaximum(4)
        self.octave_box.setValue(0)
        self.octave_box.valueChanged.connect(self._on_octave_changed)

        self.header_layout.addWidget(self.splitter_btn, 0, 0, 1, 2)
        self.header_layout.addWidget(self.split_key_box, 0, 2)
        self.header_layout.addWidget(self.octave_box, 0, 3)
        self.outer_layout.addWidget(self.header_container, 0, 0, 1, 3)

        # One stacked pair of grids per category tab.
        self.stack_layouts = []
        self.main_btns = []
        self.split_btns = []
        self.tab_container = TouchTabWidget()
        self.tab_container.currentChanged.connect(self._on_tab_changed)
        for cat in self.categories:
            main_presets = []
            split_presets = []
            stack_container = QWidget()
            stack_layout = QStackedLayout(stack_container)
            self.stack_layouts.append(stack_layout)

            main_grid_container = QWidget()
            split_grid_container = QWidget()
            main_grid_layout = QGridLayout(main_grid_container)
            main_grid_layout.setContentsMargins(15, 20, 15, 20)
            main_grid_layout.setHorizontalSpacing(15)
            main_grid_layout.setVerticalSpacing(15)
            split_grid_layout = QGridLayout(split_grid_container)
            split_grid_layout.setContentsMargins(15, 20, 15, 20)
            split_grid_layout.setHorizontalSpacing(15)
            split_grid_layout.setVerticalSpacing(15)

            for patch in self.patches:
                for preset in patch.presets:
                    if preset.category == cat:
                        main_presets.append(preset)
                        split_presets.append(preset)
            self._add_buttons(
                self.main_btns,
                main_presets,
                self._on_main_clicked,
                main_grid_layout,
            )
            self._add_buttons(
                self.split_btns,
                split_presets,
                self._on_split_clicked,
                split_grid_layout,
            )
            stack_layout.addWidget(main_grid_container)   # index 0
            stack_layout.addWidget(split_grid_container)  # index 1
            self.tab_container.addTab(stack_container, cat)
        self.outer_layout.addWidget(self.tab_container, 1, 0, 1, 3)

    def _on_splitter_clicked(self):
        """Toggle split mode: swap grids, highlight Split, restore octave."""
        enabled = not self.controller.split_enabled
        self.controller.set_split_enabled(enabled)
        curr_tab = self.tab_container.currentIndex()
        if enabled:
            self.splitter_btn.setPalette(self.palette_alt_active)
            self.stack_layouts[curr_tab].setCurrentIndex(1)
        else:
            self.splitter_btn.setPalette(self.palette)
            self.stack_layouts[curr_tab].setCurrentIndex(0)
            self._reset_button_palettes(self.split_btns)
        # Low and high keyboards keep separate octave offsets.
        self.octave_box.setValue(self.controller.octave_value)

    def _on_tab_changed(self):
        # New tab's stack should match current split/main mode.
        curr_tab = self.tab_container.currentIndex()
        stack_index = 1 if self.controller.split_enabled else 0
        self.stack_layouts[curr_tab].setCurrentIndex(stack_index)

    def _on_main_clicked(self, btn, preset):
        self._reset_button_palettes(self.main_btns)
        self.controller.select_main(preset)
        btn.setPalette(self.palette_active)

    def _on_split_clicked(self, btn, preset):
        self._reset_button_palettes(self.split_btns)
        self.controller.select_split(preset)
        btn.setPalette(self.palette_active)

    def _on_split_key_changed(self):
        self.controller.set_split_key(self.split_key_box.value())

    def _on_octave_changed(self):
        self.controller.set_octave(self.octave_box.value())

    def _add_buttons(self, btn_store, presets, click_handler, layout):
        """Fill a grid left-to-right. Row starts at 1 for a bit of top gap."""
        x = 0
        y = 1
        for preset in presets:
            btn = TouchButton(preset.parent_name + '\n' + preset.name)
            btn.setSizePolicy(self.policy, self.policy)
            btn.clicked.connect(partial(click_handler, btn, preset))
            layout.addWidget(btn, y, x)
            btn_store.append(btn)
            x += 1
            if x >= self.config.cols:
                x = 0
                y += 1

    def _reset_button_palettes(self, buttons):
        for btn in buttons:
            btn.setPalette(self.palette)
