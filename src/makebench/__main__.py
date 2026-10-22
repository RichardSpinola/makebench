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
    parser.add_argument("--run", action="store_true", help="Executar explicitamente o projeto em uma janela de teste")
    args = parser.parse_args()
    if args.run and not args.project:
        parser.error("--run exige um arquivo de projeto")

    from PySide6.QtWidgets import QApplication, QMessageBox

    from makebench.core.project import ProjectError
    from makebench.core.storage import load_project
    from makebench.editor.window import MainWindow

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
            path = args.project.resolve()
            source = SourceBuffer.load(path)
            window = RuntimeWindow(project, source.text, AssetStore(path.parent).read, path.parent, source.path)
        else:
            window = MainWindow(project, args.project)
    except (ProjectError, OSError) as exc:
        QMessageBox.critical(None, "Não foi possível abrir as funções", str(exc))
        return 1
    if not args.run and not args.project:
        window.show_home()
    window.show()
    if args.run:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, window.start)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
