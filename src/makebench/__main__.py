"""Entrada do aplicativo e suporte à abertura de um projeto pelo terminal."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from makebench import __version__


def main() -> int:
    """Inicia Qt, valida o projeto opcional e entra no ciclo da interface."""
    parser = argparse.ArgumentParser(description="Makebench — editor visual de aplicativos Linux")
    parser.add_argument("project", nargs="?", type=Path, help="Projeto .makebench.json para abrir")
    parser.add_argument("--version", action="version", version=f"Makebench {__version__}")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Executar explicitamente o projeto em uma janela de teste",
    )
    args = parser.parse_args()
    if args.run and not args.project:
        parser.error("--run exige um arquivo de projeto")

    from PySide6.QtWidgets import QApplication, QMessageBox

    from makebench.core.project import ProjectError
    from makebench.core.storage import load_project
    from makebench.editor.window import MainWindow

    from PySide6.QtCore import Qt

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    from makebench.ui.dialogs import install_translation

    install_translation(app)
    app.setApplicationName("Makebench")
    app.setApplicationDisplayName("Makebench")
    app.setOrganizationName("Makebench")
    app.setApplicationVersion(__version__)
    project = None
    if args.project:
        try:
            project = load_project(args.project)
        except ProjectError as exc:
            QMessageBox.critical(None, "Não foi possível abrir o projeto", str(exc))
            return 1
    try:
        if args.run:
            from makebench.core.source import SourceBuffer
            from makebench.editor.assets import AssetStore
            from makebench.runtime.window import RuntimeWindow

            if project.application.get("backend", "qt") == "gtk":
                from makebench.runtime.gtk_bridge import GtkRuntimeBridge as RuntimeWindow
            path = args.project.resolve()
            source = SourceBuffer.load(path)
            window = RuntimeWindow(
                project, source.text, AssetStore(path.parent).read, path.parent, source.path
            )
        else:
            if project is None:
                from makebench.core.project import Project

                project = Project.empty()
                project.metadata["empty_map"] = True
            window = MainWindow(project, args.project)
            # WebEngine entra na árvore antes da primeira apresentação da janela.
            # Evita recriação nativa ao abrir Lógica pela primeira vez.
            window.logic.ensure_loaded()
    except (ProjectError, OSError) as exc:
        QMessageBox.critical(None, "Não foi possível abrir as funções", str(exc))
        return 1
    if not args.run and not args.project:
        from makebench.editor.settings import preference

        if preference("projects/startup"):
            from makebench.editor.startup import StartupDialog

            window.startup_dialog = StartupDialog(window)
            window.startup_dialog.show()
            return app.exec()
        window.set_mode("Mapa")
    if not args.run and args.project:
        window.set_mode("Mapa")
    window.show()
    if args.run:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, window.start)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
