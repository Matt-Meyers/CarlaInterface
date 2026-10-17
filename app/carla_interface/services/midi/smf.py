"""Standard MIDI File helpers: parse, write, channel remap, and tiny messages."""

from dataclasses import dataclass
from pathlib import Path


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


@dataclass
class ParsedSmf:
    """Voice events in tick order, plus the file's own timing.

    bpm is the first tempo meta, or 120 when the file has none.
    loop_ticks is the end-of-track time. Events live in [0, loop_ticks).
    """

    events: tuple
    ppq: int
    bpm: float
    loop_ticks: int


def _parse_track(body):
    events = []
    eot = None
    tempo = None
    tick = 0
    index = 0
    running = None
    while index < len(body):
        delta, index = _read_vlq(body, index)
        tick += delta
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
            data = bytes(body[index:index + count])
            index += count
            events.append((tick, status, data))
            continue
        if status == 0xFF:
            if index >= len(body):
                raise ValueError('truncated meta event')
            meta = body[index]
            index += 1
            length, index = _read_vlq(body, index)
            if index + length > len(body):
                raise ValueError('truncated meta data')
            payload = bytes(body[index:index + length])
            index += length
            if meta == 0x2F:
                eot = tick
            elif meta == 0x51 and length == 3 and tempo is None:
                us = int.from_bytes(payload, 'big')
                if us > 0:
                    tempo = 60_000_000 / us
            continue
        if status in (0xF0, 0xF7):
            length, index = _read_vlq(body, index)
            if index + length > len(body):
                raise ValueError('truncated sysex')
            index += length
            continue
        raise ValueError('unknown MIDI status')
    return events, eot, tempo


def parse_smf(smf):
    """Read a PPQ MIDI file. SMPTE division is refused.

    Voice messages from every track are merged in tick order. The first
    set-tempo meta wins; later tempo changes are left as written and are
    not followed.
    """
    if len(smf) < 14 or smf[:4] != b'MThd':
        raise ValueError('not a MIDI file')
    header_len = int.from_bytes(smf[4:8], 'big')
    if header_len < 6 or 8 + header_len > len(smf):
        raise ValueError('truncated MIDI header')
    division = int.from_bytes(smf[12:14], 'big')
    if division & 0x8000:
        raise ValueError('SMPTE MIDI files are not supported')
    ppq = division or 960
    events = []
    eot_ticks = []
    tempo = None
    index = 8 + header_len
    while index + 8 <= len(smf):
        tag = smf[index:index + 4]
        length = int.from_bytes(smf[index + 4:index + 8], 'big')
        start = index + 8
        end = start + length
        if end > len(smf):
            raise ValueError('truncated MIDI chunk')
        body = smf[start:end]
        index = end
        if tag != b'MTrk':
            continue
        track_events, eot, track_tempo = _parse_track(body)
        events.extend(track_events)
        if eot is not None:
            eot_ticks.append(eot)
        if tempo is None and track_tempo is not None:
            tempo = track_tempo
    events.sort(key=lambda item: item[0])
    loop = max(eot_ticks) if eot_ticks else 0
    if events and events[-1][0] >= loop:
        loop = events[-1][0] + 1
    if loop <= 0:
        loop = ppq * 4
    bpm = float(tempo) if tempo else 120.0
    return ParsedSmf(tuple(events), ppq, bpm, loop)


def _tempo_bytes(bpm):
    us = int(round(60_000_000 / float(bpm)))
    us = max(1, min(0xFFFFFF, us))
    return bytes((0xFF, 0x51, 0x03)) + us.to_bytes(3, 'big')


def write_smf(path, events, ppq, bpm, end_tick):
    """Write a one-track type-0 file. end_tick is the end-of-track time."""
    ppq = max(1, min(0x7FFF, int(ppq)))
    bpm = float(bpm) if bpm and float(bpm) > 0 else 120.0
    ordered = sorted(
        (max(0, int(tick)), status & 0xFF, bytes(data))
        for tick, status, data in events
    )
    end_tick = max(0, int(end_tick))
    if ordered:
        end_tick = max(end_tick, ordered[-1][0])
    track = bytearray()
    track += _write_vlq(0)
    track += _tempo_bytes(bpm)
    last = 0
    for tick, status, data in ordered:
        track += _write_vlq(tick - last)
        track.append(status)
        track += data
        last = tick
    track += _write_vlq(end_tick - last)
    track += bytes((0xFF, 0x2F, 0x00))
    header = (
        b'MThd'
        + (6).to_bytes(4, 'big')
        + (0).to_bytes(2, 'big')
        + (1).to_bytes(2, 'big')
        + ppq.to_bytes(2, 'big')
    )
    chunk = b'MTrk' + len(track).to_bytes(4, 'big') + bytes(track)
    Path(path).write_bytes(header + chunk)


def _all_notes_off_smf(channels):
    """CC 123 on each 1-based channel, then end-of-track."""
    events = bytearray()
    for channel in channels:
        status = 0xB0 | ((max(1, min(16, int(channel))) - 1) & 0x0F)
        events += bytes((0x00, status, 0x7B, 0x00))
    events += bytes((0x00, 0xFF, 0x2F, 0x00))
    header = b'MThd' + (6).to_bytes(4, 'big') + b'\x00\x00\x00\x01\x00\x60'
    return header + b'MTrk' + len(events).to_bytes(4, 'big') + bytes(events)
