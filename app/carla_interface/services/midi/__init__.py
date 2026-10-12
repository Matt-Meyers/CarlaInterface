"""MIDI program changes via ALSA, SMF capture, and looped playback.

Program changes are used for plugins that do not expose Carla presets
(e.g. Pigments). They go to an ALSA sequencer port (Midi Through) with
`aplaymidi` so JUCE/sendmidi never opens JACK. Main vs split Pigments
use different MIDI channels so Carla midichanfilter can isolate them.
Playback remaps a take onto a dedicated channel (16 for original-voice).
Recording uses `arecordmidi` and skips Through, so a loop is not captured.
Missing binaries no-op so a Windows host can still preview the UI.
"""

from carla_interface.services.midi.ports import list_record_ports, resolve_play_port
from carla_interface.services.midi.service import MidiService
from carla_interface.services.midi.smf import remap_smf_channel
from carla_interface.services.midi.takes import (
    format_duration,
    has_midi_takes,
    latest_midi_path,
    list_midi_takes,
    read_sidecar,
    sidecar_path,
    unique_midi_path,
    voice_slug,
    write_sidecar,
)

__all__ = [
    'MidiService',
    'format_duration',
    'has_midi_takes',
    'latest_midi_path',
    'list_midi_takes',
    'list_record_ports',
    'read_sidecar',
    'remap_smf_channel',
    'resolve_play_port',
    'sidecar_path',
    'unique_midi_path',
    'voice_slug',
    'write_sidecar',
]
