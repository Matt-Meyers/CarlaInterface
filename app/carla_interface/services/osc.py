import subprocess


class CarlaOsc:
    """Send OSC commands to Carla via liblo-tools `oscsend` (Linux)."""

    def __init__(self, port, host='localhost'):
        self.url = f'osc.udp://{host}:{port}'
        self.prefix = '/Carla'

    def set_active(self, plugin_idx, active):
        self._send(f'/{plugin_idx}/set_active', 'i', '1' if active else '0')

    def set_program(self, plugin_idx, program):
        self._send(f'/{plugin_idx}/set_program', 'i', str(program))

    def set_parameter(self, plugin_idx, param_idx, value):
        self._send(
            f'/{plugin_idx}/set_parameter_value',
            'if',
            str(param_idx),
            str(value),
        )

    def _send(self, path, osc_type, *values):
        cmd = ['oscsend', self.url, f'{self.prefix}{path}', osc_type, *values]
        try:
            subprocess.run(cmd, check=False)
        except OSError:
            pass
