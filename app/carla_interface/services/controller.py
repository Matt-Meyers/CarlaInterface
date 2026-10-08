from PyQt6.QtCore import QTimer


class PatchController:
    """Preset selection, split, and octave — talks to Carla OSC and MIDI."""

    # Pigments needs a short gap after set_active before a MIDI program change.
    MIDI_PC_DELAY_MS = 250
    MIDI_RESTORE_DELAY_MS = 100

    def __init__(self, patches, config, osc, midi):
        self.patches = patches
        self.config = config
        self.osc = osc
        self.midi = midi
        self.split_enabled = False
        self.split_key_idx = config.split_key_idx
        self.octave_lo = 0
        self.octave_hi = 0
        self.curr_main_carla_idx = 0
        # Bumped to ignore QTimer callbacks from a previous MIDI program change.
        self._midi_seq = 0

    @property
    def octave_value(self):
        return self.octave_hi if self.split_enabled else self.octave_lo

    def select_main(self, preset):
        self.deactivate_bank(0)
        self.osc.set_active(preset.carla_idx, True)
        self.curr_main_carla_idx = preset.carla_idx
        self._apply_preset(preset, preset.carla_idx, for_split=False)

    def select_split(self, preset):
        # Split instruments are a second copy of the rack (see split_start_idx).
        carla_idx = preset.carla_idx + self.config.split_start_idx
        self.deactivate_bank(self.config.split_start_idx)
        self.osc.set_active(carla_idx, True)
        self._apply_preset(preset, carla_idx, for_split=True)

    def set_split_enabled(self, enabled):
        self._midi_seq += 1  # cancel in-flight MIDI PC / restore timeouts
        self.split_enabled = enabled
        self._apply_split_key()
        if not enabled:
            self.deactivate_bank(self.config.split_start_idx)

    def set_split_key(self, midi_note):
        self.split_key_idx = midi_note
        self._apply_split_key()

    def set_octave(self, value):
        if self.split_enabled:
            self.octave_hi = value
            plugin_idx = self.config.octave_hi_idx
        else:
            self.octave_lo = value
            plugin_idx = self.config.octave_lo_idx
        self.osc.set_parameter(plugin_idx, 0, value)  # param 0 = Octaves

    def deactivate_bank(self, offset=0):
        for patch in self.patches:
            self.osc.set_active(patch.carla_idx + offset, False)

    def _apply_preset(self, preset, carla_idx, for_split):
        self._midi_seq += 1
        seq = self._midi_seq
        if not preset.preset_over_midi:
            self.osc.set_program(carla_idx, preset.idx)
            return
        if for_split:
            # Mute the main instance so the PC hits only the split plugin.
            self.osc.set_active(self.curr_main_carla_idx, False)

            def send_pc():
                if seq != self._midi_seq:
                    return
                self.midi.send_program_change(preset.idx)

                def restore_main():
                    if seq != self._midi_seq:
                        return
                    self.osc.set_active(self.curr_main_carla_idx, True)

                QTimer.singleShot(self.MIDI_RESTORE_DELAY_MS, restore_main)

            QTimer.singleShot(self.MIDI_PC_DELAY_MS, send_pc)
        else:
            QTimer.singleShot(
                self.MIDI_PC_DELAY_MS,
                lambda: self._send_pc_if_current(seq, preset.idx),
            )

    def _send_pc_if_current(self, seq, program):
        if seq != self._midi_seq:
            return
        self.midi.send_program_change(program)

    def _apply_split_key(self):
        # Carla MIDI Key-Range Filter: param 3 = high note (low plugin),
        # param 2 = low note (high plugin). 127/127 effectively disables.
        if self.split_enabled:
            lo = self.split_key_idx
            hi = self.split_key_idx + 1
        else:
            lo = 127
            hi = 127
        self.osc.set_parameter(self.config.split_lo_idx, 3, lo)
        self.osc.set_parameter(self.config.split_hi_idx, 2, hi)
