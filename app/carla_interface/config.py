from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:
    """Rack indexes and I/O settings. Construct this in main.py."""

    assets_dir: Path
    osc_host: str = 'localhost'
    osc_port: str = '22752'
    midi_port: str = 'Midi Through Port-0'
    split_start_idx: int = 12
    split_lo_idx: int = 8
    split_hi_idx: int = 9
    octave_lo_idx: int = 10
    octave_hi_idx: int = 11
    split_key_idx: int = 60
    cols: int = 4

    @property
    def sendmidi_path(self) -> Path:
        return self.assets_dir / 'sendmidi'

    @property
    def stylesheet_path(self) -> Path:
        return self.assets_dir / 'stylesheet.css'

    @property
    def logo_path(self) -> Path:
        return self.assets_dir / 'logo.png'
