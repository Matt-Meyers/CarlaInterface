"""Take filenames, sidecar JSON, and listing of saved .mid files."""

import json
from pathlib import Path

_TEMP_NAME = '.carla_interface_recording.mid'
_SIDECAR_VERSION = 1


def voice_slug(main_name, split_name, split_enabled, max_chars):
    """First max_chars of the voice name(s); spaces become underscores."""

    def slug(name, n):
        return (name or 'Untitled').replace(' ', '_')[:n]

    if split_enabled:
        half = max(1, max_chars // 2)
        return f'{slug(main_name, half)}-{slug(split_name, half)}'
    return slug(main_name, max_chars)


def format_duration(seconds):
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    return f'{minutes}min{secs}sec'


def unique_midi_path(directory, stem):
    directory = Path(directory)
    candidate = directory / f'{stem}.mid'
    n = 2
    while candidate.exists():
        candidate = directory / f'{stem}_{n}.mid'
        n += 1
    return candidate


def sidecar_path(mid_path):
    return Path(mid_path).with_suffix('.json')


def write_sidecar(mid_path, payload):
    path = sidecar_path(mid_path)
    path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    return path


def read_sidecar(mid_path):
    path = sidecar_path(mid_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or data.get('version') != _SIDECAR_VERSION:
        return None
    return data


def list_midi_takes(directory):
    folder = Path(directory)
    if not folder.is_dir():
        return []
    return [path for path in folder.glob('*.mid') if path.name != _TEMP_NAME]


def latest_midi_path(directory):
    takes = list_midi_takes(directory)
    if not takes:
        return None
    return max(takes, key=lambda path: path.stat().st_mtime)


def has_midi_takes(directory):
    return bool(list_midi_takes(directory))
