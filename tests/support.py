"""Keep test runs out of the person's real Makebench settings and data.

Every test module imports this first, so QSettings, themes, pieces and plugins
point to a throwaway folder whether the whole suite or one module runs.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings

ROOT = Path(tempfile.mkdtemp(prefix="makebench-tests-"))
CONFIG = ROOT / "config"
DATA = ROOT / "data"
CONFIG.mkdir()
DATA.mkdir()
os.environ["XDG_CONFIG_HOME"] = str(CONFIG)
os.environ["XDG_DATA_HOME"] = str(DATA)
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(CONFIG))
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(CONFIG))
atexit.register(shutil.rmtree, ROOT, True)


def release_widgets():
    """Delete leftover windows while QApplication still exists.

    Views closed with deleteLater() outside an event loop otherwise outlive the
    application, and QtWebEngine crashes when it destroys them at interpreter exit.
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    app = QCoreApplication.instance()
    if app is None or not hasattr(app, "topLevelWidgets"):
        return
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


atexit.register(release_widgets)
