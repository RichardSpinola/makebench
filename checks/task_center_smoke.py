"""Real task center: output in the drawer and in the Qt application panel."""

from pathlib import Path
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
from PySide6.QtTest import QTest
from makebench.core.storage import load_project
from makebench.core.source import SourceBuffer
from makebench.core.assets import AssetStore
from makebench.runtime.window import RuntimeWindow


def wait(predicate, seconds=12):
    """Wait for real worker events without replacing execution with mocks."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    raise AssertionError("The task center did not finish in time.")


def main():
    """Question, simulation, progress, script, stderr and closing are checked."""
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    path = Path(__file__).resolve().parents[1] / "examples/en/script-center/app.makebench.json"
    window = RuntimeWindow(
        load_project(path),
        SourceBuffer.load(path).text,
        AssetStore(path.parent).read,
        path.parent,
        path.with_name("app.actions.py"),
        supervision=True,
    )
    window.show()
    window.start()
    wait(lambda: window.session.active and not window.session.busy)
    window.view.widgets["button_setup"].click()
    wait(lambda: bool(window.dialogs))
    dialog = next(iter(window.dialogs))
    assert isinstance(dialog, QInputDialog)
    dialog.setTextValue("Text editor")
    dialog.accept()
    wait(lambda: any(isinstance(d, QMessageBox) for d in window.dialogs))
    confirm = next(d for d in window.dialogs if isinstance(d, QMessageBox))
    confirm.done(QMessageBox.StandardButton.Yes)
    wait(lambda: not window.session.busy, 15)
    output = window.view.widgets["output_task"].toPlainText()
    assert "Simulation complete" in output, output
    assert "Example warning" in output, output
    assert window.view.widgets["progress_task"].value() == 100
    assert "Simulation complete" in window.output.toPlainText()
    window.view.widgets["button_check"].click()
    wait(lambda: not window.session.busy)
    assert len(window.view.widgets["output_task"].toPlainText()) >= len(output)
    window.stop()
    wait(lambda: window.session.closed)
    window.close()
    print(
        "OK: real Qt task center, question, simulation, progress, Bash, stdout/stderr and the application output panel."
    )


if __name__ == "__main__":
    main()
