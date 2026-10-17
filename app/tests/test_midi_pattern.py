"""Timing, SMF, and drum-folder tests. These do not open ALSA."""

import tempfile
import unittest
from pathlib import Path

from carla_interface.services.midi.catalog import scan_drum_catalog
from carla_interface.services.midi.pattern import (
    choose_bpm,
    events_in_range,
    filename_bpm,
    linked_drum_pattern,
    load_pattern,
    pad_ticks,
    rotate_events,
    ticks_to_seconds,
)
from carla_interface.services.midi.smf import parse_smf, write_smf


class BpmTests(unittest.TestCase):
    def test_filename_token(self):
        self.assertEqual(filename_bpm('095 BPM - So 90s.mid'), 95)
        self.assertEqual(filename_bpm('So 90s 95bpm.mid'), 95)
        self.assertEqual(filename_bpm('120.5 BPM loop.midi'), 120.5)
        self.assertIsNone(filename_bpm('So 90s.mid'))
        self.assertIsNone(filename_bpm('0 BPM.mid'))
        self.assertIsNone(filename_bpm('BPM 95.mid'))

    def test_choose_bpm_order(self):
        self.assertEqual(choose_bpm(100, '095 BPM - So 90s.mid', 80), 80)
        self.assertEqual(choose_bpm(100, '095 BPM - So 90s.mid'), 95)
        self.assertEqual(choose_bpm(100, 'So 90s.mid'), 100)
        self.assertEqual(choose_bpm(None, None), 120)
        # Takes pass no file name, so a BPM in the path is ignored.
        self.assertEqual(choose_bpm(100, None), 100)


class PadTests(unittest.TestCase):
    def test_rounds_up_to_the_loop(self):
        self.assertEqual(pad_ticks(1000, 480), 1440)
        self.assertEqual(pad_ticks(960, 480), 960)
        self.assertEqual(pad_ticks(0, 480), 480)
        self.assertEqual(pad_ticks(100, 0), 100)


class RangeTests(unittest.TestCase):
    def test_loops_without_a_gap(self):
        events = [(0, 0x99, b'\x24\x40'), (50, 0x89, b'\x24\x00')]
        found = events_in_range(events, 100, 0, 250)
        self.assertEqual([tick for tick, _status, _data in found], [0, 50, 100, 150, 200])

    def test_rotate_puts_the_phase_on_tick_zero(self):
        events = [(0, 0x99, b'\x24\x40'), (10, 0x99, b'\x26\x40')]
        rotated = rotate_events(events, 100, 10)
        self.assertEqual(rotated[0][0], 0)
        self.assertEqual(rotated[1][0], 90)

    def test_linked_pattern_fills_the_take(self):
        from carla_interface.services.midi.pattern import MidiPattern
        pattern = MidiPattern(((0, 0x99, b'\x24\x40'),), 480, 95, 480)
        linked = linked_drum_pattern(pattern, 0, 960)
        self.assertEqual(linked.loop_ticks, 960)
        self.assertEqual([tick for tick, _s, _d in linked.events], [0, 480])


class SmfTests(unittest.TestCase):
    def test_roundtrip_tempo_and_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '095 BPM - So 90s.mid'
            write_smf(
                path,
                [(0, 0x90, b'\x24\x40'), (240, 0x80, b'\x24\x00')],
                480,
                100,
                480,
            )
            parsed = parse_smf(path.read_bytes())
            self.assertEqual(parsed.ppq, 480)
            self.assertAlmostEqual(parsed.bpm, 100, places=2)
            self.assertEqual(parsed.loop_ticks, 480)
            self.assertEqual(parsed.events[0][0], 0)
            self.assertEqual(parsed.events[1][0], 240)

            drums = load_pattern(path, channel=9, use_filename_bpm=True)
            self.assertEqual(drums.bpm, 95)
            self.assertEqual(drums.events[0][1] & 0x0F, 9)

            take = load_pattern(path, channel=15)
            self.assertAlmostEqual(take.bpm, 100, places=2)
            self.assertEqual(take.events[0][1] & 0x0F, 15)

    def test_running_status_and_smpte(self):
        # Note on, running-status note on, end of track. PPQ 96.
        track = bytes((
            0x00, 0x90, 0x24, 0x40,
            0x60, 0x26, 0x40,
            0x00, 0xFF, 0x2F, 0x00,
        ))
        chunk = b'MTrk' + len(track).to_bytes(4, 'big') + track
        header = b'MThd' + (6).to_bytes(4, 'big') + b'\x00\x00\x00\x01\x00\x60'
        parsed = parse_smf(header + chunk)
        self.assertEqual(len(parsed.events), 2)
        self.assertEqual(parsed.events[1], (0x60, 0x90, b'\x26\x40'))
        smpte = b'MThd' + (6).to_bytes(4, 'big') + b'\x00\x00\x00\x01\xe2\x50'
        with self.assertRaises(ValueError):
            parse_smf(smpte + chunk)

    def test_seconds(self):
        self.assertAlmostEqual(ticks_to_seconds(480, 120, 480), 0.5)


class ServiceTests(unittest.TestCase):
    def test_constructs_when_alsa_is_missing(self):
        from carla_interface.services.midi import MidiService
        with tempfile.TemporaryDirectory() as tmp:
            midi = MidiService('Midi Through Port-0', tmp)
            midi.send_program_change(1, 2)
            self.assertFalse(midi.start_loop(Path(tmp) / 'missing.mid', 1))
            midi.stop_loop()
            midi.close()


class CatalogTests(unittest.TestCase):
    def test_one_level_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'loose.mid').write_bytes(b'')
            rock = root / 'Rock'
            rock.mkdir()
            (rock / 'b.mid').write_bytes(b'')
            (rock / 'A.MID').write_bytes(b'')
            (rock / 'notes.txt').write_bytes(b'')
            nested = rock / 'ignored'
            nested.mkdir()
            (nested / 'nope.mid').write_bytes(b'')
            (root / 'Empty').mkdir()
            jazz = root / 'jazz'
            jazz.mkdir()
            (jazz / '1.midi').write_bytes(b'')

            catalog = scan_drum_catalog(root)
            self.assertEqual([name for name, _files in catalog], ['jazz', 'Rock'])
            _name, rock_files = catalog[1]
            self.assertEqual([path.name for path in rock_files], ['A.MID', 'b.mid'])
            self.assertEqual(scan_drum_catalog(root / 'missing'), [])


if __name__ == '__main__':
    unittest.main()
