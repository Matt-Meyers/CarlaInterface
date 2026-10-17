import time
from pathlib import Path

from PyQt6.QtCore import QTimer

from carla_interface.services.midi import (
    format_duration,
    has_midi_takes,
    latest_midi_path,
    read_sidecar,
    take_detail,
    take_title,
    takes_newest_first,
    unique_midi_path,
    voice_slug,
    write_sidecar,
)
from carla_interface.services.midi.takes import _TEMP_NAME


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
    """Preset selection, split, octave, drums, MIDI record, and playback."""

    # Pigments needs a short gap after set_active before a MIDI program change.
    MIDI_PC_DELAY_MS = 125

    def __init__(self, patches, config, osc, midi, drums=None):
        self.patches = patches
        self.config = config
        self.osc = osc
        self.midi = midi
        self.drums = drums
        self.split_enabled = False
        self.split_key_idx = config.split_key_idx
        self.octave_lo = 0
        self.octave_hi = 0
        self.curr_main_carla_idx = 0
        self.curr_main_preset = None
        self.curr_split_preset = None
        self.curr_kit = None
        self._drum_path = None
        self._drums_playing = False
        self._drums_link = False
        # True when this take playback started the drum queue in phase.
        self._pair_active = False
        self._record_drums = None
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
        # None: Play resolves the newest file at press time.
        self._pinned_take = None

    @property
    def octave_value(self):
        return self.octave_hi if self.split_enabled else self.octave_lo

    @property
    def is_recording(self):
        return self._recording

    @property
    def is_playing(self):
        return self._playing

    @property
    def drums_playing(self):
        return self._drums_playing

    @property
    def drums_link(self):
        return self._drums_link

    @property
    def drums_files_locked(self):
        # The loop steppers stay put while a linked take is driving them.
        return self._pair_active

    @property
    def drum_path(self):
        return self._drum_path

    def has_midi_takes(self):
        return has_midi_takes(self.config.midi_record_dir)

    def list_playback_takes(self):
        """Newest-first (path, title, detail) for the take browser."""
        return [
            (path, take_title(path), take_detail(path))
            for path in takes_newest_first(self.config.midi_record_dir)
        ]

    def pinned_take_path(self):
        """Pinned file, or None when Play should use the newest take."""
        pin = self._pinned_take
        if pin is None:
            return None
        pin = Path(pin)
        if pin.is_file():
            return pin
        self._pinned_take = None
        return None

    def resolve_playback_path(self):
        pin = self.pinned_take_path()
        if pin is not None:
            return pin
        return latest_midi_path(self.config.midi_record_dir)

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

    def select_kit(self, kit):
        # Kits are outside both patch banks, so a piano change does not clear them.
        if self.drums is None:
            return
        for other in self.drums.kits:
            self.osc.set_active(other.carla_idx, False)
        self.osc.set_active(kit.carla_idx, True)
        self.curr_kit = kit

    def set_drums_link(self, enabled):
        # Applies on the next header Play. A take already running stays as it is.
        self._drums_link = bool(enabled)

    def start_drums(self, path):
        if self.drums is None or path is None:
            return False
        if not self.midi.start_drums(path, self.config.midi_drum_channel):
            return False
        self._drum_path = Path(path)
        self._drums_playing = True
        self._pair_active = False
        return True

    def stop_drums(self):
        self.midi.stop_drums()
        self._drums_playing = False
        self._pair_active = False

    def set_drum_file(self, path):
        if path is None:
            return
        path = Path(path)
        self._drum_path = path
        if self._drums_playing and not self._pair_active:
            if not self.midi.start_drums(path, self.config.midi_drum_channel):
                self._drums_playing = False

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
        # Phase is the drum queue tick at this moment, not the first note.
        self._record_drums = self._capture_drum_stamp()
        self._recording = True
        return True

    def stop_recording(self):
        if not self._recording:
            return None
        wall = time.monotonic() - self._record_started_at
        stamp = self._record_drums
        self._recording = False
        self._record_drums = None
        main_name = self._record_main['name'] if self._record_main else 'Untitled'
        split_name = (
            self._record_split['name'] if self._record_split else 'Untitled'
        )
        pad = stamp['loop_ticks'] if stamp else None
        temp = self.config.midi_record_dir / _TEMP_NAME
        saved = self.midi.stop_recording(temp, pad_loop_ticks=pad)
        if saved is None:
            return None
        # A take recorded over drums is named for the padded loop, so the
        # file the browser shows is the length Link will actually repeat.
        elapsed = self.midi.last_record_seconds if stamp else wall
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
        try:
            saved.replace(dest)
        except OSError:
            return None
        payload = {
            'version': 1,
            'split_enabled': self._record_split_enabled,
            'main': self._record_main,
            'split': self._record_split,
        }
        if stamp:
            payload['drums'] = stamp
        write_sidecar(dest, payload)
        # The take just saved is the newest file Play should use.
        self._pinned_take = None
        return dest

    def select_playback_take(self, path):
        """Pin a take. None means newest. A running loop switches in place.

        Stopping first would restore Split and then playback would turn it
        off again, which flickers the rack while auditioning files.
        """
        previous = self.resolve_playback_path()
        if path is None:
            self._pinned_take = None
        else:
            path = Path(path)
            self._pinned_take = path if path.is_file() else None
        if not self._playing:
            return True
        resolved = self.resolve_playback_path()
        if resolved is None:
            self.stop_playback()
            return False
        if previous == resolved:
            return True
        preset = self._preset_for_take(resolved)
        if preset is None and self._play_original:
            self._release_accompaniment()
        return self._arm_loop(resolved, preset)

    def start_playback(self):
        if self._playing:
            return False
        path = self.resolve_playback_path()
        if path is None:
            return False
        preset = self._preset_for_take(path)
        self._play_restore_split = self.split_enabled
        self._play_restore_split_preset = self.curr_split_preset
        if self.split_enabled:
            self.set_split_enabled(False)
        self._playing = True
        return self._arm_loop(path, preset)

    def stop_playback(self):
        if not self._playing:
            return
        self._playing = False
        self._play_seq += 1
        self.midi.stop_loop()
        if self._pair_active:
            self.midi.stop_drums()
            self._pair_active = False
            self._drums_playing = False
        self._release_accompaniment()
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

    def close(self):
        if self.is_playing:
            self.stop_playback()
        if self.is_recording:
            self.stop_recording()
        self.midi.close()

    def _capture_drum_stamp(self):
        mark = self.midi.record_mark
        if not mark or self.drums is None or self._drum_path is None:
            return None
        try:
            rel = (
                Path(self._drum_path)
                .resolve()
                .relative_to(Path(self.drums.midi_dir).resolve())
                .as_posix()
            )
        except (OSError, ValueError):
            return None
        return {
            'file': rel,
            'bpm': mark['bpm'],
            'ppq': mark['ppq'],
            'phase_ticks': mark['phase_ticks'],
            'loop_ticks': mark['loop_ticks'],
            'kit': self.curr_kit.carla_idx if self.curr_kit is not None else None,
        }

    def _select_kit_by_index(self, carla_idx):
        if self.drums is None or carla_idx is None:
            return
        for kit in self.drums.kits:
            if kit.carla_idx == carla_idx:
                self.select_kit(kit)
                return

    def _pair_plan(self, take_path):
        """Stamped drum loop for this take, when Link is on and the file exists."""
        if not self._drums_link or self.drums is None:
            return None
        sidecar = read_sidecar(take_path)
        if not sidecar:
            return None
        stamp = sidecar.get('drums')
        if not isinstance(stamp, dict) or not stamp.get('file'):
            return None
        drum_path = Path(self.drums.midi_dir) / stamp['file']
        if not drum_path.is_file():
            return None
        return {
            'path': drum_path,
            'phase_ticks': int(stamp.get('phase_ticks') or 0),
            'bpm': stamp.get('bpm') or 120,
            'kit': stamp.get('kit'),
        }

    def _start_transport(self, path, channel, plan):
        if plan is None:
            if self._pair_active:
                self.midi.stop_drums()
                self._pair_active = False
                self._drums_playing = False
            return self.midi.start_loop(path, channel)
        if not self.midi.start_linked(
            path,
            channel,
            plan['path'],
            self.config.midi_drum_channel,
            plan['phase_ticks'],
            plan['bpm'],
        ):
            return False
        self._pair_active = True
        self._drums_playing = True
        self._drum_path = plan['path']
        self._select_kit_by_index(plan.get('kit'))
        return True

    def _preset_for_take(self, path):
        sidecar = read_sidecar(path)
        if sidecar is None:
            return None
        return self._preset_from_sidecar(sidecar.get('main'))

    def _arm_loop(self, path, preset):
        self._play_seq += 1
        seq = self._play_seq
        plan = self._pair_plan(path)
        if preset is None:
            self._play_original = False
            if not self._start_transport(path, 1, plan):
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
                lambda seq=seq, path=path, channel=channel, plan=plan: (
                    self._start_transport_if_current(seq, path, channel, plan)
                ),
            )
        elif not self._start_transport(path, channel, plan):
            self.stop_playback()
            return False
        return True

    def _release_accompaniment(self):
        if not self._play_original:
            return
        self._set_accompaniment_routing(False)
        self.deactivate_bank(self.config.split_start_idx)
        self.osc.set_parameter(self.config.octave_hi_idx, 0, self.octave_hi)
        self._play_original = False

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

    def _start_transport_if_current(self, seq, path, channel, plan):
        if seq != self._play_seq or not self._playing:
            return
        if not self._start_transport(path, channel, plan):
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
