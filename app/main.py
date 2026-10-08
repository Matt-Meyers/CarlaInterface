import sys
from PyQt6.QtWidgets import QApplication
from gui import CarlaInterface
from structures import Patch

if __name__ == '__main__':
    categories = ['Piano', 'Keys', 'Synth-Keys', 'Pad']
    patches = []
    split_start_idx = 12

    # This is a single plugin/patch in Carla. Each '.add' stands for a preset.
    # Without supplying indexes, presets are assumed sequential.
    patch1 = Patch('Pianoteq 7', 0)   # Plugin is Pianoteq 7, at rack 0
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
    carla_interface = CarlaInterface(patches, categories, split_start_idx)
    carla_interface.showMaximized()    # TODO uncomment
    carla_interface.show()
    carla_interface.resize(800, 500)
    sys.exit(app.exec())
