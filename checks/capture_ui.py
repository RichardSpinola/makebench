"""Real editor screenshots for QA; never runs project scripts."""

import argparse
import os
from pathlib import Path
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")


def main():
    """Generate a matrix of modes/sizes/themes using a known in-memory project."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--sizes", nargs="+", default=["1280x800", "1920x1080"])
    parser.add_argument("--themes", nargs="+", default=["light", "dark"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="makebench-captures-") as temporary:
        os.environ["XDG_CONFIG_HOME"] = str(Path(temporary) / "config")
        os.environ["XDG_STATE_HOME"] = str(Path(temporary) / "state")
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        from makebench.core.navigation import welcome_template
        from makebench.editor.window import MainWindow
        from makebench.editor.theme import manager

        window = MainWindow(welcome_template())
        window.recovery_timer.stop()
        window.show()
        window.set_mode("logic")
        deadline = time.monotonic() + 15
        while not window.logic.ready and time.monotonic() < deadline:
            QTest.qWait(25)
        if not window.logic.ready:
            raise RuntimeError(window.logic.diagnostics.text())
        from native_palette import kde_palette

        for theme in args.themes:
            # QA only: offscreen does not receive the compositor scheme. The palette comes
            # from the installed Breeze schemes, with no palette invented by the editor.
            app.setPalette(kde_palette(theme))
            manager().set_mode("system")
            for size in args.sizes:
                width, height = map(int, size.split("x"))
                window.resize(width, height)
                window.activate_window(window.project.root.id, "@default")
                QTest.qWait(100)
                for mode in ["start", "design", "logic", "code", "map", "publish"]:
                    window.publish_dialog.hide()
                    if mode == "start":
                        window.show_home()
                    else:
                        if mode == "logic":
                            button = next(
                                node
                                for node in window.project.root.walk()
                                if node.properties.get("text") == "Next"
                            )
                            window._select(button.id)
                        window.set_mode(mode)
                    app.processEvents()
                    if mode == "map":
                        window.map_panel.fit()
                    QTest.qWait(400 if mode == "logic" else 100)
                    filename = args.output / f"{theme}-{size}-{mode}.png"
                    if (
                        not (window.publish_dialog if mode == "publish" else window)
                        .grab()
                        .save(str(filename))
                    ):
                        raise RuntimeError("Falha ao gravar " + str(filename))
                window.publish_dialog.hide()
                window.set_mode("design")
                window.left_tabs.setCurrentIndex(1)
                QTest.qWait(80)
                window.grab().save(str(args.output / f"{theme}-{size}-inserir.png"))
                window.left_tabs.setCurrentIndex(0)
                window.show_test_error(
                    {
                        "message": "Example failure: task ended with code 3.",
                        "traceback": "Visual check diagnostic.",
                    }
                )
                QTest.qWait(80)
                window.grab().save(str(args.output / f"{theme}-{size}-gaveta-erro.png"))
                window.drawer.hide()
                window.test_status.setText("Stopped")
                window.preferences()
                QTest.qWait(80)
                window.preferences_dialog.grab().save(
                    str(args.output / f"{theme}-{size}-preferencias.png")
                )
                window.preferences_dialog.close()
                window.application_settings()
                QTest.qWait(80)
                window.app_settings_dialog.grab().save(
                    str(args.output / f"{theme}-{size}-configuracoes.png")
                )
                window.app_settings_dialog.close()

                # The dialog is real; it is only captured and cancelled, without creating a folder.
                def capture_dialog():
                    dialog = app.activeModalWidget()
                    if dialog:
                        dialog.grab().save(str(args.output / f"{theme}-{size}-novo-projeto.png"))
                        dialog.reject()

                QTimer.singleShot(100, capture_dialog)
                window.new_project_dialog("blank")
        window.history.mark_saved()
        window.source.mark_saved()
        window.close()
        if window.logic.view:
            window.logic.page.deleteLater()
            from PySide6.QtCore import QCoreApplication, QEvent

            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        window.deleteLater()
        app.processEvents()
    print("Capturas gravadas em", args.output)


if __name__ == "__main__":
    main()
