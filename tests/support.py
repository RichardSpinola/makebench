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
