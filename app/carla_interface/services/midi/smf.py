"""Standard MIDI File helpers: channel remap and tiny Type-0 messages."""


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
