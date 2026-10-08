import os


class Osc:
    def __init__(self, port, host='localhost', exe=None):
        """
        Initializer for Osc class.
        Requires liblo-tools.

        :param port: port of osc server to send to
        :param host: host of server to send to (default: localhost)
        :param exec: if using .exe (if Windows), supply path
        """
        self.cmd = 'oscsend'
        self.host = f'{host}:{port}'
        self.prefix = 'osc.udp://'
        self.name = '/Carla'

        if exe is not None:
            self.cmd = exe
            self.prefix = ''
            self.host = f'{host} {port}'

    def send_osc(self, cmd, osc_type, val):
        """
        Basic send of single osc command using oscsend.
        Check oscsend --help for more info.

        :param cmd: command string
        :param osc_type: single-char string of type to send
        :param val: command value
        :return:
        """
        cmd_str1 = f'{self.cmd} {self.prefix}{self.host}'
        cmd_str2 = f'{self.name}{cmd} {osc_type} {val}'
        # print(f'{cmd_str1} {cmd_str2}')
        try:
            os.system(f'{cmd_str1} {cmd_str2}')
        except Exception:
            pass


class Midi:
    def __init__(self, exec_location, port_name):
        self.exec_location = exec_location
        self.port_name = port_name

        self.exec = os.path.join(self.exec_location, 'sendmidi')

    def send_prog_change(self, num):
        print(f'.{self.exec} dev \"{self.port_name}\" pc {num}')
        os.system(f'{self.exec} dev \"{self.port_name}\" pc {num}')
