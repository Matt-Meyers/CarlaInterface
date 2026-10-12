"""MIDI program changes via ALSA, SMF capture, and looped playback.

Program changes are used for plugins that do not expose Carla presets
(e.g. Pigments). They go to an ALSA sequencer port (Midi Through) with
`aplaymidi` so JUCE/sendmidi never opens JACK. Main vs split Pigments
use different MIDI channels so Carla midichanfilter can isolate them.
Playback remaps a take onto a dedicated channel (16 for original-voice).
Recording uses `arecordmidi` and skips Through, so a loop is not captured.
Missing binaries no-op so a Windows host can still preview the UI.
"""

import json
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QProcess

# arecordmidi/aplaymidi -l: " 14:0    Midi Through                     Midi Through Port-0"
_PORT_LINE = re.compile(r'^\s*(\d+:\d+)\s+(.*)$')
_TEMP_NAME = '.carla_interface_recording.mid'
_STOP_WAIT_SEC = 8
_PLAY_TIMEOUT_SEC = 2
_LOOP_FAIL_SEC = 0.15
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


def _write_vlq(value):
    value = max(0, int(value))
    chunks = [value & 0x7F]
    value >>= 7
    while value:
        chunks.append(0x80 | (value & 0x7F))
        value >>= 7
    chunks.reverse()
    return bytes(chunks)


def _read_vlq(data, index):
    value = 0
    while index < len(data):
        byte = data[index]
        index += 1
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, index
    raise ValueError('truncated VLQ')


def _voice_data_len(status):
    high = status & 0xF0
    if high in (0xC0, 0xD0):
        return 1
    return 2


def _remap_track(body, channel):
    out = bytearray()
    index = 0
    running = None
    while index < len(body):
        delta, index = _read_vlq(body, index)
        out += _write_vlq(delta)
        if index >= len(body):
            raise ValueError('truncated track event')
        first = body[index]
        if first < 0x80:
            if running is None:
                raise ValueError('running status with no prior status')
            status = running
        else:
            index += 1
            status = first
            if status < 0xF0:
                running = status
            else:
                running = None
        if status < 0xF0:
            count = _voice_data_len(status)
            if index + count > len(body):
                raise ValueError('truncated voice message')
            data = body[index:index + count]
            index += count
            out.append((status & 0xF0) | channel)
            out += data
            continue
        if status == 0xFF:
            if index >= len(body):
                raise ValueError('truncated meta event')
            meta = body[index]
            index += 1
            length, index = _read_vlq(body, index)
            if index + length > len(body):
                raise ValueError('truncated meta data')
            out.append(0xFF)
            out.append(meta)
            out += _write_vlq(length)
            out += body[index:index + length]
            index += length
            continue
        if status in (0xF0, 0xF7):
            length, index = _read_vlq(body, index)
            if index + length > len(body):
                raise ValueError('truncated sysex')
            out.append(status)
            out += _write_vlq(length)
            out += body[index:index + length]
            index += length
            continue
        out.append(status)
    return bytes(out)


def remap_smf_channel(smf, channel):
    """Rewrite voice-message channels. channel is 0-based. Copy if not SMF."""
    channel = max(0, min(15, int(channel)))
    if len(smf) < 14 or smf[:4] != b'MThd':
        raise ValueError('not a MIDI file')
    header_len = int.from_bytes(smf[4:8], 'big')
    index = 8 + header_len
    chunks = [smf[:index]]
    while index + 8 <= len(smf):
        tag = smf[index:index + 4]
        length = int.from_bytes(smf[index + 4:index + 8], 'big')
        start = index + 8
        end = start + length
        if end > len(smf):
            raise ValueError('truncated MIDI chunk')
        body = smf[start:end]
        index = end
        if tag == b'MTrk':
            body = _remap_track(body, channel)
        chunks.append(tag + len(body).to_bytes(4, 'big') + body)
    return b''.join(chunks)


def _program_change_smf(program, channel=0):
    """One-event type-0 SMF: program change, then end-of-track.

    channel is 0-based (0 = MIDI channel 1).
    """
    program = max(0, min(127, int(program)))
    status = 0xC0 | (channel & 0x0F)
    track = bytes((0x00, status, program, 0x00, 0xFF, 0x2F, 0x00))
    header = b'MThd' + (6).to_bytes(4, 'big') + b'\x00\x00\x00\x01\x00\x60'
    return header + b'MTrk' + len(track).to_bytes(4, 'big') + track


def _all_notes_off_smf(channels):
    """CC 123 on each 1-based channel, then end-of-track."""
    events = bytearray()
    for channel in channels:
        status = 0xB0 | ((max(1, min(16, int(channel))) - 1) & 0x0F)
        events += bytes((0x00, status, 0x7B, 0x00))
    events += bytes((0x00, 0xFF, 0x2F, 0x00))
    header = b'MThd' + (6).to_bytes(4, 'big') + b'\x00\x00\x00\x01\x00\x60'
    return header + b'MTrk' + len(events).to_bytes(4, 'big') + bytes(events)


class MidiService:
    def __init__(self, port_name, record_dir):
        self.port_name = port_name
        self.record_dir = Path(record_dir)
        self._play_addr = None
        self._record_proc = None
        self._record_temp = None
        self._looping = False
        self._loop_file = None
        self._loop_started_at = 0
        self._loop_proc = QProcess()
        self._loop_proc.setStandardOutputFile(QProcess.nullDevice())
        self._loop_proc.setStandardErrorFile(QProcess.nullDevice())
        self._loop_proc.finished.connect(self._on_loop_finished)

    def send_program_change(self, program, channel=1):
        # channel is 1-based (Carla midichanfilter / keyboard = 1).
        addr = self._play_addr or resolve_play_port(self.port_name)
        if addr is None:
            return
        self._play_addr = addr
        path = None
        smf_channel = max(1, min(16, int(channel))) - 1
        try:
            with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as tmp:
                tmp.write(_program_change_smf(program, smf_channel))
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

    def start_loop(self, midi_path, channel):
        """Loop a take on 1-based channel. Remaps voice messages first."""
        self.stop_loop(notes_off=False)
        addr = self._play_addr or resolve_play_port(self.port_name)
        if addr is None:
            return False
        self._play_addr = addr
        src = Path(midi_path)
        try:
            remapped = remap_smf_channel(
                src.read_bytes(),
                max(1, min(16, int(channel))) - 1,
            )
        except (OSError, ValueError):
            return False
        try:
            with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as tmp:
                tmp.write(remapped)
                self._loop_file = Path(tmp.name)
        except OSError:
            self._loop_file = None
            return False
        self._looping = True
        if not self._launch_loop():
            self.stop_loop(notes_off=False)
            return False
        return True

    def stop_loop(self, notes_off=True):
        self._looping = False
        if self._loop_proc.state() != QProcess.ProcessState.NotRunning:
            self._loop_proc.kill()
            self._loop_proc.waitForFinished(2000)
        if self._loop_file is not None:
            self._loop_file.unlink(missing_ok=True)
            self._loop_file = None
        if notes_off:
            self.send_all_notes_off((1, 16))

    def send_all_notes_off(self, channels=(1, 16)):
        addr = self._play_addr or resolve_play_port(self.port_name)
        if addr is None:
            return
        self._play_addr = addr
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as tmp:
                tmp.write(_all_notes_off_smf(channels))
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
            pass
        finally:
            if path is not None:
                Path(path).unlink(missing_ok=True)

    def _launch_loop(self):
        if self._loop_file is None or self._play_addr is None:
            return False
        self._loop_started_at = time.monotonic()
        self._loop_proc.start(
            'aplaymidi',
            ['-p', self._play_addr, str(self._loop_file)],
        )
        return self._loop_proc.waitForStarted(1500)

    def _on_loop_finished(self, _code=0, _status=QProcess.ExitStatus.NormalExit):
        if not self._looping:
            return
        # Missing aplaymidi (Windows preview) exits immediately — do not spin.
        if time.monotonic() - self._loop_started_at < _LOOP_FAIL_SEC:
            self._looping = False
            return
        if not self._launch_loop():
            self._looping = False
