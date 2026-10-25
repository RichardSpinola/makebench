"""QA visual de exportação e teclado em compositor privado, sem construir nem executar projeto."""

import argparse
import faulthandler
import signal
import json
import os
from pathlib import Path
import tempfile
import time


def main():
    """Confere os dois produtos, prévia inerte e Tab/Ctrl+Tab reais no terminal da IDE."""
    faulthandler.enable()
    faulthandler.register(signal.SIGTERM, chain=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, choices=("qt", "gtk"))
    parser.add_argument("--theme", default="dark", choices=("light", "dark"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from makebench.core.project import Project
    from makebench.editor.window import MainWindow
    from native_palette import kde_palette

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setPalette(kde_palette(args.theme))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        os.environ["XDG_CONFIG_HOME"] = str(root / "config")
        os.environ["XDG_STATE_HOME"] = str(root / "state")
        project = Project.empty("Distribuição QA")
        project.application["backend"] = args.backend
        terminal = project.add(project.root.id, "terminal")
        terminal.properties["terminal_autostart"] = True
        window = MainWindow(project)
        window.recovery_timer.stop()
        window.logic.ensure_loaded()
        window.show()

        def wait(predicate, seconds=10):
            """Processa os eventos e cede a GIL ao worker/PTY do teste."""
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)
                if predicate():
                    return
            raise AssertionError("Prazo de QA excedido")

        try:
            window.export_action.trigger()
            panel = window.publish_panel
            wait(lambda: window.publish_dialog.isVisible())
            for format in ("source", "deb", "rpm", "appimage", "flatpak"):
                panel.format.setCurrentIndex(panel.format.findData(format))
                app.processEvents()
                assert panel.job is None
                window.publish_dialog.grab().save(str(args.output / (format + ".png")))
            panel.product.setCurrentIndex(1)
            app.processEvents()
            assert panel.format.currentData() == "appimage" and panel.job is None
            window.publish_dialog.grab().save(str(args.output / "editor.png"))
            window.publish_dialog.hide()
            surface = window.terminal_panel.surface
            assert not surface.terminal.running
            (root / "completion_target_123").touch()
            surface.terminal.root = root
            window.drawer.show()
            window.drawer.setCurrentWidget(window.terminal_panel)
            surface.start_terminal("/bin/bash", ["--noprofile", "--norc"])
            wait(lambda: surface.terminal.running)
            QTest.keyClicks(surface, "printf '%s\\n' completion_")
            QTest.keyClick(surface, Qt.Key.Key_Tab)
            QTest.keyClick(surface, Qt.Key.Key_Return)
            wait(
                lambda: any(
                    line.strip() == "completion_target_123"
                    for line in surface.terminal.screen.display
                )
            )
            QTest.keyClick(surface, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
            app.processEvents()
            assert not surface.hasFocus()
            surface.stop_terminal()
            assert not surface.terminal.running
            ratio = window.devicePixelRatioF()
            (args.output / "results.json").write_text(
                json.dumps(
                    {
                        "backend": args.backend,
                        "theme": args.theme,
                        "actual_scale": ratio,
                        "checks": [
                            "Cinco destinos e AppImage do editor sem execução",
                            "Terminal da IDE inerte até ação explícita",
                            "Tab completa arquivo; Ctrl+Tab sai do terminal",
                            "Encerramento recolhe a sessão",
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        finally:
            window.history.mark_saved()
            window.source.mark_saved()
            window.close()
            wait(lambda: not window.isVisible(), 15)


if __name__ == "__main__":
    main()
