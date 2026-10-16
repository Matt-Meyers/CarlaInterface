"""Take filenames, sidecar JSON, and listing of saved .mid files."""

import json
import re
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


# Stem ends with the duration baked in at save time, plus _N when the name collided.
_DURATION_RE = re.compile(r'(\d+)min(\d+)sec(?:_\d+)?$')


def list_midi_takes(directory):
    folder = Path(directory)
    if not folder.is_dir():
        return []
    return [path for path in folder.glob('*.mid') if path.name != _TEMP_NAME]


def takes_newest_first(directory):
    takes = list_midi_takes(directory)
    takes.sort(key=lambda path: path.name)
    takes.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return takes


def latest_midi_path(directory):
    takes = list_midi_takes(directory)
    if not takes:
        return None
    return max(takes, key=lambda path: path.stat().st_mtime)


def has_midi_takes(directory):
    return bool(list_midi_takes(directory))


def _voice_name(voice):
    if isinstance(voice, dict) and voice.get('name'):
        return voice['name']
    return 'Untitled'


def _duration_parts(path):
    match = _DURATION_RE.search(Path(path).stem)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), match.start()


def take_title(path):
    """Voice name from the sidecar, or the filename stem when it is missing."""
    path = Path(path)
    data = read_sidecar(path)
    if data is not None:
        main = _voice_name(data.get('main'))
        if data.get('split_enabled'):
            return f'{main} / {_voice_name(data.get("split"))}'
        return main
    parts = _duration_parts(path)
    if parts is None:
        return path.stem
    # Filenames use underscores; show them as words when no sidecar has the real name.
    title = path.stem[:parts[2]].rstrip('-_').replace('_', ' ')
    return title or path.stem


def take_detail(path):
    """Duration stored in the filename, as m:ss. Empty when the stem has none."""
    parts = _duration_parts(path)
    if parts is None:
        return ''
    minutes, seconds, _start = parts
    return f'{minutes}:{seconds:02d}'
