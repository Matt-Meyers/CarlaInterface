import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from carla_interface import (
    AppConfig,
    CarlaInterface,
    Patch,
    apply_config_args,
    parse_args,
    run_app,
)

if __name__ == '__main__':
    args = parse_args()
    categories = ['Piano', 'Keys', 'Synth-Keys', 'Pad']
    patches = []

    # Carla rack indexes and I/O. Split bank is main index + split_start_idx.
    # Pigments filters are so MIDI program changes are sent to the correct plugin.
    config = AppConfig(
        osc_port='22752',
        midi_port='Midi Through Port-0',
        midi_pc_main_channel=2,   # MAIN Pigments filter
        midi_pc_split_channel=3,  # SPLIT Pigments filter
        midi_play_channel=16,     # original-voice accompaniment
        midi_record_dir=Path.home() / 'midi',
        ch_filter_split_std_idx=22,
        ch_filter_split_pigments_idx=23,
        midi_record_name_chars=20,
        split_start_idx=12,   # duplicated instruments start here
        split_lo_idx=8,       # MIDI Key-Range Filter (low)
        split_hi_idx=9,       # MIDI Key-Range Filter (high)
        octave_lo_idx=10,     # MIDI Transpose (low / unsplit)
        octave_hi_idx=11,     # MIDI Transpose (high / split)
        split_key_idx=60,     # default split note (C4)
        cols=4,
        rows=2,
    )
    config = apply_config_args(config, args)

    # This is a single plugin/patch in Carla. Each '.add' stands for a preset.
    # Without supplying indexes, presets are assumed sequential.
    patch1 = Patch('Pianoteq 9', 0)   # Plugin is Pianoteq 9, at rack 0
    patch1.add('Bluethner Concert', 'Piano')    # first preset
    patch1.add('Bluethner Cinematic', 'Piano')   # second preset...
    patch1.add('NY Steinway Chamber', 'Piano')
    patch1.add('Bechstein Recording 2', 'Piano')
    patch1.add('Bechstein Cosmic', 'Piano')
    patch1.add('Bechstein Felt 2', 'Piano')
    patch1.add('Pianet T Cosmic', 'Keys')   # different category
    patch1.add('Pianet T Jazzy', 'Keys')
    patch1.add('Pianet N 80s Band', 'Keys')
    patch1.add('Pianet N Little Fuzzy', 'Keys')
    patch1.add('Electra Fatty', 'Keys')
    patch1.add('Electra RubberChorus', 'Keys')
    patch1.add('Bechstein Sombre', 'Piano')   # Prev cat to the end to avoid reordering
    patches.append(patch1)   # append to patch-list to send to CarlaInterface

    # If a plugin does not support presets or MIDI program changes (or you want
    # to chain each instance different FX), simply make several patches.
    # In these cases, just '.add' once to each patch.
    patch2 = Patch('Zebralette', 1)   # rack 1
    patch2.add('HS Grand Entrance', 'Synth-Keys')   # just one append
    patch3 = Patch('Zebralette', 2)   # rack 2
    patch3.add('HS Pacific Swell', 'Pad')   # just one append
    patches.append(patch2)
    patches.append(patch3)

    patch4 = Patch('Podolski', 3)
    patch4.add('HUC Waterworld Keys', 'Synth-Keys')
    patch5 = Patch('Podolski', 4)
    patch5.add('SM Fullpad', 'Pad')
    patches.append(patch4)
    patches.append(patch5)

    # This plugin is using MIDI program changes for preset selection.
    # It will look the same as a patch that uses presets, except for a boolean.
    patch6 = Patch('Pigments', 5, True)    # true for preset_over_midi
    patch6.add('Sweet DX', 'Synth-Keys')
    patch6.add('Atmo Lead', 'Synth-Keys')   # TODO add category for lead?
    patch6.add('DX Keys', 'Synth-Keys')
    patch6.add('Malibu Express', 'Synth-Keys')
    patch6.add('Rompler', 'Synth-Keys')
    patch6.add('Reverse Box', 'Synth-Keys')
    patch6.add('Journeys 1983', 'Pad')
    patch6.add('Choral Grains', 'Pad')
    patch6.add('Borderline Forrest', 'Pad')
    patch6.add('Star Jumping', 'Pad')
    patch6.add('Smoothly', 'Pad')
    patch6.add('Evolution', 'Pad')
    patch6.add('Winnie', 'Keys')

    patches.append(patch6)

    app = QApplication(['Carla Interface'])
    carla_interface = CarlaInterface(
        patches, categories, config, windowed=args.windowed
    )
    carla_interface.show_app()
    sys.exit(run_app(app))
