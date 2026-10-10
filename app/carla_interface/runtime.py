"""Launch helpers: CLI flags and the Qt event loop."""

import argparse
import signal
from dataclasses import fields, replace
from pathlib import Path

from PyQt6.QtCore import QTimer

from carla_interface.config import AppConfig

_CLI_TYPES = {str: str, int: int, Path: Path}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Carla Interface')
    parser.add_argument(
        '--windowed',
        action='store_true',
        help='Open a framed window instead of the fullscreen kiosk',
    )
    for field in fields(AppConfig):
        cli_type = _CLI_TYPES.get(field.type)
        if cli_type is None:
            raise TypeError(f'No CLI mapping for AppConfig.{field.name}')
        parser.add_argument(
            f'--{field.name.replace("_", "-")}',
            dest=field.name,
            default=None,
            type=cli_type,
            metavar=field.name.upper(),
            help=f'Override AppConfig.{field.name}',
        )
    return parser.parse_args(argv)


def apply_config_args(config, args):
    """Copy explicitly passed CLI flags onto a main.py AppConfig."""
    updates = {
        field.name: getattr(args, field.name)
        for field in fields(AppConfig)
        if getattr(args, field.name, None) is not None
    }
    return replace(config, **updates) if updates else config


def run_app(app):
    """Run the Qt loop so Ctrl+C from a terminal can quit.

    SIGINT is only delivered between Python bytecode instructions. Qt's
    C++ exec() never returns on its own, so a short timer yields back to
    the interpreter.
    """
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    wakeup = QTimer(app)
    wakeup.start(200)
    wakeup.timeout.connect(lambda: None)
    return app.exec()
