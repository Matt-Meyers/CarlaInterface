"""Drum kits edited from main.py. Loop files are not part of this list."""

from pathlib import Path


class DrumKit:
    """One sfizz slot. The keyboard must not reach it (channel filter in Carla)."""

    def __init__(self, name, carla_idx):
        self.name = name
        self.carla_idx = carla_idx


class Drums:
    """Kits shown on the Drums tab, plus the folder that holds loop files.

    rows is the kit grid only. The category / file strip is always an extra
    row under that grid. Kits past cols * rows are not shown.
    """

    def __init__(self, midi_dir, rows=1):
        self.midi_dir = Path(midi_dir)
        self.rows = max(0, int(rows))
        self.kits = []

    def add(self, name, carla_idx):
        self.kits.append(DrumKit(name, carla_idx))
