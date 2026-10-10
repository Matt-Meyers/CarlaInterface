"""Main kiosk window: layout and signal wiring only (no OSC/MIDI strings)."""

from functools import partial

from PyQt6.QtCore import QDir, Qt
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
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
    RecordButton,
    TouchButton,
    TouchTabWidget,
    set_style_property,
)


# Top row / numpad (NumLock on); Qt has no Key_KeypadN. 0 is the tenth slot.
_SLOT_KEYS = {
    Qt.Key.Key_1: 0,
    Qt.Key.Key_2: 1,
    Qt.Key.Key_3: 2,
    Qt.Key.Key_4: 3,
    Qt.Key.Key_5: 4,
    Qt.Key.Key_6: 5,
    Qt.Key.Key_7: 6,
    Qt.Key.Key_8: 7,
    Qt.Key.Key_9: 8,
    Qt.Key.Key_0: 9,
}


class CarlaInterface(QWidget):
    """
    Touch UI for the Carla rack.

    Each category tab has two stacked grids: main presets (index 0) and the
    split-bank copy (index 1). Clicks go to PatchController; this class only
    updates button styles and which grid is visible.

    Keys 1-9 and 0 select slots on the current tab; left/right change tabs;
    up/down step through that tab's slots.
    """

    def __init__(self, patches, categories, config, windowed=False):
        # GTK/XFCE styles add 3D chrome on QPalette buttons; Fusion + CSS stay flat.
        QApplication.setStyle('Fusion')
        super().__init__()
        self.patches = patches
        self.categories = categories
        self.config = config
        self._windowed = windowed
        self.controller = PatchController(
            patches,
            config,
            CarlaOsc(config.osc_port, config.osc_host),
            MidiService(
                config.sendmidi_path,
                config.midi_port,
                config.midi_record_dir,
            ),
        )

        # stylesheet.css uses url(icons:up_arrow_sml.png) etc.
        QDir.addSearchPath('icons', str(config.assets_dir))
        self.setWindowIcon(QIcon(str(config.logo_path)))
        self.setWindowTitle('Carla Interface')
        if not windowed:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint)  # kiosk
        # Children are NoFocus; this widget must keep keys for patch/tab nav.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Palette fills the window; stylesheet.css paints buttons/tabs/spinboxes.
        self.setPalette(palettes.set_full_dark())
        self.setStyleSheet(config.stylesheet_path.read_text(encoding='utf-8'))

        self.policy = QSizePolicy.Policy.Expanding
        font = QFont()
        font.setPointSize(12)
        self.setFont(font)

        # Header: record mark, Split toggle, split-note spinner, octave spinner.
        self.outer_layout = QGridLayout(self)
        self.header_container = QWidget()
        self.header_layout = QGridLayout(self.header_container)
        self.header_layout.setHorizontalSpacing(45)
        self.header_layout.setContentsMargins(25, 15, 25, 10)

        self.record_btn = RecordButton()
        self.record_btn.setMinimumHeight(46)
        self.record_btn.clicked.connect(self._on_record_clicked)

        self.splitter_btn = QPushButton('Split')
        self.splitter_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.splitter_btn.setMinimumHeight(46)
        self.splitter_btn.clicked.connect(self._on_splitter_clicked)

        self.split_key_box = NoteSpinBox()
        self.split_key_box.setMinimumHeight(46)
        self.split_key_box.setMaximum(127)
        self.split_key_box.setValue(config.split_key_idx)
        self.split_key_box.valueChanged.connect(self._on_split_key_changed)

        self.octave_box = OctaveSpinBox()
        self.octave_box.setMinimumHeight(46)
        self.octave_box.setMinimum(-4)
        self.octave_box.setMaximum(4)
        self.octave_box.setValue(0)
        self.octave_box.valueChanged.connect(self._on_octave_changed)

        self.header_layout.addWidget(self.record_btn, 0, 0)
        self.header_layout.addWidget(self.splitter_btn, 0, 1)
        self.header_layout.addWidget(self.split_key_box, 0, 2)
        self.header_layout.addWidget(self.octave_box, 0, 3)
        self.header_layout.setColumnStretch(0, 1)
        self.header_layout.setColumnStretch(1, 3)
        self.header_layout.setColumnStretch(2, 2)
        self.header_layout.setColumnStretch(3, 2)
        self.outer_layout.addWidget(self.header_container, 0, 0, 1, 3)

        # One stacked pair of grids per category tab.
        self.stack_layouts = []
        self.main_btns = []
        self.split_btns = []
        # Per-tab (btn, preset) lists so keys 1-9 / 0 / up/down index the visible grid.
        self.main_bank_by_tab = []
        self.split_bank_by_tab = []
        self.main_sel_by_tab = []
        self.split_sel_by_tab = []
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
            self.main_bank_by_tab.append(
                self._add_buttons(
                    self.main_btns,
                    main_presets,
                    self._on_main_clicked,
                    main_grid_layout,
                )
            )
            self.split_bank_by_tab.append(
                self._add_buttons(
                    self.split_btns,
                    split_presets,
                    self._on_split_clicked,
                    split_grid_layout,
                )
            )
            self.main_sel_by_tab.append(-1)
            self.split_sel_by_tab.append(-1)
            stack_layout.addWidget(main_grid_container)   # index 0
            stack_layout.addWidget(split_grid_container)  # index 1
            self.tab_container.addTab(stack_container, cat)
        self.outer_layout.addWidget(self.tab_container, 1, 0, 1, 3)

    def show_app(self):
        if self._windowed:
            self.resize(1600, 900)
            self.show()
        else:
            self.showMaximized()

    def _on_record_clicked(self):
        if self.controller.is_recording:
            self.controller.stop_recording()
            self.record_btn.set_recording(False)
            return
        self.controller.start_recording()
        self.record_btn.set_recording(True)

    def closeEvent(self, event):
        if self.controller.is_recording:
            self.controller.stop_recording()
        super().closeEvent(event)

    def _on_splitter_clicked(self):
        """Toggle split mode: swap grids, highlight Split, restore octave."""
        enabled = not self.controller.split_enabled
        self.controller.set_split_enabled(enabled)
        curr_tab = self.tab_container.currentIndex()
        if enabled:
            set_style_property(self.splitter_btn, 'altActive', True)
            self.stack_layouts[curr_tab].setCurrentIndex(1)
        else:
            set_style_property(self.splitter_btn, 'altActive', False)
            self.stack_layouts[curr_tab].setCurrentIndex(0)
            self._reset_button_styles(self.split_btns)
        # Low and high keyboards keep separate octave offsets.
        self.octave_box.setValue(self.controller.octave_value)

    def _on_tab_changed(self):
        # New tab's stack should match current split/main mode.
        curr_tab = self.tab_container.currentIndex()
        stack_index = 1 if self.controller.split_enabled else 0
        self.stack_layouts[curr_tab].setCurrentIndex(stack_index)

    def _on_main_clicked(self, btn, preset):
        self._reset_button_styles(self.main_btns)
        self.controller.select_main(preset)
        btn.set_active(True)
        self._remember_selection(
            self.main_bank_by_tab, self.main_sel_by_tab, btn
        )

    def _on_split_clicked(self, btn, preset):
        self._reset_button_styles(self.split_btns)
        self.controller.select_split(preset)
        btn.set_active(True)
        self._remember_selection(
            self.split_bank_by_tab, self.split_sel_by_tab, btn
        )

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def keyPressEvent(self, event):
        key = event.key()
        # Terminal SIGINT never arrives while this window has focus.
        if (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and key == Qt.Key.Key_C
            and not event.isAutoRepeat()
        ):
            self.close()
            event.accept()
            return
        slot = _SLOT_KEYS.get(key)
        if slot is not None:
            # Hold-repeat would retrigger OSC/MIDI for the same preset.
            if not event.isAutoRepeat():
                self._activate_slot(slot)
            event.accept()
            return
        if key == Qt.Key.Key_Left:
            self._step_tab(-1)
        elif key == Qt.Key.Key_Right:
            self._step_tab(1)
        elif key == Qt.Key.Key_Down:
            self._step_slot(1)
        elif key == Qt.Key.Key_Up:
            self._step_slot(-1)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _visible_bank(self):
        if self.controller.split_enabled:
            return (
                self.split_bank_by_tab,
                self.split_sel_by_tab,
                self._on_split_clicked,
            )
        return self.main_bank_by_tab, self.main_sel_by_tab, self._on_main_clicked

    def _activate_slot(self, index):
        banks, _sel, handler = self._visible_bank()
        entries = banks[self.tab_container.currentIndex()]
        if 0 <= index < len(entries):
            btn, preset = entries[index]
            handler(btn, preset)

    def _step_slot(self, delta):
        banks, sel_by_tab, handler = self._visible_bank()
        tab = self.tab_container.currentIndex()
        entries = banks[tab]
        n = len(entries)
        if n == 0:
            return
        current = sel_by_tab[tab]
        if current < 0:
            index = 0 if delta > 0 else n - 1
        else:
            index = (current + delta) % n
        btn, preset = entries[index]
        handler(btn, preset)

    def _step_tab(self, delta):
        n = self.tab_container.count()
        if n == 0:
            return
        self.tab_container.setCurrentIndex(
            (self.tab_container.currentIndex() + delta) % n
        )

    def _remember_selection(self, banks, sel_by_tab, btn):
        for tab_idx, entries in enumerate(banks):
            for i, (b, _preset) in enumerate(entries):
                if b is btn:
                    sel_by_tab[tab_idx] = i
                    return

    def _on_split_key_changed(self):
        self.controller.set_split_key(self.split_key_box.value())

    def _on_octave_changed(self):
        self.controller.set_octave(self.octave_box.value())

    def _add_buttons(self, btn_store, presets, click_handler, layout):
        """Fill a grid left-to-right. Row starts at 1 for a bit of top gap."""
        x = 0
        y = 1
        last_row = 1
        bank = []
        for preset in presets:
            btn = TouchButton(preset.parent_name + '\n' + preset.name)
            btn.setSizePolicy(self.policy, self.policy)
            btn.clicked.connect(partial(click_handler, btn, preset))
            layout.addWidget(btn, y, x)
            btn_store.append(btn)
            bank.append((btn, preset))
            last_row = y
            x += 1
            if x >= self.config.cols:
                x = 0
                y += 1
        # Keep empty cells so a sparse tab still matches the configured grid.
        for row in range(1, max(self.config.rows, last_row) + 1):
            layout.setRowStretch(row, 1)
        return bank

    def _reset_button_styles(self, buttons):
        for btn in buttons:
            btn.set_active(False)
