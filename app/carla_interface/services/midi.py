"""MIDI program changes via ALSA, and SMF capture via arecordmidi.

Program changes are used for plugins that do not expose Carla presets
(e.g. Pigments). They go to an ALSA sequencer port (Midi Through) with
`aplaymidi` so JUCE/sendmidi never opens JACK. Recording uses
`arecordmidi`. Missing binaries no-op so a Windows host can still
preview the UI.
"""

import re
import signal
import subprocess
import tempfile
from pathlib import Path

# arecordmidi/aplaymidi -l: " 14:0    Midi Through                     Midi Through Port-0"
_PORT_LINE = re.compile(r'^\s*(\d+:\d+)\s+(.*)$')
_TEMP_NAME = '.carla_interface_recording.mid'
_STOP_WAIT_SEC = 8
_PLAY_TIMEOUT_SEC = 2


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


def _list_seq_ports(command):
    try:
        result = subprocess.run(
            [command, '-l'],
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
        ports.append((match.group(1), match.group(2).strip()))
    return ports


def list_record_ports():
    """ALSA sequencer addresses for arecordmidi -p, excluding Midi Through."""
    ports = []
    for addr, rest in _list_seq_ports('arecordmidi'):
        if 'through' in rest.lower():
            continue
        ports.append(addr)
    return ports


def resolve_play_port(port_name):
    """aplaymidi client:port whose listing contains port_name."""
    name = port_name.lower()
    ports = _list_seq_ports('aplaymidi')
    for addr, rest in ports:
        rest_l = rest.lower()
        if rest_l == name or rest_l.endswith(name):
            return addr
    for addr, rest in ports:
        if name in rest.lower():
            return addr
    return None


def _program_change_smf(program, channel=0):
    """One-event type-0 SMF: program change, then end-of-track."""
    program = max(0, min(127, int(program)))
    status = 0xC0 | (channel & 0x0F)
    track = bytes((0x00, status, program, 0x00, 0xFF, 0x2F, 0x00))
    header = b'MThd' + (6).to_bytes(4, 'big') + b'\x00\x00\x00\x01\x00\x60'
    return header + b'MTrk' + len(track).to_bytes(4, 'big') + track


class MidiService:
    def __init__(self, port_name, record_dir):
        self.port_name = port_name
        self.record_dir = Path(record_dir)
        self._play_addr = None
        self._record_proc = None
        self._record_temp = None

    def send_program_change(self, program):
        addr = self._play_addr or resolve_play_port(self.port_name)
        if addr is None:
            return
        self._play_addr = addr
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as tmp:
                tmp.write(_program_change_smf(program))
                path = tmp.name
            subprocess.run(
                ['aplaymidi', '-p', addr, path],
                check=False,
                timeout=_PLAY_TIMEOUT_SEC,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired):
            # aplaymidi missing (Windows preview) or a wedged sequencer.
            pass
        finally:
            if path is not None:
                Path(path).unlink(missing_ok=True)

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
