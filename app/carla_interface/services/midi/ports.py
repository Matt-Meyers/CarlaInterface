"""ALSA sequencer port listing via aplaymidi/arecordmidi -l."""

import re
import subprocess

# arecordmidi/aplaymidi -l: " 14:0    Midi Through                     Midi Through Port-0"
_PORT_LINE = re.compile(r'^\s*(\d+:\d+)\s+(.*)$')


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
