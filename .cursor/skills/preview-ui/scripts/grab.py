"""Screenshot the kiosk. Run with app/.venv Python. Do not set QT_QPA_PLATFORM."""

import os
import runpy
import sys
import tempfile
from pathlib import Path

os.environ.pop('QT_QPA_PLATFORM', None)


def _repo_root():
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / 'app' / 'main.py').is_file():
            return parent
    raise SystemExit('Could not find app/main.py')


ROOT = _repo_root()
APP_DIR = ROOT / 'app'
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

OUT = Path(os.environ.get('TEMP', tempfile.gettempdir())) / 'carla_interface_preview.png'
# Optional: `grab.py Drums` shows that tab before the shot.
# Pop it so main.py's argument parser does not see the tab name.
_TAB = None
if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
    _TAB = sys.argv.pop(1)


def _preview_run(app):
    def capture():
        widget = next(
            (w for w in QApplication.topLevelWidgets() if w.isVisible()),
            None,
        )
        if widget is None:
            print('No visible top-level widget', file=sys.stderr)
            app.exit(1)
            return
        if _TAB:
            from PyQt6.QtWidgets import QTabWidget
            tabs = widget.findChild(QTabWidget)
            if tabs is not None:
                for index in range(tabs.count()):
                    if tabs.tabText(index) == _TAB:
                        tabs.setCurrentIndex(index)
                        break
            app.processEvents()
        widget.grab().save(str(OUT))
        print(OUT)
        app.quit()

    QTimer.singleShot(500, capture)
    return app.exec()


def _show_preview(self):
    self.setGeometry(80, 80, 1050, 600)
    self.show()


QWidget.showMaximized = _show_preview  # frameless kiosk must not cover the desktop

import carla_interface  # noqa: E402
import carla_interface.runtime as runtime  # noqa: E402

carla_interface.run_app = _preview_run
runtime.run_app = _preview_run

runpy.run_path(str(APP_DIR / 'main.py'), run_name='__main__')
