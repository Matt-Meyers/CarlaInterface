class Patch:
    """
    A single plugin in the Carla rack. If the plugin supports presets, append
    more than one preset. Otherwise, just append 1.
    """

    class Preset:
        """A single preset belonging to a plugin."""

        def __init__(self, parent, name, category, idx):
            self.name = name
            self.category = category
            self.idx = idx
            self.carla_idx = parent.carla_idx
            self.parent_name = parent.name
            self.preset_over_midi = parent.preset_over_midi

    def __init__(self, name, carla_idx, preset_over_midi=False):
        self.name = name
        self.presets = []
        self.carla_idx = carla_idx
        self.i = 0  # next sequential preset index for add()
        # True: MIDI program change instead of Carla /set_program (Pigments).
        self.preset_over_midi = preset_over_midi

    def add(self, preset, category, idx=None):
        """
        Append a Preset to this patch. Indexes are assigned sequentially unless
        otherwise specified.
        """
        if idx is None:
            idx = self.i
            self.i += 1
        self.presets.append(self.Preset(self, preset, category, idx))
