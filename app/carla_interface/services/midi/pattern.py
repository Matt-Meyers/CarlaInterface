"""Timing math for drum loops and takes. No ALSA."""

import re
from dataclasses import dataclass
from pathlib import Path

from carla_interface.services.midi.smf import parse_smf

_BPM_RE = re.compile(r'(\d+(?:\.\d+)?)\s*bpm', re.IGNORECASE)
_DEFAULT_BPM = 120.0


@dataclass(frozen=True)
class MidiPattern:
    """Voice events already remapped onto one channel, in tick order."""

    events: tuple
    ppq: int
    bpm: float
    loop_ticks: int


def filename_bpm(name):
    """First '95 BPM' / '095 bpm' token in a file name, or None."""
    match = _BPM_RE.search(Path(name).stem)
    if match is None:
        return None
    value = float(match.group(1))
    if value <= 0:
        return None
    return value


def choose_bpm(file_bpm, name=None, override=None):
    """override, then a filename token, then the file tempo, then 120.

    Pass name only for drum loops. Takes must not pick up a BPM in the name.
    """
    for candidate in (override, filename_bpm(name) if name else None, file_bpm):
        if candidate is None:
            continue
        value = float(candidate)
        if value > 0:
            return value
    return _DEFAULT_BPM


def pad_ticks(length, loop_ticks):
    """Round length up to a whole number of loops. 0 becomes one loop."""
    length = max(0, int(length))
    loop_ticks = int(loop_ticks)
    if loop_ticks <= 0:
        return length
    if length <= 0:
        return loop_ticks
    remainder = length % loop_ticks
    if remainder == 0:
        return length
    return length + (loop_ticks - remainder)


def ticks_to_seconds(ticks, bpm, ppq):
    bpm = float(bpm)
    ppq = int(ppq)
    if bpm <= 0 or ppq <= 0:
        return 0.0
    return max(0, int(ticks)) * 60.0 / (bpm * ppq)


def ns_to_ticks(nanoseconds, bpm, ppq):
    bpm = float(bpm)
    ppq = int(ppq)
    nanoseconds = int(nanoseconds)
    if bpm <= 0 or ppq <= 0 or nanoseconds <= 0:
        return 0
    return int(round(nanoseconds * bpm * ppq / 60_000_000_000))


def horizon_ticks(bpm, ppq, seconds=1.0):
    """How many ticks to keep queued ahead of the clock."""
    bpm = float(bpm) if bpm else _DEFAULT_BPM
    ppq = int(ppq) if ppq else 960
    return max(1, int(bpm * ppq * float(seconds) / 60.0))


def load_pattern(path, channel=None, bpm=None, use_filename_bpm=False):
    """Load a MIDI file. channel is 0-based; None keeps each event's channel.

    bpm forces the playback tempo. use_filename_bpm lets a drum file name
    override the tempo written in the file.
    """
    parsed = parse_smf(Path(path).read_bytes())
    events = parsed.events
    if channel is not None:
        chan = max(0, min(15, int(channel)))
        events = tuple((tick, (status & 0xF0) | chan, data) for tick, status, data in events)
    chosen = choose_bpm(
        parsed.bpm,
        path if use_filename_bpm else None,
        bpm,
    )
    return MidiPattern(events, parsed.ppq, chosen, parsed.loop_ticks)


def rescale_pattern(pattern, ppq):
    """Move ticks onto another PPQ. bpm is unchanged."""
    ppq = int(ppq)
    if ppq <= 0 or pattern.ppq == ppq or pattern.ppq <= 0:
        return pattern
    factor = ppq / pattern.ppq
    events = tuple(
        (int(round(tick * factor)), status, data)
        for tick, status, data in pattern.events
    )
    loop = max(1, int(round(pattern.loop_ticks * factor)))
    return MidiPattern(events, ppq, pattern.bpm, loop)


def rotate_events(events, loop_ticks, phase):
    """Shift events so the recorded phase lands on tick 0."""
    loop_ticks = int(loop_ticks)
    if loop_ticks <= 0:
        return list(events)
    phase = int(phase) % loop_ticks
    rotated = [
        ((int(tick) - phase) % loop_ticks, status, data)
        for tick, status, data in events
        if int(tick) < loop_ticks
    ]
    rotated.sort(key=lambda item: item[0])
    return rotated


def tile_events(events, loop_ticks, period):
    """Repeat a loop until period. period should be a multiple of loop_ticks."""
    loop_ticks = int(loop_ticks)
    period = int(period)
    if loop_ticks <= 0:
        return list(events)
    if period <= loop_ticks:
        return [
            (int(tick), status, data)
            for tick, status, data in events
            if int(tick) < period
        ]
    copies = period // loop_ticks
    tiled = []
    for copy in range(copies):
        base = copy * loop_ticks
        for tick, status, data in events:
            tick = int(tick)
            if tick >= loop_ticks:
                continue
            tiled.append((base + tick, status, data))
    return tiled


def linked_drum_pattern(pattern, phase, period):
    """One cycle of the take, with the drum loop rotated and tiled into it."""
    period = pad_ticks(period, pattern.loop_ticks)
    rotated = rotate_events(pattern.events, pattern.loop_ticks, phase)
    tiled = tile_events(rotated, pattern.loop_ticks, period)
    return MidiPattern(tuple(tiled), pattern.ppq, pattern.bpm, period)


def with_loop(pattern, loop_ticks):
    return MidiPattern(pattern.events, pattern.ppq, pattern.bpm, int(loop_ticks))


def pair_patterns(take, drums, phase_ticks):
    """Place a drum loop beside a take on one PPQ and BPM.

    The take keeps its tick length (already padded when it was recorded
    over drums). Drum events are rotated so phase_ticks is the downbeat,
    then tiled across that length. Both patterns use the drum BPM so the
    two queues run at the tempo the part was played against.
    """
    phase = int(phase_ticks)
    if drums.ppq != take.ppq and drums.ppq > 0:
        phase = int(round(phase * take.ppq / drums.ppq))
        drums = rescale_pattern(drums, take.ppq)
    bpm = drums.bpm
    drums = MidiPattern(drums.events, take.ppq, bpm, drums.loop_ticks)
    take = MidiPattern(take.events, take.ppq, bpm, take.loop_ticks)
    drums = linked_drum_pattern(drums, phase, take.loop_ticks)
    take = with_loop(take, drums.loop_ticks)
    return take, drums


def events_in_range(events, loop_ticks, start, end):
    """Absolute ticks in [start, end) from a pattern that loops every loop_ticks."""
    loop_ticks = int(loop_ticks)
    start = int(start)
    end = int(end)
    if loop_ticks <= 0 or start >= end:
        return []
    first = start // loop_ticks
    last = (end - 1) // loop_ticks
    found = []
    for cycle in range(first, last + 1):
        base = cycle * loop_ticks
        for tick, status, data in events:
            absolute = base + int(tick)
            if start <= absolute < end:
                found.append((absolute, status, data))
    return found
