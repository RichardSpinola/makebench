# SPDX-License-Identifier: GPL-3.0-or-later
"""Real launcher: WebEngine is ready, the workbench stays hidden and the internal X server exits."""

import os
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")


def main():
    """Exercise the public entry point without opening projects or touching the author's preferences."""
    with tempfile.TemporaryDirectory(prefix="makebench-startup-") as root:
        os.environ["XDG_CONFIG_HOME"] = root + "/config"
        os.environ["XDG_STATE_HOME"] = root + "/state"
        from PySide6.QtCore import Qt, QTimer
        from makebench.editor.startup import StartupDialog
        from makebench.__main__ import main as launch

        original = StartupDialog.show
        verified = []

        def show(dialog):
            """Close with the same action the user uses after the first presentation."""
            original(dialog)

            def close():
                """Check the real window and let Qt quit when the last dialog closes."""
                verified.append(
                    dialog.isVisible()
                    and not dialog.window.isVisible()
                    and bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
                    and dialog.minimumSize() == dialog.maximumSize()
                )
                dialog.banner.close_button.click()

            QTimer.singleShot(100, close)

        with patch("sys.argv", ["makebench"]), patch.object(StartupDialog, "show", show):
            assert launch() == 0
        assert verified == [True], verified
    print("OK: real fixed launcher, frameless, hidden workbench and exit through the inner X.")


if __name__ == "__main__":
    main()
