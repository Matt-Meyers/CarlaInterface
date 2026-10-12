import time

from PyQt6.QtCore import QTimer

from carla_interface.services.midi import (
    format_duration,
    has_midi_takes,
    latest_midi_path,
    read_sidecar,
    unique_midi_path,
    voice_slug,
    write_sidecar,
)


def _voice_record(preset):
    if preset is None:
        return {
            'name': 'Untitled',
            'carla_idx': None,
            'preset_idx': None,
            'preset_over_midi': False,
        }
    return {
        'name': preset.name,
        'carla_idx': preset.carla_idx,
        'preset_idx': preset.idx,
        'preset_over_midi': bool(preset.preset_over_midi),
    }


class PatchController:
    """Preset selection, split, octave, MIDI record, and playback — OSC/MIDI I/O."""

    # Pigments needs a short gap after set_active before a MIDI program change.
    MIDI_PC_DELAY_MS = 125

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
        self.curr_main_preset = None
        self.curr_split_preset = None
        # Bumped to ignore QTimer callbacks from a previous MIDI program change.
        self._midi_seq = 0
        self._recording = False
        self._record_main = None
        self._record_split = None
        self._record_split_enabled = False
        self._record_started_at = None
        self._playing = False
        self._play_original = False
        self._play_restore_split = False
        self._play_restore_split_preset = None
        self._play_seq = 0

    @property
    def octave_value(self):
        return self.octave_hi if self.split_enabled else self.octave_lo

    @property
    def is_recording(self):
        return self._recording

    @property
    def is_playing(self):
        return self._playing

    def has_midi_takes(self):
        return has_midi_takes(self.config.midi_record_dir)

    def select_main(self, preset):
        self.deactivate_bank(0)
        self.osc.set_active(preset.carla_idx, True)
        self.curr_main_carla_idx = preset.carla_idx
        self.curr_main_preset = preset
        self._apply_preset(preset, preset.carla_idx, for_split=False)

    def select_split(self, preset):
        # Split instruments are a second copy of the rack (see split_start_idx).
        carla_idx = preset.carla_idx + self.config.split_start_idx
        self.deactivate_bank(self.config.split_start_idx)
        self.osc.set_active(carla_idx, True)
        self.curr_split_preset = preset
        self._apply_preset(preset, carla_idx, for_split=True)

    def start_recording(self):
        if self._recording:
            return False
        self._record_main = _voice_record(self.curr_main_preset)
        self._record_split = (
            _voice_record(self.curr_split_preset)
            if self.split_enabled
            else None
        )
        # Voice + names are frozen here so a mid-take patch change does not rename.
        self._record_split_enabled = self.split_enabled
        if not self.midi.start_recording():
            return False
        self._record_started_at = time.monotonic()
        self._recording = True
        return True

    def stop_recording(self):
        if not self._recording:
            return None
        elapsed = time.monotonic() - self._record_started_at
        self._recording = False
        main_name = self._record_main['name'] if self._record_main else 'Untitled'
        split_name = (
            self._record_split['name'] if self._record_split else 'Untitled'
        )
        stem = (
            voice_slug(
                main_name,
                split_name,
                self._record_split_enabled,
                self.config.midi_record_name_chars,
            )
            + '-'
            + format_duration(elapsed)
        )
        dest = unique_midi_path(self.config.midi_record_dir, stem)
        saved = self.midi.stop_recording(dest)
        if saved is not None:
            write_sidecar(
                saved,
                {
                    'version': 1,
                    'split_enabled': self._record_split_enabled,
                    'main': self._record_main,
                    'split': self._record_split,
                },
            )
        return saved

    def start_playback(self):
        if self._playing:
            return False
        path = latest_midi_path(self.config.midi_record_dir)
        if path is None:
            return False
        sidecar = read_sidecar(path)
        preset = None
        if sidecar is not None:
            preset = self._preset_from_sidecar(sidecar.get('main'))
        self._play_restore_split = self.split_enabled
        self._play_restore_split_preset = self.curr_split_preset
        if self.split_enabled:
            self.set_split_enabled(False)
        self._playing = True
        self._play_seq += 1
        seq = self._play_seq
        if preset is None:
            self._play_original = False
            if not self.midi.start_loop(path, 1):
                self.stop_playback()
                return False
            return True
        self._play_original = True
        self._activate_accompaniment(preset)
        self._set_accompaniment_routing(True)
        delay = self.MIDI_PC_DELAY_MS if preset.preset_over_midi else 0
        channel = self.config.midi_play_channel
        if delay:
            QTimer.singleShot(
                delay,
                lambda: self._start_loop_if_current(seq, path, channel),
            )
        elif not self.midi.start_loop(path, channel):
            self.stop_playback()
            return False
        return True

    def stop_playback(self):
        if not self._playing:
            return
        self._playing = False
        self._play_seq += 1
        self.midi.stop_loop()
        if self._play_original:
            self._set_accompaniment_routing(False)
            self.deactivate_bank(self.config.split_start_idx)
            self.osc.set_parameter(self.config.octave_hi_idx, 0, self.octave_hi)
        self._play_original = False
        if self._play_restore_split:
            self.set_split_enabled(True)
            if self._play_restore_split_preset is not None:
                self.select_split(self._play_restore_split_preset)
        else:
            self._apply_split_key()
        self._play_restore_split = False
        self._play_restore_split_preset = None

    def set_split_enabled(self, enabled):
        self._midi_seq += 1  # cancel in-flight MIDI program-change timeouts
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

    def _preset_from_sidecar(self, voice):
        if not isinstance(voice, dict):
            return None
        carla_idx = voice.get('carla_idx')
        preset_idx = voice.get('preset_idx')
        if carla_idx is None or preset_idx is None:
            return None
        for patch in self.patches:
            if patch.carla_idx != carla_idx:
                continue
            for preset in patch.presets:
                if preset.idx == preset_idx:
                    return preset
        return None

    def _activate_accompaniment(self, preset):
        # Use the split-bank copy; do not overwrite curr_split_preset.
        carla_idx = preset.carla_idx + self.config.split_start_idx
        self.deactivate_bank(self.config.split_start_idx)
        self.osc.set_active(carla_idx, True)
        self._apply_preset(preset, carla_idx, for_split=True)

    def _set_accompaniment_routing(self, active):
        # Drop keyboard ch 1 on the split filters so live notes stay on main.
        ch1 = 0 if active else 1
        self.osc.set_parameter(self.config.ch_filter_split_std_idx, 0, ch1)
        self.osc.set_parameter(self.config.ch_filter_split_pigments_idx, 0, ch1)
        if active:
            # Split-off parks HIGH at 127; open it so ch 16 reaches the split bank.
            self.osc.set_parameter(self.config.split_hi_idx, 2, 0)
            self.osc.set_parameter(self.config.octave_hi_idx, 0, 0)

    def _start_loop_if_current(self, seq, path, channel):
        if seq != self._play_seq or not self._playing:
            return
        if not self.midi.start_loop(path, channel):
            self.stop_playback()

    def _apply_preset(self, preset, carla_idx, for_split):
        self._midi_seq += 1
        seq = self._midi_seq
        if not preset.preset_over_midi:
            self.osc.set_program(carla_idx, preset.idx)
            return
        # Channels 2/3: midichanfilter in front of each Pigments (1 is keyboard).
        channel = (
            self.config.midi_pc_split_channel
            if for_split
            else self.config.midi_pc_main_channel
        )
        QTimer.singleShot(
            self.MIDI_PC_DELAY_MS,
            lambda: self._send_pc_if_current(seq, preset.idx, channel),
        )

    def _send_pc_if_current(self, seq, program, channel):
        if seq != self._midi_seq:
            return
        self.midi.send_program_change(program, channel)

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
