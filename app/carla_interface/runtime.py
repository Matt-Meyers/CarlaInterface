"""Qt event-loop helpers."""

import signal

from PyQt6.QtCore import QTimer


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
