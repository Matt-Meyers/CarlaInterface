"""MIDI output via the bundled sendmidi binary.

Program changes are used for plugins that do not expose Carla presets
(e.g. Pigments). Recording and MIDI input can be added in this module later
without changing the UI.
"""

import subprocess
from pathlib import Path


class MidiService:
    def __init__(self, sendmidi_path, port_name):
        self.sendmidi_path = Path(sendmidi_path)
        self.port_name = port_name

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
