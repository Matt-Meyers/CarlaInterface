"""MIDI program changes, SMF capture, and looped playback.

Program changes go to plugins that do not expose Carla presets (Pigments).
Takes, drum loops, and recording share one ALSA sequencer client
(`alsa-midi`) aimed at Midi Through, which is bridged into Carla. Main vs
split Pigments use different MIDI channels so midichanfilter can isolate
them. A take is remapped onto one channel (16 for original-voice). Recording
subscribes to hardware ports and skips Midi Through, so a loop is not
captured. If alsa-midi cannot open a sequencer, calls no-op and the UI
still previews.
"""

from carla_interface.services.midi.service import MidiService
from carla_interface.services.midi.smf import remap_smf_channel
from carla_interface.services.midi.takes import (
    format_duration,
    has_midi_takes,
    latest_midi_path,
    list_midi_takes,
    read_sidecar,
    sidecar_path,
    take_detail,
    take_title,
    takes_newest_first,
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
    'read_sidecar',
    'remap_smf_channel',
    'sidecar_path',
    'take_detail',
    'take_title',
    'takes_newest_first',
    'unique_midi_path',
    'voice_slug',
    'write_sidecar',
]
