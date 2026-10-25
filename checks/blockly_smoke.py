# SPDX-License-Identifier: GPL-3.0-or-later
"""Real Qt/WebEngine/Blockly integration; run it separately from the browser-less tests."""

import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from makebench.core.logic import create_flow
from makebench.core.project import ComponentKind, Project
from makebench.core.storage import load_project
from makebench.core.source import source_path
from makebench.editor.window import MainWindow


class BlocklyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.window = MainWindow()
        cls.window.show()
        cls.window.tabs.setCurrentIndex(1)
        deadline = time.monotonic() + 12
        while not cls.window.logic.ready and time.monotonic() < deadline:
            QTest.qWait(25)
        if not cls.window.logic.ready:
            raise AssertionError(cls.window.logic.diagnostics.text())

    @classmethod
    def tearDownClass(cls):
        cls.window._finish_field_edit()
        cls.window.history.mark_saved()
        cls.window.source.mark_saved()
        cls.window.close()
        # The Chromium profile must outlive the page that uses it.
        cls.window.logic.page.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        cls.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def setUp(self):
        project = Project.empty("Teste de blocos")
        self.button = project.add(project.root.id, ComponentKind.BUTTON)
        self.label = project.add(project.root.id, ComponentKind.LABEL)
        self.flow = create_flow(project, self.button.id)
        self.window._replace_project(project, None)
        self.window.tabs.setCurrentIndex(1)
        QTest.qWait(100)

    def js(self, code):
        loop = QEventLoop()
        results = []

        def done(result):
            results.append(result)
            loop.quit()

        self.window.logic.page.runJavaScript(code, done)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(5000)
        loop.exec()
        timer.stop()
        self.assertTrue(results, "The JavaScript did not respond.")
        return results[0]

    def install_log(self, text="Hello from Blockly"):
        payload = json.dumps(text)
        self.js(
            """(() => {
          const ws=window.makebench.workspace;
          const hat=ws.getTopBlocks(false).find(b=>b.type==='mb_event');
          const log=ws.newBlock('mb_log','log_1');log.initSvg();log.render();
          const text=ws.newBlock('text','text_1');text.setFieldValue("""
            + payload
            + """,'TEXT');text.initSvg();text.render();
          log.getInput('VALUE').connection.connect(text.outputConnection);
          hat.getInput('DO').connection.connect(log.previousConnection);
          log.setCommentText('Block comment');
          const comment=ws.newComment('note_1');
          comment.setText('Nota solta preservada');comment.moveTo(new Blockly.utils.Coordinate(450,80));
          return true;
        })()"""
        )

    def test_01_offline_engine_and_comment_serialization(self):
        self.assertEqual(self.js("Blockly.VERSION"), "13.4.0")
        self.install_log()
        self.assertTrue(self.window.logic.flush())
        saved = self.window.project.workflows[0]
        self.assertEqual(saved["body"][0]["value"]["value"], "Hello from Blockly")
        self.assertEqual(saved["body"][0]["comment"], "Block comment")
        comments = saved["workspace"].get("workspaceComments")
        self.assertIsNotNone(comments, "Workspace comments need a serializer.")
        self.assertEqual(comments[0]["text"], "Nota solta preservada")
        line = self.window.logic.generated.lines[(saved["id"], "log_1")]
        self.window.logic._select_block(saved["id"], "log_1")
        self.assertEqual(
            self.window.logic.code.textCursor().blockNumber() + self.window.logic.code_start, line
        )

    def test_02_flush_save_reopen_and_source_is_never_executed(self):
        self.install_log("Salvar imediatamente")
        # Saving before the 220 ms debounce must also capture the blocks.
        self.window.source_editor.setPlainText(
            "raise RuntimeError('do not run')\ndef mine(ctx, value):\n    return value\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project.makebench.json"
            self.assertTrue(self.window.save_to(path))
            saved = load_project(path)
            self.assertEqual(
                saved.workflows[0]["body"][0]["value"]["value"], "Salvar imediatamente"
            )
            self.assertIn("raise RuntimeError", source_path(path).read_text())
            self.window._replace_project(saved, path)
            QTest.qWait(100)
            self.assertEqual(
                self.js("window.makebench.workspace.getBlockById('text_1').getFieldValue('TEXT')"),
                "Salvar imediatamente",
            )
            self.assertEqual(
                self.js(
                    "Blockly.serialization.workspaces.save(window.makebench.workspace).workspaceComments[0].text"
                ),
                "Nota solta preservada",
            )
            self.assertFalse(self.window.source.dirty)

    def test_03_undo_redo_restores_blocks_and_comments(self):
        self.install_log()
        self.window.logic.flush()
        self.js(
            "window.makebench.workspace.getBlockById('text_1').setFieldValue('Alterado','TEXT')"
        )
        self.window.logic.flush()
        self.window.undo()
        QTest.qWait(100)
        self.assertEqual(
            self.js("window.makebench.workspace.getBlockById('text_1').getFieldValue('TEXT')"),
            "Hello from Blockly",
        )
        self.window.redo()
        QTest.qWait(100)
        self.assertEqual(
            self.js("window.makebench.workspace.getBlockById('text_1').getFieldValue('TEXT')"),
            "Alterado",
        )

    def test_04_incomplete_draft_is_saved_without_executable_handler(self):
        self.js("const b=window.makebench.workspace.newBlock('mb_log'); b.initSvg();b.render();")
        self.window.logic.flush()
        self.assertIsNone(self.window.project.workflows[0]["body"])
        self.assertIn("loose blocks", self.window.logic.diagnostics.text())
        self.assertNotIn("def on_event", self.window.logic.generated.text)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "draft.makebench.json"
            self.assertTrue(self.window.save_to(path))
            self.window._replace_project(load_project(path), path)
            QTest.qWait(100)
            self.assertEqual(self.js("window.makebench.workspace.getTopBlocks(false).length"), 2)

    def test_05_switching_events_and_stale_updates(self):
        self.install_log()
        self.window.edit_logic(self.window.project.root.id)
        QTest.qWait(100)
        self.assertEqual(len(self.window.project.workflows), 2)
        self.assertEqual(self.window.project.workflows[0]["body"][0]["op"], "log")
        before = self.window.project.to_dict()
        self.window.logic._receive(
            json.dumps({"token": "old", "flow": self.flow["id"], "body": [], "workspace": {}})
        )
        self.assertEqual(self.window.project.to_dict(), before)
        self.window.logic.events.setCurrentIndex(0)
        QTest.qWait(100)
        self.assertEqual(
            self.js("window.makebench.workspace.getBlockById('text_1').getFieldValue('TEXT')"),
            "Hello from Blockly",
        )

    def test_06_neutral_model_overrides_conflicting_visual_state(self):
        self.install_log()
        self.window.logic.flush()
        saved = self.window.project.to_dict()
        visual = saved["workflows"][0]["workspace"]["blocks"]["blocks"][0]
        visual["inputs"]["DO"]["block"]["inputs"]["VALUE"]["block"]["fields"]["TEXT"] = (
            "Estado conflitante"
        )
        model = Project.from_dict(saved)
        self.window._replace_project(model, None)
        QTest.qWait(100)
        self.assertEqual(
            self.js("window.makebench.workspace.getBlockById('text_1').getFieldValue('TEXT')"),
            "Hello from Blockly",
        )

    def test_07_source_dirty_cancel_conflict_and_separate_undo(self):
        self.window.history.mark_saved()
        self.window.tabs.setCurrentIndex(2)
        self.window.source_editor.insertPlainText("# my function\n")
        self.assertTrue(self.window.source.dirty)
        self.window.undo()
        self.assertFalse(self.window.source.dirty)
        self.window.redo()
        self.assertTrue(self.window.source.dirty)
        with patch(
            "makebench.editor.window.QMessageBox.warning",
            return_value=QMessageBox.StandardButton.Cancel,
        ):
            original = self.window.project.id
            self.window.new_project()
        self.assertEqual(self.window.project.id, original)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.makebench.json"
            self.assertTrue(self.window.save_to(path))
            source_path(path).write_text("# external edit\n")
            with patch.object(self.window, "_show_error") as error:
                self.assertFalse(self.window.save_to(path))
            error.assert_called_once()
            self.assertEqual(source_path(path).read_text(), "# external edit\n")

    def test_08_all_operations_roundtrip_and_clean_open(self):
        project = load_project("examples/welcome/project.makebench.json")
        flow = project.workflows[1]
        self.window._replace_project(project, None)
        self.window.logic.sync(flow["id"])
        QTest.qWait(300)
        self.assertTrue(self.window.logic.flush())
        self.assertFalse(
            self.window.history.dirty, "Just opening a flow must not change the document."
        )
        compiled = json.loads(self.js("JSON.stringify(window.makebench.compileWorkspace())"))
        self.assertEqual(compiled["body"], flow["body"])
        self.assertEqual(compiled["errors"], [])
        self.assertIsNotNone(
            self.js("window.makebench.workspace.getBlockById('greet').getCommentText()")
        )

    def test_09_duplicate_preserves_workspace_notes_and_internal_references(self):
        self.install_log()
        self.window.logic.flush()
        original = self.window.project.workflows[0]
        clone = self.window.project.duplicate(self.button.id)
        copied = self.window.project.workflows[1]
        self.assertEqual(copied["event"]["component"], clone.id)
        self.window._refresh()
        self.window.logic.sync(copied["id"])
        QTest.qWait(100)
        notes = self.js(
            "Blockly.serialization.workspaces.save(window.makebench.workspace).workspaceComments[0].text"
        )
        self.assertEqual(notes, "Nota solta preservada")

    def test_10_every_operation_converts_back_to_neutral_model(self):
        project = self.window.project
        progress = project.add(project.root.id, ComponentKind.PROGRESS)
        pages = project.add(project.root.id, ComponentKind.PAGES)
        checkbox = project.add(project.root.id, ComponentKind.CHECKBOX)
        counter = 0

        def node(op, **values):
            nonlocal counter
            counter += 1
            return {"id": f"node_{counter}", "op": op, **values}

        def value(item):
            return node("literal", value=item)

        body = [
            node("assign", name="counter", value=value(0)),
            node(
                "repeat",
                count=value(3),
                body=[
                    node(
                        "assign",
                        name="counter",
                        value=node(
                            "binary",
                            operator="+",
                            left=node("variable", name="counter"),
                            right=value(1),
                        ),
                    )
                ],
            ),
            node(
                "set_text",
                component=self.label.id,
                value=node("join", left=value("Number: "), right=node("variable", name="counter")),
            ),
            node("set_enabled", component=self.button.id, value=value(False)),
            node("set_value", component=progress.id, value=value(50)),
            node("show_page", component=pages.children[0].id),
            node("log", value=node("read", component=progress.id, attribute="value")),
            node(
                "if",
                condition=node(
                    "binary",
                    operator="and",
                    left=node("read", component=checkbox.id, attribute="checked"),
                    right=value(True),
                ),
                then=[node("message", value=value("Yes"))],
                **{"else": []},
            ),
            node(
                "call",
                function="saudacao",
                value=node("read", component=self.button.id, attribute="text"),
            ),
        ]
        project.workflows[0]["body"] = body
        self.window._refresh()
        QTest.qWait(100)
        compiled = json.loads(self.js("JSON.stringify(window.makebench.compileWorkspace())"))
        self.assertEqual(compiled["errors"], [])
        self.assertEqual(compiled["body"], body)
        self.window.logic.flush()
        self.assertEqual(project.workflows[0]["body"], body)

    def test_11_keyboard_undo_and_save_include_pending_changes(self):
        self.install_log()
        self.window.logic.flush()
        self.window.history.mark_saved()
        self.js("window.makebench.workspace.getBlockById('text_1').setFieldValue('Teclado','TEXT')")
        QTest.qWait(30)
        self.assertTrue(self.window.undo_action.isEnabled())
        self.window.logic.view.setFocus()
        target = self.window.logic.view.focusProxy() or self.window.logic.view
        QTest.keyClick(target, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        QTest.qWait(100)
        self.assertEqual(
            self.js("window.makebench.workspace.getBlockById('text_1').getFieldValue('TEXT')"),
            "Hello from Blockly",
        )
        QTest.keyClick(
            target,
            Qt.Key.Key_Z,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        QTest.qWait(100)
        self.assertEqual(
            self.js("window.makebench.workspace.getBlockById('text_1').getFieldValue('TEXT')"),
            "Teclado",
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "keys.makebench.json"
            self.window.path = path
            QTest.keyClick(target, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
            QTest.qWait(100)
            self.assertTrue(path.exists())
            self.assertEqual(
                load_project(path).workflows[0]["body"][0]["value"]["value"], "Teclado"
            )

    def test_12_flush_failure_allows_explicit_discard_without_false_save(self):
        self.window.logic.ready = False
        try:
            with patch.object(self.window, "_show_error"):
                with patch(
                    "makebench.editor.window.QMessageBox.warning",
                    return_value=QMessageBox.StandardButton.Cancel,
                ):
                    self.assertFalse(self.window._confirm_discard())
                with patch(
                    "makebench.editor.window.QMessageBox.warning",
                    return_value=QMessageBox.StandardButton.Discard,
                ):
                    self.assertTrue(self.window._confirm_discard())
                with tempfile.TemporaryDirectory() as temp:
                    path = Path(temp) / "blocked.makebench.json"
                    self.assertFalse(self.window.save_to(path))
                    self.assertFalse(path.exists())
        finally:
            self.window.logic.ready = True

    def test_13_task_dialog_and_list_operations_roundtrip(self):
        counter = 0

        def node(op, **values):
            nonlocal counter
            counter += 1
            return {"id": f"new_{counter}", "op": op, **values}

        def value(item):
            return node("literal", value=item)

        body = [
            node(
                "ask",
                kind="choice",
                name="resposta",
                prompt=value("Escolha"),
                options=node("list", items=[value("A"), value("B")]),
            ),
            node("confirm", prompt=value("Continuar?")),
            node(
                "run",
                program=value("uname"),
                arguments=node("list", items=[value("-a")]),
                admin=False,
            ),
            node(
                "script",
                source=value('printf "%s\\n" "$1"'),
                arguments=node("list", items=[value("Hello with spaces")]),
                admin=True,
            ),
        ]
        self.window.project.workflows[0]["body"] = body
        self.window._refresh()
        QTest.qWait(100)
        compiled = json.loads(self.js("JSON.stringify(window.makebench.compileWorkspace())"))
        self.assertEqual(compiled["body"], body)
        self.assertEqual(compiled["errors"], [])
        self.window.logic.flush()
        self.assertIn("ctx.run_script", self.window.logic.generated.text)
        self.assertIn("admin=True", self.window.logic.generated.text)

    def test_14_run_button_executes_unsaved_snapshot_and_locates_function_error(self):
        from makebench.core.project import Project

        self.window.source_editor.setPlainText(
            'def fail(ctx, valor):\n    raise ValueError("Erro do exemplo")\n'
        )
        self.window.project.workflows[0]["body"] = [
            {
                "id": "call_failure",
                "op": "call",
                "function": "fail",
                "value": {"id": "argument", "op": "literal", "value": ""},
            }
        ]
        self.window._refresh()
        self.window.run_action.trigger()
        runtime = self.window.runtime_window
        try:
            deadline = time.monotonic() + 5
            while (
                not runtime.session.active or runtime.session.busy
            ) and time.monotonic() < deadline:
                QTest.qWait(20)
            self.assertTrue(runtime.session.active)
            runtime.view.widgets[self.button.id].click()
            while runtime.session.busy and time.monotonic() < deadline:
                QTest.qWait(20)
            self.assertEqual(runtime.last_error["block"], "call_failure")
            runtime.locate.click()
            QTest.qWait(50)
            self.assertEqual(self.window.tabs.currentIndex(), 2)
            self.assertEqual(self.window.source_editor.textCursor().blockNumber(), 1)
        finally:
            runtime.stop()
            deadline = time.monotonic() + 3
            while not runtime.session.closed and time.monotonic() < deadline:
                QTest.qWait(20)
            runtime.close()
            QTest.qWait(50)

    def test_15_multiline_editor_preserves_text_comments_and_roundtrip(self):
        self.install_log()
        self.window.logic.flush()
        script = (
            'window.makebench.setTextValue("text_1",'
            + json.dumps('primeira linha\nsegunda linha com "aspas"\n$1')
            + ")"
        )
        result = self.js("(()=>{try{return " + script + ";}catch(error){return error.stack;}})()")
        self.assertEqual(result, True)
        self.window.logic.flush()
        flow = self.window.project.workflows[0]
        self.assertEqual(
            flow["body"][0]["value"]["value"], 'primeira linha\nsegunda linha com "aspas"\n$1'
        )
        self.assertEqual(flow["body"][0]["value"]["id"], "text_1")
        self.window._refresh()
        QTest.qWait(100)
        text = json.loads(self.js('JSON.stringify(window.makebench.textValue("text_1"))'))
        self.assertEqual(text["text"], flow["body"][0]["value"]["value"])
        self.window.undo()
        QTest.qWait(100)
        self.assertEqual(
            self.js("window.makebench.workspace.getBlockById('text_1').getFieldValue('TEXT')"),
            "Hello from Blockly",
        )

    def test_16_multiline_can_replace_shadow_literal_without_losing_connection(self):
        state = {
            "type": "mb_script",
            "id": "script_shadow",
            "inputs": {
                "SOURCE": {
                    "shadow": {
                        "type": "text",
                        "id": "source_shadow",
                        "fields": {"TEXT": "printf ok"},
                    }
                },
                "ARGUMENTS": {
                    "block": {
                        "type": "lists_create_with",
                        "id": "args_shadow",
                        "extraState": {"itemCount": 0},
                    }
                },
            },
        }
        self.js(
            """(()=>{const ws=window.makebench.workspace;const hat=ws.getTopBlocks(false).find(b=>b.type==='mb_event');const b=Blockly.serialization.blocks.append("""
            + json.dumps(state)
            + """,ws);hat.getInput('DO').connection.connect(b.previousConnection);return true;})()"""
        )
        result = self.js(
            '(()=>{try{return window.makebench.setTextValue("source_shadow","printf one\\nprintf two");}catch(e){return e.stack;}})()'
        )
        self.assertEqual(result, True)
        self.window.logic.flush()
        flow = self.window.project.workflows[0]
        self.assertEqual(flow["body"][0]["source"]["value"], "printf one\nprintf two")
        self.assertEqual(flow["body"][0]["source"]["id"], "source_shadow")

    def test_17_navigation_and_scoped_variables_roundtrip(self):
        from makebench.core.navigation import add_state, add_window

        project = self.window.project
        state = add_state(project, project.root.id, "Etapa seguinte")
        other = add_window(project, "Outra janela")
        self.flow["body"] = [
            {
                "id": "scope_assign",
                "op": "assign",
                "scope": "window",
                "name": "counter",
                "value": {"id": "scope_value", "op": "literal", "value": 3},
            },
            {
                "id": "scope_log",
                "op": "log",
                "value": {
                    "id": "scope_read",
                    "op": "variable",
                    "scope": "window",
                    "name": "counter",
                },
            },
            {"id": "go_state", "op": "go_state", "state": state["id"]},
            {"id": "open_window", "op": "open_window", "window": other.id, "close_current": True},
            {"id": "close_window", "op": "close_window"},
        ]
        expected = json.loads(json.dumps(self.flow["body"]))
        self.window._refresh()
        self.window.logic.sync(self.flow["id"])
        QTest.qWait(150)
        result = json.loads(self.js("JSON.stringify(window.makebench.compileWorkspace())"))
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["body"], expected)
        self.assertIn("ctx.window_variables", self.window.logic.generated.text)
        self.assertIn("ctx.open_window", self.window.logic.generated.text)

    def test_18_flow_python_panel_uses_global_line_mapping(self):
        from makebench.core.logic import create_flow

        self.flow["body"] = [
            {
                "id": "first_log",
                "op": "log",
                "value": {"id": "first_text", "op": "literal", "value": "Primeiro"},
            }
        ]
        button = self.window.project.add(self.window.project.root.id, ComponentKind.BUTTON)
        second = create_flow(self.window.project, button.id)
        second["body"] = [
            {
                "id": "second_log",
                "op": "log",
                "value": {"id": "second_text", "op": "literal", "value": "Segundo"},
            }
        ]
        self.window._refresh()
        self.window.logic.sync(second["id"])
        QTest.qWait(100)
        text = self.window.logic.code.toPlainText()
        self.assertIn("def on_event_2(", text)
        self.assertNotIn("def on_event_1(", text)
        self.window.logic._select_block(second["id"], "second_log")
        visible = self.window.logic.code.textCursor().blockNumber() + self.window.logic.code_start
        self.assertEqual(visible, self.window.logic.generated.lines[(second["id"], "second_log")])

    def test_19_pending_script_tray_is_included_in_immediate_save(self):
        self.install_log("Texto original")
        self.window.logic.flush()
        self.window.logic._select_block(self.flow["id"], "text_1")
        self.window.logic._edit_text()
        deadline = time.monotonic() + 3
        while not getattr(self.window, "_script_target", None) and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertTrue(self.window._script_target)
        text = 'Novo texto\nSegunda linha com "aspas" e $1'
        self.window.script_editor.setPlainText(text)
        self.assertTrue(self.window.script_dirty())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.makebench.json"
            self.assertTrue(self.window.save_to(path))
            saved = load_project(path)
            self.assertEqual(saved.workflows[0]["body"][0]["value"]["value"], text)
            self.assertFalse(self.window.script_dirty())
            self.assertEqual(saved.workflows[0]["body"][0]["value"]["id"], "text_1")

    def test_20_terminal_operations_and_breakpoints_roundtrip(self):
        """Terminals keep their ID/argv/input; the menu marks the origin without running anything."""
        from makebench.core.logic_defaults import default_block

        self.install_log("Antes")
        self.window.logic.flush()
        terminal = self.window.project.add(self.window.project.root.id, ComponentKind.TERMINAL)
        self.flow["body"] = [
            default_block(op, self.window.project, self.window.project.root.id)
            for op in ("terminal_start", "terminal_send", "terminal_stop")
        ]
        expected = json.loads(json.dumps(self.flow["body"]))
        self.window._refresh()
        self.window.logic.sync(self.flow["id"])
        QTest.qWait(150)
        self.assertTrue(self.window.logic.flush())
        self.assertEqual(self.window.project.workflows[0]["body"], expected)
        block = expected[0]["id"]
        self.js(
            "bridge.toggleBreakpoint("
            + json.dumps(self.flow["id"])
            + ","
            + json.dumps(block)
            + "); true"
        )
        QTest.qWait(100)
        self.assertIn(
            {"file": "block", "flow": self.flow["id"], "block": block}, self.window.breakpoints()
        )
        self.assertIn("ctx.terminal_start(", self.window.logic.generated.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
