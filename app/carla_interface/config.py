from dataclasses import dataclass
from pathlib import Path

# Bundled CSS and icons live next to the package.
_ASSETS_DIR = Path(__file__).resolve().parent.parent / 'assets'


@dataclass
class AppConfig:
    """Rack indexes and I/O settings. Construct this in main.py."""

    osc_host: str = 'localhost'
    osc_port: str = '22752'                 # Carla OSC UDP port
    midi_port: str = 'Midi Through Port-0'  # ALSA sequencer port (aplaymidi)
    # 1-based. Channel 1 is the keyboard; 16 is reserved for playback.
    midi_pc_main_channel: int = 2           # MAIN Pigments midichanfilter
    midi_pc_split_channel: int = 3          # SPLIT Pigments midichanfilter
    midi_record_dir: Path = Path.home() / 'midi'  # arecordmidi save folder
    midi_record_name_chars: int = 20        # voice slug length in .mid names
    split_start_idx: int = 12               # duplicate rack starts here
    split_lo_idx: int = 8                   # Key-Range Filter (below split)
    split_hi_idx: int = 9                   # Key-Range Filter (above split)
    octave_lo_idx: int = 10                 # Transpose, low / unsplit
    octave_hi_idx: int = 11                 # Transpose, high / split
    split_key_idx: int = 60                 # default split note (C4)
    cols: int = 4                           # preset button columns
    rows: int = 2                           # preset button rows

    @property
    def assets_dir(self) -> Path:
        return _ASSETS_DIR

    @property
    def stylesheet_path(self) -> Path:
        return self.assets_dir / 'stylesheet.css'

    @property
    def logo_path(self) -> Path:
        return self.assets_dir / 'logo.png'
