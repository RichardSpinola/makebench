"""Native workbench journeys: map, commands and build, without running the project."""

import os
from pathlib import Path
import sys
import tempfile
import time
import zipfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main():
    """Use only known documents and keep every write in a temporary folder."""
    with tempfile.TemporaryDirectory(prefix="makebench-studio-check-") as temporary:
        root = Path(temporary)
        os.environ["XDG_CONFIG_HOME"] = str(root / "config")
        os.environ["XDG_STATE_HOME"] = str(root / "state")
        from PySide6.QtCore import QTimer
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLineEdit
        from makebench.core.project import ComponentKind, Project
        from makebench.core.navigation import add_window, welcome_template
        from makebench.editor.window import MainWindow

        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        project = Project.empty("Mapa de teste")
        button = project.add(project.root.id, ComponentKind.BUTTON)
        other = add_window(project, "Destination")
        window = MainWindow(project)
        window.show()
        window.set_mode("map")
        app.processEvents()

        def accept_connection():
            """Simulate confirming the native connection dialog and closing the source."""
            dialog = app.activeModalWidget()
            assert isinstance(dialog, QDialog)
            closing = dialog.findChild(QCheckBox)
            assert closing is not None
            closing.setChecked(True)
            dialog.accept()

        QTimer.singleShot(50, accept_connection)
        window.map_panel.connect_nodes(project.root.id + "|@default", other.id + "|@default")
        flow = window.project.workflows[0]
        assert flow["event"]["component"] == button.id and flow["body"][0]["close_current"] is True

        def jump_function():
            """Pick a function through the real palette, without calling the function code."""
            dialog = app.activeModalWidget()
            assert dialog is not None
            query = dialog.findChild(QLineEdit)
            query.setText("Go to function · greet")
            dialog.invoke()

        QTimer.singleShot(50, jump_function)
        window.show_commands()
        assert window.tabs.currentIndex() == 2 and window.code_files.currentIndex() == 1
        window.history.mark_saved()
        window.source.mark_saved()
        window.close()
        example = MainWindow(welcome_template("Assistente Makebench"))
        example.show()
        icon = root / "icon.svg"
        icon.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect width="256" height="256" rx="40" fill="#a34916"/><path d="M56 184V72l72 64 72-64v112" fill="none" stroke="white" stroke-width="20" stroke-linejoin="round"/></svg>'
        )
        reference = example.assets.import_image(icon)
        example.project.application = {
            "name": "Assistente Makebench",
            "id": "io.makebench.example",
            "version": "0.1.0",
            "description": "Three steps and two windows.",
            "icon": reference,
        }
        example.set_mode("publish")
        app.processEvents()
        assert example.publish_panel.check()
        destination = root / "example.zip"
        with patch(
            "makebench.editor.publish.QFileDialog.getSaveFileName",
            return_value=(str(destination), ""),
        ):
            example.publish_panel.build_source()
        limit = time.monotonic() + 120
        while example.publish_panel.job.isRunning() and time.monotonic() < limit:
            QTest.qWait(20)
        app.processEvents()
        assert destination.is_file(), example.publish_panel.result.text()
        with zipfile.ZipFile(destination) as archive:
            assert archive.testzip() is None
            assert "run.py" in archive.namelist()
            assert not any("/editor/" in name for name in archive.namelist())
        if len(sys.argv) > 1:
            import shutil

            output = Path(sys.argv[1])
            output.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, output / "exemplo-fonte-python.zip")
        example.history.mark_saved()
        example.source.mark_saved()
        example.close()
        app.processEvents()
        print("OK: connection in the map, function lookup and build through the native UI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
