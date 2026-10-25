"""Application entry point and support for opening a project from the terminal."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from makebench import __version__
from makebench.i18n import tr


def configure_language() -> str:
    """Activate the interface language before any module builds translated labels.

    `MAKEBENCH_LANGUAGE` overrides the saved preference (useful for screenshots
    and tests); otherwise the editor preference is read, defaulting to English.
    """
    import os

    from makebench.i18n import set_language

    code = os.environ.get("MAKEBENCH_LANGUAGE")
    if not code:
        from PySide6.QtCore import QSettings

        code = QSettings("Makebench", "Makebench").value("v1/appearance/language", "en")
    return set_language(str(code))


def main() -> int:
    """Start Qt, validate the optional project and enter the interface loop."""
    configure_language()

    parser = argparse.ArgumentParser(
        description=tr("Makebench — visual editor for Linux applications")
    )
    parser.add_argument("project", nargs="?", type=Path, help=tr(".makebench.json project to open"))
    parser.add_argument("--version", action="version", version=f"Makebench {__version__}")
    parser.add_argument(
        "--run",
        action="store_true",
        help=tr("Explicitly run the project in a test window"),
    )
    args = parser.parse_args()
    if args.run and not args.project:
        parser.error(tr("--run requires a project file"))

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
            QMessageBox.critical(None, tr("Could not open the project"), str(exc))
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
            # WebEngine joins the widget tree before the window is first shown.
            # This avoids native re-creation when Logic opens for the first time.
            window.logic.ensure_loaded()
    except (ProjectError, OSError) as exc:
        QMessageBox.critical(None, tr("Could not open the functions"), str(exc))
        return 1
    if not args.run and not args.project:
        from makebench.editor.settings import preference

        if preference("projects/startup"):
            from makebench.editor.startup import StartupDialog

            window.startup_dialog = StartupDialog(window)
            window.startup_dialog.show()
            return app.exec()
        window.set_mode("map")
    if not args.run and args.project:
        window.set_mode("map")
    window.show()
    if args.run:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, window.start)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
