# SPDX-License-Identifier: GPL-3.0-or-later
"""Trusted probe of the editor runtime; never imports user projects."""

import json
import ssl


def probe():
    """Exercise the real bootstrap and host tools, keeping the target certificates."""
    from makebench.core.build_environment import run_tool

    version = run_tool(["/usr/bin/flatpak", "--version"]).strip()
    run_tool(
        [
            "/usr/bin/python3",
            "-c",
            "import os; assert not os.environ.get('PYTHONHOME'); assert not os.environ.get('PYTHONPATH')",
        ]
    )
    certificates = ssl.create_default_context().cert_store_stats()["x509_ca"]
    assert certificates > 0, "Portable Python did not find the target's trusted certificates"
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from makebench.core.project import Project
    from makebench.editor.window import MainWindow
    from makebench.editor.settings import EditorPreferences

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(Project.empty())
    window.recovery_timer.stop()
    window.show()
    try:
        window.add_code_module(
            "makebench_user/probe.py", "def calculate(value):\n    return value+1\n"
        )
        assert "makebench_user/probe.py" in window.module_editors
        window.open_code_file("@actions")
        editor = window.source_editor
        editor.setPlainText("def action(ctx, value):\n    ctx.term")
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        editor.setFocus()
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        assert window._entry_assist.popup.isVisible()
        QTest.keyClick(editor, Qt.Key.Key_Return)
        assert "ctx.terminal_send" in editor.toPlainText()
        preferences = EditorPreferences(window)
        assert "Plugins" in [
            preferences.sections.item(n).text() for n in range(preferences.sections.count())
        ]
        preferences.close()
        preferences.deleteLater()
    finally:
        window.history.mark_saved()
        window.source.mark_saved()
        window.close()
        app.processEvents()
    print(
        json.dumps(
            {
                "host_flatpak": version,
                "certificates": certificates,
                "host_python_clean": True,
                "module_editor": True,
                "completion": True,
                "plugins_reserved": True,
            }
        )
    )
    return 0
