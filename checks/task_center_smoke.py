"""Central de tarefas real: saída na gaveta e no painel do aplicativo Qt."""

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
    """Espera eventos reais do worker sem substituir a execução por mocks."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    raise AssertionError("Central de tarefas não terminou no prazo.")


def main():
    """Pergunta, simulação, progresso, script, stderr e fechamento são verificados."""
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    path = Path(__file__).resolve().parents[1] / "examples/script-center/app.makebench.json"
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
    dialog.setTextValue("Editor de texto")
    dialog.accept()
    wait(lambda: any(isinstance(d, QMessageBox) for d in window.dialogs))
    confirm = next(d for d in window.dialogs if isinstance(d, QMessageBox))
    confirm.done(QMessageBox.StandardButton.Yes)
    wait(lambda: not window.session.busy, 15)
    output = window.view.widgets["output_task"].toPlainText()
    assert "Simulação concluída" in output, output
    assert "Aviso de exemplo" in output, output
    assert window.view.widgets["progress_task"].value() == 100
    assert "Simulação concluída" in window.output.toPlainText()
    window.view.widgets["button_check"].click()
    wait(lambda: not window.session.busy)
    assert len(window.view.widgets["output_task"].toPlainText()) >= len(output)
    window.stop()
    wait(lambda: window.session.closed)
    window.close()
    print(
        "OK: central Qt real, pergunta, simulação, progresso, Bash, stdout/stderr e painel de saída do aplicativo."
    )


if __name__ == "__main__":
    main()
