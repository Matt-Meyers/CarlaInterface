import os
import time
from PyQt6.QtWidgets import *
from PyQt6.QtWidgets import QPushButton as QPush
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor, QFocusEvent
from PyQt6.QtCore import Qt, QDir, QSize
from functools import partial
from qt_elems import NoteSpinBox, OctaveSpinBox, TouchTabWidget, TouchButton
import qt_ops
import osc_cmds

# Notes:
# Started adding windows capabilities but never finished.
# May not be worth doing? For now, must have Linux and Qt6 compatibilities.
# Change 'PyQt6' to 'PyQt5' if older distro.


# noinspection PyUnresolvedReferences
class CarlaInterface(QWidget):
    def __init__(self, patches, categories, split_start_idx, cols=4):
        super().__init__()
        # init
        self.patches = patches
        self.categories = categories
        self.split_start_idx = split_start_idx
        self.cols = cols    # columns of grid buttons
        self.work_dir = (os.path.dirname(os.path.realpath(__file__)))
        if os.name == 'nt':    # If Windows
            self.nt = True
            exe = os.path.join(self.work_dir, 'sendosc.exe')
        else:
            self.nt = False
            exe = None
        self.osc = osc_cmds.Osc('22752', exe=exe)
        self.midi = osc_cmds.Midi(self.work_dir, 'Midi Through Port-0')
        # TODO these patch indexes should be set in main
        self.split_lo_idx = 8      # split patch low index in Carla
        self.split_hi_idx = 9      # split patch high index in Carla
        self.split_key_idx = 60   # start idx, can be changed thru NoteSpinBox
        self.octave_lo_idx = 10   # transpose patch low index in Carla
        self.octave_hi_idx = 11   # transpose patch high index in Carla
        self.octave_lo = 0   # octave SpinBox val for low keys
        self.octave_hi = 0   # octave SpinBox val for high keys
        # window
        QDir.addSearchPath('icons', self.work_dir)   # for stylesheet rel paths
        self.setWindowIcon(QIcon('logo.png'))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)    # TODO
        # colors
        self.palette = qt_ops.set_full_dark()
        self.palette_active = qt_ops.set_active(qt_ops.set_full_dark())
        self.palette_alt_active = qt_ops.set_alt_active(qt_ops.set_full_dark())
        self.setPalette(self.palette)
        with open(os.path.join(self.work_dir, 'stylesheet.css')) as f:
            self.custom_css = f.read()
        if self.nt:
            self.setStyleSheet(self.custom_css)    # if Windows, use stylesheet
        # styles
        self.policy = QSizePolicy.Policy.Expanding
        self.font = QFont()
        self.font.setPointSize(12)
        self.setFont(self.font)

        # outer layouts
        self.outer_layout = QGridLayout(self)   # outer-most
        self.header_container = QWidget()
        self.header_layout = QGridLayout(self.header_container)
        self.header_layout.setHorizontalSpacing(70)
        self.header_layout.setContentsMargins(30, 15, 30, 10)
        # split button
        self.split_state = False
        self.splitter_btn = QPush('Split')   # activates split mode
        self.splitter_btn.setMinimumHeight(46)
        self.splitter_btn.clicked.connect(self.splitter_click)
        # split note SpinBox
        self.split_key_box = NoteSpinBox()
        self.split_key_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.split_key_box.setStyleSheet(self.custom_css)   # custom css
        self.split_key_box.setMaximum(127)
        self.split_key_box.setValue(self.split_key_idx)
        self.split_key_box.valueChanged.connect(self.split_key_box_chgd)
        # octave SpinBox
        self.octave_box = OctaveSpinBox()
        self.octave_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.octave_box.setStyleSheet(self.custom_css)  # custom css
        self.octave_box.setMinimum(-4)
        self.octave_box.setMaximum(4)
        self.octave_box.setValue(0)
        self.octave_box.valueChanged.connect(self.octave_box_chgd)
        # add to layout
        self.header_layout.addWidget(self.splitter_btn, 0, 0, 1, 2)
        self.header_layout.addWidget(self.split_key_box, 0, 2)
        self.header_layout.addWidget(self.octave_box, 0, 3)
        self.outer_layout.addWidget(self.header_container, 0, 0, 1, 3)
        # grid btns - have stacked layout to display "main" or "split" buttons
        # tabbed area
        self.stack_layouts = []
        self.main_btns = []
        self.split_btns = []
        self.tab_container = TouchTabWidget()
        self.tab_container.currentChanged.connect(self.tab_change)  # tab change
        for cat in self.categories:
            main_presets = []
            split_presets = []
            stack_container = QWidget()
            stack_layout = QStackedLayout(stack_container)   # stacked
            self.stack_layouts.append(stack_layout)
            # grid
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
            # main_btn creation loop
            for patch in self.patches:
                for preset in patch.presets:
                    if preset.category == cat:
                        main_presets.append(preset)
                        split_presets.append(preset)
            self.add_btns_to_layout(self.main_btns,
                                    main_presets,
                                    self.main_btn_click,
                                    main_grid_layout)
            self.add_btns_to_layout(self.split_btns,
                                    split_presets,
                                    self.split_btn_click,
                                    split_grid_layout)
            # add to stack layout
            stack_layout.addWidget(main_grid_container)
            stack_layout.addWidget(split_grid_container)
            self.tab_container.addTab(stack_container, cat)
        self.outer_layout.addWidget(self.tab_container, 1, 0, 1, 3)
        # other
        self.curr_main_carla_idx = 0

    # Event
    def splitter_click(self):
        """
        Create keyboard split. Sets carla split notes and shows the
        alternate 'split_btn' menu
        """
        self.split_state = not self.split_state
        if self.split_state is True:
            self.splitter_btn.setPalette(self.palette_alt_active)
            curr_tab = self.tab_container.currentIndex()
            self.stack_layouts[curr_tab].setCurrentIndex(1)
            self.send_split_key_osc(True)
            self.octave_box.setValue(self.octave_hi)
        else:
            self.splitter_btn.setPalette(self.palette)
            curr_tab = self.tab_container.currentIndex()
            self.stack_layouts[curr_tab].setCurrentIndex(0)
            self.send_split_key_osc(False)
            # disable split patches
            self.deselect_all_grid(self.split_btns, self.split_start_idx)
            self.octave_box.setValue(self.octave_lo)

    # Event
    def tab_change(self):
        if self.split_state is True:
            curr_tab = self.tab_container.currentIndex()
            self.stack_layouts[curr_tab].setCurrentIndex(1)
        else:
            curr_tab = self.tab_container.currentIndex()
            self.stack_layouts[curr_tab].setCurrentIndex(0)

    # Event
    def main_btn_click(self, btn, preset):
        """
        Event if a main_btn is clicked. Set active channel in Carla
        :param btn: main_btn
        :param preset: preset belonging to button
        :return:
        """
        # deactivate all
        self.deselect_all_grid(self.main_btns)
        # activate current index
        self.osc.send_osc(f'/{preset.carla_idx}/set_active', 'i', '1')
        self.curr_main_carla_idx = preset.carla_idx   # record current idx
        # send prog change
        if preset.preset_over_midi:
            # send midi after sleep
            time.sleep(.25)
            self.midi.send_prog_change(preset.idx)
        else:
            self.osc.send_osc(f'/{preset.carla_idx}/set_program',
                              'i',
                              preset.idx)
        btn.setPalette(self.palette_active)
        if self.nt:
            btn.setStyleSheet('background-color:#212121;')

    # Event
    def split_btn_click(self, btn, preset):
        """
        Event if a split_btn is clicked. Set active 2nd channel in Carla
        :param btn: split_btn
        :param preset: preset belonging to button
        :return:
        """
        carla_idx = preset.carla_idx + self.split_start_idx
        # deactivate all split patches
        self.deselect_all_grid(self.split_btns, self.split_start_idx)
        # activate current index
        self.osc.send_osc(f'/{carla_idx}/set_active', 'i', '1')
        # send prog change
        if preset.preset_over_midi:
            # deactivate main preset to avoid sending MIDI to it
            self.osc.send_osc(f'/{self.curr_main_carla_idx}/set_active',
                              'i',
                              '0')
            # send MIDI after sleep
            time.sleep(.25)
            self.midi.send_prog_change(preset.idx)
            time.sleep(.1)
            # reactivate main idx
            self.osc.send_osc(f'/{self.curr_main_carla_idx}/set_active',
                              'i',
                              '1')
        else:
            self.osc.send_osc(f'/{carla_idx}/set_program',
                              'i',
                              preset.idx)
        btn.setPalette(self.palette_active)
        if self.nt:
            btn.setStyleSheet('background-color:#212121;')

    # Event
    def split_key_box_chgd(self):
        """Event for Spinbox change for split key index"""
        self.split_key_idx = self.split_key_box.value()
        self.send_split_key_osc(self.split_state)

    # Event
    def octave_box_chgd(self):
        """Event for Spinbox change for octave index"""
        octave_val = self.octave_box.value()
        if self.split_state is True:
            patch_idx = self.octave_hi_idx
            self.octave_hi = octave_val
        else:
            patch_idx = self.octave_lo_idx
            self.octave_lo = octave_val
        self.osc.send_osc(f'/{patch_idx}/set_parameter_value',
                          'if',
                          f'0 {octave_val}')

    # Method
    def add_btns_to_layout(self, self_btns, btn_list, btn_func, layout):
        """
        Add list of buttons (with click events) to a grid layout.

        :param self_btns:
        :param btn_list:
        :param btn_func:
        :param layout:
        :return:
        """
        x = 0
        y = 1
        for preset in btn_list:
            btn = TouchButton(preset.parent_name + '\n' + preset.name)
            btn.setSizePolicy(self.policy, self.policy)
            btn.clicked.connect(partial(btn_func,
                                        btn,
                                        preset))
            layout.addWidget(btn, y, x)
            self_btns.append(btn)
            x += 1
            if x >= self.cols:
                x = 0
                y += 1

    # Method
    def send_split_key_osc(self, enabled):
        """
        Send osc messages to key-split patches
        :param enabled: whether to enable or disable key splitting
        :return:
        """
        if enabled:
            split_key_idx_lo = self.split_key_idx
            split_key_idx_hi = self.split_key_idx + 1
        else:
            split_key_idx_lo = 127
            split_key_idx_hi = 127

        self.osc.send_osc(f'/{self.split_lo_idx}/set_parameter_value',
                          'if',
                          f'3 {split_key_idx_lo}')
        self.osc.send_osc(f'/{self.split_hi_idx}/set_parameter_value',
                          'if',
                          f'2 {split_key_idx_hi}')

    # Method
    def deselect_all_grid(self, btns, offset=0):
        # deactivate all split patches
        for x in range(len(btns)):
            btns[x].setPalette(self.palette)
            if self.nt:
                btns[x].setStyleSheet('background-color:#414141;')
        for x in self.patches:
            idx = x.carla_idx + offset
            self.osc.send_osc(f'/{idx}/set_active', 'i', '0')