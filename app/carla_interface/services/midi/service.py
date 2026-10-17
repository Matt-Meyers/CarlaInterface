"""MIDI facade. The ALSA client lives on Engine's thread."""

from pathlib import Path

from carla_interface.services.midi.engine import Engine
from carla_interface.services.midi.pattern import pad_ticks, ticks_to_seconds
from carla_interface.services.midi.smf import write_smf


class MidiService:
    def __init__(self, port_name, record_dir):
        self.port_name = port_name
        self.record_dir = Path(record_dir)
        self.record_mark = None
        self.last_record_seconds = 0.0
        self._engine = Engine(port_name)

    def send_program_change(self, program, channel=1):
        self._engine.call('program', program, channel)

    def start_recording(self):
        self.record_mark = None
        result = self._engine.call('record_start')
        if not isinstance(result, dict):
            return False
        self.record_mark = result.get('mark')
        return True

    def stop_recording(self, dest_path, pad_loop_ticks=None):
        """Write the take. pad_loop_ticks stretches the end to a whole loop."""
        result = self._engine.call('record_stop')
        if not isinstance(result, dict):
            return None
        end_tick = int(result['end_tick'])
        if pad_loop_ticks:
            end_tick = pad_ticks(end_tick, pad_loop_ticks)
        bpm = result['bpm']
        ppq = result['ppq']
        self.last_record_seconds = ticks_to_seconds(end_tick, bpm, ppq)
        dest = Path(dest_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            write_smf(dest, result['events'], ppq, bpm, end_tick)
        except OSError:
            return None
        return dest

    def start_loop(self, midi_path, channel):
        """Loop a take on a 1-based channel. The file tempo is kept."""
        return bool(self._engine.call('play_take', str(midi_path), int(channel)))

    def stop_loop(self, notes_off=True):
        self._engine.call('stop_take', bool(notes_off))

    def start_drums(self, midi_path, channel, bpm=None):
        """Loop a drum file. A filename BPM overrides the file unless bpm is set."""
        return bool(self._engine.call(
            'play_drums', str(midi_path), int(channel), bpm
        ))

    def stop_drums(self, notes_off=True):
        self._engine.call('stop_drums', bool(notes_off))

    def start_linked(self, take_path, take_channel, drum_path, drum_channel,
                     phase_ticks, bpm):
        """Start the take and the drum loop on one drain, in phase."""
        return bool(self._engine.call(
            'play_linked',
            str(take_path),
            int(take_channel),
            str(drum_path),
            int(drum_channel),
            int(phase_ticks),
            bpm,
        ))

    def send_all_notes_off(self, channels=(1, 16)):
        self._engine.call('notes_off', tuple(channels))

    def close(self):
        self._engine.close()
