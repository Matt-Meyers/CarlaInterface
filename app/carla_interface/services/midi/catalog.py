"""Drum-loop folders. One level of subdirectories, no ALSA."""

from pathlib import Path

_MIDI_SUFFIXES = {'.mid', '.midi'}


def scan_drum_catalog(root):
    """(category, [files]) for immediate subfolders that contain MIDI files.

    Files in the root and anything nested under a category are ignored.
    Names sort case-insensitively. An empty or missing root yields [].
    """
    root = Path(root)
    if not root.is_dir():
        return []
    catalog = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        files = [
            path for path in child.iterdir()
            if path.is_file() and path.suffix.lower() in _MIDI_SUFFIXES
        ]
        if not files:
            continue
        files.sort(key=lambda path: path.name.lower())
        catalog.append((child.name, files))
    catalog.sort(key=lambda item: item[0].lower())
    return catalog
