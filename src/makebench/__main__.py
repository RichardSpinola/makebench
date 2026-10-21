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
    args = parser.parse_args()

    from PySide6.QtWidgets import QApplication, QMessageBox

    from makebench.core.project import ProjectError
    from makebench.core.storage import load_project
    from makebench.editor.window import MainWindow

    app = QApplication(sys.argv[:1])
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
    window = MainWindow(project, args.project)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
