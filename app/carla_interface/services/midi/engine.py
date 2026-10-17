"""One ALSA sequencer client for program changes, takes, drums, and recording.

The client is used from a single thread. Each playback gets a new tick queue
so a stop can drop that queue instead of trying to pull events back out of
the kernel. A take and a drum loop use separate queues, so each keeps its
own tempo.

Sends and receives go through SequencerClientBase. SequencerClient waits
forever when the kernel buffer is full, and its event_input timeout is passed
to poll() in seconds while poll() expects milliseconds. Either stall keeps
this thread from closing the client, and the kernel then holds the sequencer
open across process exit.
"""

import errno
import queue
import threading

from carla_interface.services.midi.pattern import (
    events_in_range,
    horizon_ticks,
    load_pattern,
    ns_to_ticks,
    pair_patterns,
)

try:
    from alsa_midi import (
        ChannelPressureEvent,
        ControlChangeEvent,
        KeyPressureEvent,
        NoteOffEvent,
        NoteOnEvent,
        PitchBendEvent,
        PortCaps,
        ProgramChangeEvent,
        SequencerClient,
    )
    from alsa_midi.client import SequencerClientBase
    from alsa_midi.exceptions import ALSAError
    _ALSA = True
except (ImportError, OSError):
    _ALSA = False

_RECORD_PPQ = 960
_RECORD_BPM = 120.0
_POLL_SEC = 0.05
# A drum loop coming back in through a subscribed port must not crowd out
# playback and stop commands.
_CAPTURE_BATCH = 64


def _safe_bpm(bpm):
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        return _RECORD_BPM
    if bpm < 1:
        return _RECORD_BPM
    if bpm > 1000:
        return 1000.0
    return bpm


def _safe_ppq(ppq):
    try:
        ppq = int(ppq)
    except (TypeError, ValueError):
        return _RECORD_PPQ
    return max(1, min(0x7FFF, ppq))


def _port_label(info):
    client = info.client_name or ''
    return f'{client} {info.name}'.strip()


def _find_port(ports, port_name):
    name = (port_name or '').lower()
    if not name:
        return None
    labeled = [(info, _port_label(info).lower()) for info in ports]
    for info, label in labeled:
        if label == name or label.endswith(name):
            return info
    for info, label in labeled:
        if name in label:
            return info
    return None


def _ns(real_time):
    return int(real_time.seconds) * 1_000_000_000 + int(real_time.nanoseconds)


def _voice_event(status, data, tick):
    """ALSA event for one stored voice message. tick is absolute on the queue."""
    channel = status & 0x0F
    kind = status & 0xF0
    if not data:
        return None
    if kind == 0x80:
        velocity = data[1] if len(data) > 1 else 0
        return NoteOffEvent(data[0], channel, velocity, tick=tick)
    if kind == 0x90:
        velocity = data[1] if len(data) > 1 else 0
        return NoteOnEvent(data[0], channel, velocity, tick=tick)
    if kind == 0xA0:
        pressure = data[1] if len(data) > 1 else 0
        return KeyPressureEvent(data[0], channel, pressure, tick=tick)
    if kind == 0xB0:
        value = data[1] if len(data) > 1 else 0
        return ControlChangeEvent(channel, data[0], value, tick=tick)
    if kind == 0xC0:
        return ProgramChangeEvent(channel, data[0], tick=tick)
    if kind == 0xD0:
        return ChannelPressureEvent(channel, data[0], tick=tick)
    if kind == 0xE0 and len(data) > 1:
        raw = (data[0] & 0x7F) | ((data[1] & 0x7F) << 7)
        return PitchBendEvent(channel, raw - 8192, tick=tick)
    return None


def _capture_message(event, tick):
    """Store an incoming voice event, or None for sequencer bookkeeping."""
    channel = getattr(event, 'channel', None)
    if channel is None:
        return None
    channel &= 0x0F
    if isinstance(event, NoteOffEvent):
        return (tick, 0x80 | channel, bytes((event.note & 0x7F, event.velocity & 0x7F)))
    if isinstance(event, NoteOnEvent):
        return (tick, 0x90 | channel, bytes((event.note & 0x7F, event.velocity & 0x7F)))
    if isinstance(event, KeyPressureEvent):
        return (tick, 0xA0 | channel, bytes((event.note & 0x7F, event.velocity & 0x7F)))
    if isinstance(event, ControlChangeEvent):
        return (
            tick,
            0xB0 | channel,
            bytes((int(event.param) & 0x7F, int(event.value) & 0x7F)),
        )
    if isinstance(event, ProgramChangeEvent):
        return (tick, 0xC0 | channel, bytes((int(event.value) & 0x7F,)))
    if isinstance(event, ChannelPressureEvent):
        return (tick, 0xD0 | channel, bytes((int(event.value) & 0x7F,)))
    if isinstance(event, PitchBendEvent):
        raw = max(0, min(16383, int(event.value) + 8192))
        return (tick, 0xE0 | channel, bytes((raw & 0x7F, (raw >> 7) & 0x7F)))
    return None


class _Player:
    def __init__(self, alsa_queue, pattern, channel):
        self.queue = alsa_queue
        self.pattern = pattern
        self.channel = channel
        self.scheduled_until = 0


class Engine:
    """ALSA worker. available is False when the sequencer cannot be opened."""

    def __init__(self, port_name):
        self.port_name = port_name
        self.available = False
        self._client = None
        self._out = None
        self._in = None
        self._clock = None
        self._dest_ok = False
        self._input_count = 0
        self._take = None
        self._drums = None
        self._recording = False
        self._record_events = []
        self._record_origin = 0
        self._record_bpm = _RECORD_BPM
        self._record_ppq = _RECORD_PPQ
        self._record_mark = None
        self._cmds = queue.Queue()
        self._wake = threading.Event()
        self._running = False
        self._ready = threading.Event()
        if not _ALSA:
            self._ready.set()
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name='carla-midi', daemon=False
        )
        self._thread.start()
        self._ready.wait(timeout=3)

    def call(self, op, *args, timeout=3):
        if not self.available:
            return None
        box = queue.Queue(maxsize=1)
        self._cmds.put((op, args, box))
        self._wake.set()
        try:
            return box.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        if not self.available:
            return
        self.call('shutdown', timeout=2)
        self._thread.join(timeout=2)
        self.available = False

    def _run(self):
        try:
            try:
                self._open()
                self.available = self._client is not None
            except Exception:
                self.available = False
            self._ready.set()
            while self.available and self._running:
                try:
                    self._drain_commands()
                    if not self._running:
                        break
                    self._refill(self._take)
                    self._refill(self._drums)
                    self._drain()
                    if self._recording:
                        self._capture_pending()
                except Exception:
                    pass
                # Same wait while recording, so a stream of incoming notes
                # cannot postpone the next drum refill or a stop command.
                self._wake.wait(_POLL_SEC)
                self._wake.clear()
        finally:
            self._shutdown()

    def _drain_commands(self):
        while True:
            try:
                op, args, box = self._cmds.get_nowait()
            except queue.Empty:
                return
            try:
                result = getattr(self, f'_op_{op}')(*args)
            except Exception:
                result = False
            if box is not None:
                box.put(result)

    def _open(self):
        self._client = SequencerClient('CarlaInterface')
        self._out = self._client.create_port(
            'play',
            caps=PortCaps.READ | PortCaps.SUBS_READ,
        )
        # Real-time stamps for recording. Tick time on this queue is not the
        # drum clock; drum phase is read from the drum queue itself.
        self._clock = self._client.create_queue('clock')
        self._clock.set_tempo(bpm=_RECORD_BPM, ppq=_RECORD_PPQ)
        self._clock.start()
        self._drain()
        self._in = self._client.create_port(
            'record',
            caps=PortCaps.WRITE | PortCaps.SUBS_WRITE,
            timestamping=True,
            timestamp_real=True,
            timestamp_queue=self._clock,
        )
        self._connect()

    def _connect(self):
        outputs = self._client.list_ports(output=True, include_midi_through=True)
        dest = _find_port(outputs, self.port_name)
        self._dest_ok = False
        if dest is not None:
            try:
                self._client.subscribe_port(self._out, dest)
                self._dest_ok = True
            except Exception:
                self._dest_ok = False
        self._input_count = 0
        inputs = self._client.list_ports(input=True, include_midi_through=False)
        for info in inputs:
            if info.client_id == self._client.client_id:
                continue
            if 'through' in _port_label(info).lower():
                continue
            try:
                self._client.subscribe_port(info, self._in)
            except Exception:
                continue
            self._input_count += 1

    def _alsa_call(self, method, *args, **kwargs):
        """Non-blocking ALSA call. A full buffer is a miss, not a wait."""
        try:
            return method(self._client, *args, **kwargs)
        except ALSAError as err:
            if err.errnum != -errno.EAGAIN:
                return None
        except Exception:
            return None
        try:
            SequencerClientBase.drain_output(self._client)
            return method(self._client, *args, **kwargs)
        except Exception:
            return None

    def _drain(self):
        if self._client is None:
            return
        try:
            SequencerClientBase.drain_output(self._client)
        except Exception:
            return

    def _clock_ns(self):
        status = self._clock.get_status()
        return _ns(status.real_time)

    def _emit(self, player, start, end):
        batch = events_in_range(
            player.pattern.events, player.pattern.loop_ticks, start, end
        )
        for tick, status, data in batch:
            event = _voice_event(status, data, tick)
            if event is None:
                continue
            self._alsa_call(
                SequencerClientBase.event_output,
                event,
                queue=player.queue,
                port=self._out,
            )

    def _arm(self, pattern, channel):
        bpm = _safe_bpm(pattern.bpm)
        ppq = _safe_ppq(pattern.ppq)
        loop = max(1, int(pattern.loop_ticks))
        pattern = pattern.__class__(pattern.events, ppq, bpm, loop)
        alsa_queue = self._client.create_queue()
        alsa_queue.set_tempo(bpm=bpm, ppq=ppq)
        player = _Player(alsa_queue, pattern, channel)
        horizon = horizon_ticks(bpm, ppq)
        self._emit(player, 0, horizon)
        player.scheduled_until = horizon
        alsa_queue.start()
        return player

    def _refill(self, player):
        if player is None:
            return
        try:
            now = int(player.queue.get_status().tick_time)
        except Exception:
            return
        horizon = horizon_ticks(player.pattern.bpm, player.pattern.ppq)
        target = now + horizon
        start = max(player.scheduled_until, now)
        if target <= start:
            return
        self._emit(player, start, target)
        player.scheduled_until = target

    def _notes_off(self, channels):
        if self._out is None:
            return
        for channel in channels:
            event = ControlChangeEvent(int(channel) & 0x0F, 123, 0)
            self._alsa_call(
                SequencerClientBase.event_output_direct,
                event,
                port=self._out,
            )
        self._drain()

    def _drop(self, player, channels):
        if player is None:
            return
        try:
            player.queue.stop()
            self._drain()
        except Exception:
            pass
        try:
            player.queue.close()
        except Exception:
            pass
        if channels:
            self._notes_off(channels)

    def _stop_take(self, notes_off):
        # Channel 1 is the keyboard and 16 is accompaniment; either may be
        # holding notes from the take that just stopped.
        channels = {0, 15}
        if self._take is not None:
            channels.add(self._take.channel)
        self._drop(self._take, channels if notes_off else ())
        self._take = None

    def _stop_drums(self, notes_off):
        channel = self._drums.channel if self._drums is not None else None
        self._drop(self._drums, (channel,) if notes_off and channel is not None else ())
        self._drums = None

    def _channel(self, channel):
        return max(0, min(15, int(channel) - 1))

    def _op_play_take(self, path, channel):
        if not self._dest_ok:
            return False
        pattern = load_pattern(path, channel=self._channel(channel))
        # Drop the old queue and silence it before the new one starts.
        self._stop_take(True)
        self._take = self._arm(pattern, self._channel(channel))
        self._drain()
        return True

    def _op_stop_take(self, notes_off):
        self._stop_take(bool(notes_off))
        return True

    def _op_play_drums(self, path, channel, bpm):
        if not self._dest_ok:
            return False
        pattern = load_pattern(
            path,
            channel=self._channel(channel),
            bpm=bpm,
            use_filename_bpm=bpm is None,
            align_bars=True,
        )
        self._stop_drums(True)
        self._drums = self._arm(pattern, self._channel(channel))
        self._drain()
        return True

    def _op_stop_drums(self, notes_off):
        self._stop_drums(bool(notes_off))
        return True

    def _op_play_linked(self, take_path, take_channel, drum_path, drum_channel,
                        phase_ticks, bpm):
        if not self._dest_ok:
            return False
        take = load_pattern(take_path, channel=self._channel(take_channel))
        drums = load_pattern(
            drum_path,
            channel=self._channel(drum_channel),
            bpm=bpm,
            align_bars=True,
        )
        take, drums = pair_patterns(take, drums, phase_ticks)
        self._stop_take(True)
        self._stop_drums(True)
        self._take = self._arm(take, self._channel(take_channel))
        self._drums = self._arm(drums, self._channel(drum_channel))
        # One drain so both queue-start events leave together.
        self._drain()
        return True

    def _op_program(self, program, channel):
        if not self._dest_ok or self._out is None:
            return False
        event = ProgramChangeEvent(
            self._channel(channel),
            max(0, min(127, int(program))),
        )
        self._alsa_call(
            SequencerClientBase.event_output_direct, event, port=self._out
        )
        return True

    def _op_notes_off(self, channels):
        self._notes_off(self._channel(channel) for channel in channels)
        return True

    def _op_record_start(self):
        if self._recording or self._input_count <= 0:
            return None
        mark = None
        bpm = _RECORD_BPM
        ppq = _RECORD_PPQ
        if self._drums is not None:
            loop = max(1, int(self._drums.pattern.loop_ticks))
            try:
                tick = int(self._drums.queue.get_status().tick_time)
            except Exception:
                tick = 0
            bpm = _safe_bpm(self._drums.pattern.bpm)
            ppq = _safe_ppq(self._drums.pattern.ppq)
            mark = {
                'phase_ticks': tick % loop,
                'bpm': bpm,
                'ppq': ppq,
                'loop_ticks': loop,
            }
        self._recording = True
        self._record_events = []
        self._record_origin = self._clock_ns()
        self._record_bpm = bpm
        self._record_ppq = ppq
        self._record_mark = mark
        return {'mark': mark}

    def _op_record_stop(self):
        if not self._recording:
            return None
        self._recording = False
        end_tick = ns_to_ticks(
            self._clock_ns() - self._record_origin,
            self._record_bpm,
            self._record_ppq,
        )
        events = list(self._record_events)
        self._record_events = []
        return {
            'events': events,
            'end_tick': end_tick,
            'bpm': self._record_bpm,
            'ppq': self._record_ppq,
        }

    def _capture_pending(self):
        # Base event_input raises EAGAIN instead of polling forever.
        for _ in range(_CAPTURE_BATCH):
            try:
                if not self._client.event_input_pending(True):
                    return
                event = SequencerClientBase.event_input(self._client)
            except ALSAError:
                return
            except Exception:
                return
            if event is None:
                return
            try:
                self._capture(event)
            except Exception:
                continue

    def _capture(self, event):
        when = getattr(event, 'time', None)
        if when is None or not hasattr(when, 'seconds'):
            when = self._clock_ns()
        else:
            when = _ns(when)
        tick = ns_to_ticks(when - self._record_origin, self._record_bpm, self._record_ppq)
        message = _capture_message(event, tick)
        if message is not None:
            self._record_events.append(message)

    def _op_shutdown(self):
        self._running = False
        return True

    def _shutdown(self):
        self._recording = False
        try:
            self._stop_take(True)
            self._stop_drums(True)
        except Exception:
            pass
        if self._clock is not None:
            try:
                self._clock.stop()
                self._drain()
                self._clock.close()
            except Exception:
                pass
            self._clock = None
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
