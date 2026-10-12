"""ALSA record/play via arecordmidi and aplaymidi (QProcess for loops)."""

import signal
import subprocess
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QProcess

from carla_interface.services.midi.ports import list_record_ports, resolve_play_port
from carla_interface.services.midi.smf import (
    _all_notes_off_smf,
    _program_change_smf,
    remap_smf_channel,
)
from carla_interface.services.midi.takes import _TEMP_NAME

_STOP_WAIT_SEC = 8
_PLAY_TIMEOUT_SEC = 2
_LOOP_FAIL_SEC = 0.15


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
        self._async_plays = []
        self._loop_proc = self._new_loop_proc()

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
        if self._loop_proc.state() != QProcess.ProcessState.NotRunning:
            self._retire_loop_proc()
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
        if self._loop_file is not None:
            # Linux keeps the open fd; unlinking must not wait on aplaymidi.
            self._loop_file.unlink(missing_ok=True)
            self._loop_file = None
        if notes_off:
            self.send_all_notes_off((1, 16))

    def send_all_notes_off(self, channels=(1, 16)):
        self._play_smf_async(_all_notes_off_smf(channels))

    def _play_smf_async(self, smf):
        addr = self._play_addr or resolve_play_port(self.port_name)
        if addr is None:
            return
        self._play_addr = addr
        try:
            with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as tmp:
                tmp.write(smf)
                path = tmp.name
        except OSError:
            return
        proc = QProcess()
        proc.setStandardOutputFile(QProcess.nullDevice())
        proc.setStandardErrorFile(QProcess.nullDevice())
        proc.finished.connect(lambda *_: self._finish_async_play(proc, path))
        self._async_plays.append(proc)
        proc.start('aplaymidi', ['-p', addr, path])

    def _finish_async_play(self, proc, path):
        Path(path).unlink(missing_ok=True)
        if proc in self._async_plays:
            self._async_plays.remove(proc)
        proc.deleteLater()

    def _new_loop_proc(self):
        proc = QProcess()
        proc.setStandardOutputFile(QProcess.nullDevice())
        proc.setStandardErrorFile(QProcess.nullDevice())
        proc.finished.connect(self._on_loop_finished)
        return proc

    def _retire_loop_proc(self):
        old = self._loop_proc
        try:
            old.finished.disconnect(self._on_loop_finished)
        except TypeError:
            pass
        if old.state() != QProcess.ProcessState.NotRunning:
            old.kill()
        old.finished.connect(old.deleteLater)
        self._loop_proc = self._new_loop_proc()

    def _launch_loop(self):
        if self._loop_file is None or self._play_addr is None:
            return False
        self._loop_started_at = time.monotonic()
        self._loop_proc.start(
            'aplaymidi',
            ['-p', self._play_addr, str(self._loop_file)],
        )
        return self._loop_proc.state() != QProcess.ProcessState.NotRunning

    def _on_loop_finished(self, _code=0, _status=QProcess.ExitStatus.NormalExit):
        if not self._looping:
            return
        # Missing aplaymidi (Windows preview) exits immediately — do not spin.
        if time.monotonic() - self._loop_started_at < _LOOP_FAIL_SEC:
            self._looping = False
            return
        if not self._launch_loop():
            self._looping = False
