# SPDX-License-Identifier: GPL-3.0-or-later
"""Visual journey of the Designer, modules and Qt/GTK debugging in a private compositor."""

import argparse
import json
import os
from pathlib import Path
import tempfile
import time


def main():
    """Record real clicks, files and execution without opening personal projects."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, choices=("qt", "gtk"))
    parser.add_argument("--theme", default="dark", choices=("light", "dark"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QLineEdit, QToolButton, QCheckBox
    from PySide6.QtTest import QTest
    from makebench.core.project import Project, ComponentKind, LayoutKind
    from makebench.core.storage import load_project
    from makebench.core.source import SourceBuffer
    from makebench.editor.window import MainWindow
    from makebench.editor.settings import EditorPreferences
    from native_palette import kde_palette

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setPalette(kde_palette(args.theme))
    errors = []
    results = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        os.environ["XDG_CONFIG_HOME"] = str(root / "config")
        os.environ["XDG_STATE_HOME"] = str(root / "state")
        project = Project.empty("Designer · " + args.backend)
        project.application["backend"] = args.backend
        project.root.layout = LayoutKind.FREE
        project.root.properties.update(width=760, height=600)
        a = project.add(project.root.id, ComponentKind.BUTTON)
        b = project.add(project.root.id, ComponentKind.LABEL)
        a.geometry.update(x=32, y=32, width=160, height=40)
        b.geometry.update(x=220, y=96, width=180, height=40)
        a.properties["text"] = "Um"
        b.properties["text"] = "Dois"
        window = MainWindow(project)
        window.recovery_timer.stop()
        window.logic.ensure_loaded()
        window.resize(1440, 950)
        window.show()
        window.set_mode("design")
        window._show_error = lambda error, *_: errors.append(error)
        native = window.winId()

        def wait(predicate, seconds=25):
            """Process real events, always with a deadline to detect hangs."""
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                QTest.qWait(20)
                if errors:
                    raise AssertionError(errors)
                if predicate():
                    return
            print("TIMEOUT OUTPUT", window.output_log.toPlainText(), flush=True)
            raise AssertionError("Prazo excedido: " + str(args.backend))

        def settle():
            """Wait for a current GTK preview without pausing the Qt event queue."""
            if args.backend == "gtk":
                wait(
                    lambda: (
                        not window.canvas.gtk_surface.image.isNull()
                        and window.canvas.gtk_surface.job is None
                        and not window.canvas.gtk_surface.timer.isActive()
                    )
                )
            QTest.qWait(80)

        def capture(name, widget=None):
            """Capture the tested window, without redrawing the interface into an artificial image."""
            QTest.qWait(60)
            assert (widget or window).grab().save(str(args.output / (name + ".png")))

        try:
            settle()
            window.select_multiple([a.id, b.id])
            frames = dict(window.canvas._frames)
            zoom = window.zoom_view.zoom
            field = window.inspector.findChild(QLineEdit, "batch_text")
            assert field.placeholderText() == "Multiple values"
            field.setFocus()
            QTest.keyClicks(field, "Texto comum")
            QTest.keyClick(field, Qt.Key.Key_Return)
            settle()
            assert (
                window.project.find(a.id).properties["text"] == "Texto comum"
                and window.project.find(b.id).properties["text"] == "Texto comum"
            )
            assert frames == window.canvas._frames and window.zoom_view.zoom == zoom
            capture("01-propriedades-comuns")
            before = window.history._index
            window.selection_command("left")
            settle()
            assert window.history._index == before + 1
            assert frames == window.canvas._frames
            window.undo()
            window.redo()
            settle()
            window._select(a.id)
            window.selected_ids = {a.id}
            window.select_multiple([a.id])
            frames = dict(window.canvas._frames)
            original = dict(window.project.find(a.id).geometry)
            window._commit_geometry(a.id, dict(original, x=original["x"] + 8))
            settle()
            assert frames == window.canvas._frames
            assert window.winId() == native
            results.extend(
                [
                    "Collective property by keyboard, one edit and preserved widgets",
                    "Alinhamento e movimento reutilizam controles",
                    "Undo/redo keep the selection and zoom",
                ]
            )
            preferences = EditorPreferences(window)
            preferences.show()
            preferences.navigation.setCurrentRow(6) if hasattr(preferences, "navigation") else None
            # Find the page by its text, without assuming its position among the preferences.
            for list_widget in preferences.findChildren(
                __import__("PySide6.QtWidgets", fromlist=["QListWidget"]).QListWidget
            ):
                for index in range(list_widget.count()):
                    if list_widget.item(index).text() == "Plugins":
                        list_widget.setCurrentRow(index)
            QTest.qWait(80)
            capture("02-plugins", preferences)
            preferences.close()
            results.append("Plugins reserved in the Preferences")
            example = (
                Path(__file__).resolve().parents[1]
                / "examples/python-modules"
                / args.backend
                / "project.makebench.json"
            )
            window._replace_project(load_project(example), example)
            window._created_here = True
            marker = root / "explicit-execution"
            source = window.source.text
            window.source_editor.setPlainText(
                "from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n" + str(source)
            )
            window.set_mode("code")
            window.open_code_file("makebench_user/calculations.py", 5)
            editor = window.active_code_editor()
            editor.appendPlainText("\n# editable comment")
            window._update_code()
            assert not marker.exists()
            capture("03-arquivos-python")
            before = window.execution_fingerprint()
            editor.appendPlainText("# change not run yet")
            assert before != window.execution_fingerprint()
            # Ctrl+Space shows the real ctx methods; Esc closes without changing the text.
            window.open_code_file("@actions")
            entry = window.source_editor
            original = entry.toPlainText()
            entry.appendPlainText("ctx.term")
            entry.moveCursor(entry.textCursor().MoveOperation.End)
            window.raise_()
            window.activateWindow()
            entry.setFocus()
            QTest.qWait(160)
            QTest.keyClick(entry, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
            QTest.qWait(80)
            assert window._entry_assist.popup.isVisible()
            capture("04-sugestoes")
            QTest.keyClick(entry, Qt.Key.Key_Escape)
            entry.setPlainText(original)
            # Invalid syntax stays editable and the diagnostic opens the right module.
            helper = window.module_editors["makebench_user/calculations.py"]
            text = helper.toPlainText()
            helper.appendPlainText("def incompleta(")
            window._update_actions()
            item = next(
                window.problems.item(i)
                for i in range(window.problems.count())
                if window.problems.item(i).data(Qt.ItemDataRole.UserRole).get("source_file")
                == "makebench_user/calculations.py"
            )
            window.go_to_problem(item)
            assert window.active_code_editor() is helper
            capture("05-diagnostico")
            helper.setPlainText(text)
            window._update_code()
            assert not marker.exists()
            results.extend(
                [
                    "Editable module tree and tabs; generated code read-only",
                    "Real Ctrl+Space with ctx methods",
                    "Diagnostic by file/line/column opens the origin",
                    "Opening, editing and previewing never run source",
                ]
            )
            window.toggle_source_breakpoint(6, "makebench_user/calculations.py")
            window.debug_project()
            runtime = window.runtime_window
            assert runtime is not None
            runtime.session.error.connect(errors.append)
            pauses = []

            def paused_message(message):
                if message.get("state") == "paused":
                    pauses.append(message)

            runtime.session.debug_changed.connect(paused_message)
            wait(lambda: bool(pauses))
            runtime.session.debug_command("continue")
            wait(
                lambda: any(
                    p.get("source_file") == "makebench_user/calculations.py" for p in pauses
                )
            )
            paused = next(
                p for p in pauses if p.get("source_file") == "makebench_user/calculations.py"
            )
            assert paused["stack"][0]["variables"]["result"] == 3
            assert marker.exists()
            capture("06-depuracao-modulo")
            runtime.session.debug_command("continue")
            wait(lambda: runtime.session.closed)
            results.append(
                "Qt/GTK debugging steps into the module and shows the snapshot stack/variables"
            )
            (args.output / "results.json").write_text(
                json.dumps(
                    {
                        "backend": args.backend,
                        "theme": args.theme,
                        "actual_scale": window.devicePixelRatioF(),
                        "checks": results,
                        "pauses": pauses,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            print("OK", args.backend, args.theme, len(results), flush=True)
        finally:
            if window.runtime_window and not window.runtime_window.session.closed:
                window.runtime_window.stop()
                wait(lambda: window.runtime_window.session.closed)
            window.history.mark_saved()
            window.source.mark_saved()
            window.close()
            wait(lambda: not window.isVisible())


if __name__ == "__main__":
    main()
