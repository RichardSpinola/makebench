"""Aceitação da bancada e da ponte GTK com ações reais de depuração."""

import argparse
import json
import os
from pathlib import Path
import tempfile
import time


def main():
    """Verifica F6, pontos, aviso de snapshot, shell explícito e limpeza da IDE."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("qt", "gtk"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="makebench-debug-editor-") as directory:
        os.environ["XDG_CONFIG_HOME"] = directory + "/config"
        os.environ["XDG_STATE_HOME"] = directory + "/state"
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QCoreApplication, QEvent, Qt
        from makebench.core.storage import load_project
        from makebench.core.source import SourceBuffer
        from makebench.editor.window import MainWindow

        path = (
            Path(__file__).resolve().parents[1]
            / "examples/terminal-debug"
            / f"{args.backend}.makebench.json"
        )
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        window = MainWindow(load_project(path))
        window.recovery_timer.stop()
        window.path = path
        window.source = SourceBuffer.load(path)
        window.source_editor.setPlainText(window.source.text)
        window.confirm_trust = lambda: True
        window.logic.ensure_loaded()
        window.show()
        window.set_mode("Design")
        errors = []
        pauses = []

        def wait(predicate, seconds=15):
            """Aguarda sinais e desenho sem bloquear o loop de eventos do editor."""
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                QTest.qWait(25)
                if errors:
                    raise AssertionError(errors)
                if predicate():
                    return
            raise AssertionError(
                ("Prazo excedido", pauses, window.debug_panel.status.text(), runtime.session.closed)
            )

        window.toggle_block_breakpoint(window.project.workflows[0]["id"], "call_demo")
        assert not window.terminal_panel.surface.terminal.running
        window.debug_project()
        runtime = window.runtime_window
        runtime.session.error.connect(errors.append)
        runtime.session.debug_changed.connect(
            lambda m: pauses.append(m) if m.get("state") == "paused" else None
        )
        wait(lambda: runtime.session.active)
        button = window.project.workflows[0]["event"]["component"]
        if args.backend == "qt":
            runtime.view.widgets[button].click()
        else:
            runtime.command({"command": "click", "component": button})
        wait(lambda: len(pauses) == 1)
        wait(lambda: window.logic.ready)
        window.grab().save(str(args.output / "01-depurador.png"))
        window.debug_command("step_in")
        wait(lambda: len(pauses) >= 2)
        assert pauses[1].get("source_line") == 6
        window.grab().save(str(args.output / "02-python.png"))
        window.source_editor.appendPlainText("\n# Mudança durante o snapshot")
        window.update_test_time()
        window.locate_debug(pauses[1])
        assert "reinicie" in window.debug_panel.status.text()
        window.debug_command("continue")
        wait(lambda: not runtime.session.busy)
        window.drawer.setCurrentWidget(window.terminal_panel)
        window.terminal_panel.start_button.click()
        wait(lambda: window.terminal_panel.surface.terminal.running)
        terminal = window.terminal_panel.surface
        terminal.send_terminal("printf 'IDE_TERMINAL_OK\\n'\n")
        wait(lambda: "IDE_TERMINAL_OK" in "\n".join(terminal.terminal.screen.display))
        window.grab().save(str(args.output / "03-terminal-ide.png"))
        window.stop_test()
        wait(lambda: runtime.session.closed)
        window.history.mark_saved()
        window.source.mark_saved()
        window.close()
        QTest.qWait(100)
        assert not terminal.terminal.running
        if hasattr(window.logic, "page"):
            window.logic.page.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        (args.output / "results.json").write_text(
            json.dumps(
                {
                    "backend": args.backend,
                    "passed": [
                        "Depurar separado de Executar",
                        "Parada no bloco",
                        "Entrar na função",
                        "Snapshot preservado ao editar",
                        "Shell só após clique",
                        "Fechar IDE encerra shell",
                        "Ponte GTK ou runtime Qt",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print("OK editor", args.backend)


if __name__ == "__main__":
    main()
