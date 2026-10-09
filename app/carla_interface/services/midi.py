"""MIDI program changes via sendmidi, and SMF capture via arecordmidi.

Program changes are used for plugins that do not expose Carla presets
(e.g. Pigments). Recording uses the system `arecordmidi` binary (Linux).
Missing binaries no-op so a Windows host can still preview the UI.
"""

import re
import signal
import subprocess
from pathlib import Path

# arecordmidi -l: " 14:0    Midi Through                     Midi Through Port-0"
_PORT_LINE = re.compile(r'^\s*(\d+:\d+)\s+(.*)$')
_TEMP_NAME = '.carla_interface_recording.mid'
_STOP_WAIT_SEC = 8


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


def list_record_ports():
    """ALSA sequencer addresses for arecordmidi -p, excluding Midi Through."""
    try:
        result = subprocess.run(
            ['arecordmidi', '-l'],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    ports = []
    for line in result.stdout.splitlines():
        match = _PORT_LINE.match(line)
        if not match:
            continue
        addr, rest = match.group(1), match.group(2)
        if 'through' in rest.lower():
            continue
        ports.append(addr)
    return ports


class MidiService:
    def __init__(self, sendmidi_path, port_name, record_dir):
        self.sendmidi_path = Path(sendmidi_path)
        self.port_name = port_name
        self.record_dir = Path(record_dir)
        self._record_proc = None
        self._record_temp = None

    def send_program_change(self, program):
        try:
            subprocess.run(
                [
                    str(self.sendmidi_path),
                    'dev',
                    self.port_name,
                    'pc',
                    str(program),
                ],
                check=False,
            )
        except OSError:
            # sendmidi missing or not executable (e.g. Windows host).
            pass

    def start_recording(self):
        if self._record_proc is not None:
            return False
        ports = list_record_ports()
        if not ports:
            return False
        try:
            self.record_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        temp = self.record_dir / _TEMP_NAME
        try:
            self._record_proc = subprocess.Popen(
                ['arecordmidi', '-p', ','.join(ports), str(temp)],
            )
        except OSError:
            self._record_proc = None
            return False
        self._record_temp = temp
        return True

    def stop_recording(self, dest_path):
        proc = self._record_proc
        temp = self._record_temp
        self._record_proc = None
        self._record_temp = None
        if proc is None:
            return None
        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=_STOP_WAIT_SEC)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        except OSError:
            pass
        if temp is None or not temp.exists():
            return None
        dest = Path(dest_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp.replace(dest)
        except OSError:
            return None
        return dest
