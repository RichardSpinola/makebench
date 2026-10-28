# SPDX-License-Identifier: GPL-3.0-or-later
"""Qt editing journeys for Python files and common properties."""

import support  # noqa: F401  (first: isolates settings and data)
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from makebench.core.project import Project, ComponentKind, LayoutKind
from makebench.core.storage import load_project


class CodeWorkspaceInterfaceTests(unittest.TestCase):
    """Real editing of multiple files and collective properties with history."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from makebench.editor.window import MainWindow

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(
            os.environ,
            {
                "XDG_STATE_HOME": str(self.root / "state"),
                "XDG_CONFIG_HOME": str(self.root / "config"),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.window = MainWindow(Project.empty())
        self.window.recovery_timer.stop()
        self.window._created_here = True
        self.window._show_error = lambda message, *_: self.fail(str(message))

    def tearDown(self):
        self.window.history.mark_saved()
        self.window.source.mark_saved()
        self.window.close()
        self.app.processEvents()
        self.window.deleteLater()
        self.app.processEvents()

    def test_tabs_module_undo_save_reopen_and_generated_readonly(self):
        w = self.window
        w.add_code_module("makebench_user/helpers.py", "# comentário\n")
        editor = w.module_editors["makebench_user/helpers.py"]
        editor.appendPlainText("value = 2")
        self.assertIn("value = 2", w.source.modules["makebench_user/helpers.py"].text)
        w.undo()
        self.assertNotIn("value = 2", w.source.modules["makebench_user/helpers.py"].text)
        w.redo()
        path = self.root / "project.makebench.json"
        self.assertTrue(w.save_to(path))
        self.assertFalse(w.source.dirty)
        w._replace_project(load_project(path), path)
        self.assertIn("value = 2", w.module_editors["makebench_user/helpers.py"].toPlainText())
        self.assertTrue(w.generated_editor.isReadOnly())

    def test_batch_mixed_properties_single_undo_preserves_widgets_and_zoom(self):
        from PySide6.QtWidgets import QLineEdit

        w = self.window
        w.project.root.layout = LayoutKind.FREE
        a = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        b = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        a.properties["text"] = "A"
        b.properties["text"] = "B"
        w.history.push(w.project)
        w._refresh()
        w.set_mode("design")
        w.select_multiple([a.id, b.id])
        field = w.inspector.findChild(QLineEdit, "batch_text")
        self.assertEqual(field.placeholderText(), "Multiple values")
        frames = {name: widget for name, widget in w.canvas._frames.items()}
        zoom = w.zoom_view.zoom
        before = w.history._index
        w.change_multiple_properties("text", "Mesmo texto")
        self.assertEqual(w.history._index, before + 1)
        self.assertEqual(w.project.find(a.id).properties["text"], "Mesmo texto")
        self.assertEqual(w.project.find(b.id).properties["text"], "Mesmo texto")
        self.assertEqual(frames, w.canvas._frames)
        self.assertEqual(w.zoom_view.zoom, zoom)
        self.assertEqual(w.selected_ids, {a.id, b.id})
        w.undo()
        self.assertEqual(w.project.find(a.id).properties["text"], "A")
        self.assertEqual(w.project.find(b.id).properties["text"], "B")

    def test_incompatible_layout_disables_alignment_with_explanation(self):
        from PySide6.QtWidgets import QToolButton

        w = self.window
        a = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        b = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        w._refresh()
        w.select_multiple([a.id, b.id])
        button = w.inspector.findChild(QToolButton, "selection_left")
        self.assertFalse(button.isEnabled())
        self.assertIn("Free", button.toolTip())

    def test_module_diagnostics_navigate_and_snapshot_changes(self):
        w = self.window
        w.add_code_module(
            "makebench_user/helpers.py", "def calculate(value):\n    return value+1\n"
        )
        before = w.execution_fingerprint()
        w.module_editors["makebench_user/helpers.py"].setPlainText("def calculate(\n")
        w._update_actions()
        self.assertNotEqual(w.execution_fingerprint(), before)
        targets = [w.problems.item(i) for i in range(w.problems.count())]
        item = next(
            i for i in targets if i.data(256).get("source_file") == "makebench_user/helpers.py"
        )
        w.go_to_problem(item)
        self.assertIs(w.active_code_editor(), w.module_editors["makebench_user/helpers.py"])

    def test_blocks_project_flags_python_calls_in_problems(self):
        w = self.window
        w.project.metadata.update(programming="blocks", logic_version=1)
        w.project.workflows = [
            {
                "id": "flow-a",
                "name": "Start",
                "event": {"kind": "start", "component": w.project.root.id},
                "body": [{"id": "call-a", "op": "call", "function": "greet", "value": None}],
                "workspace": {},
            }
        ]
        w.sync_problems()
        targets = [w.problems.item(i).data(256) for i in range(w.problems.count())]
        self.assertIn({"flow": "flow-a", "block": "call-a"}, targets)
        labels = [w.problems.item(i).text() for i in range(w.problems.count())]
        self.assertTrue(any("calls Python" in label for label in labels))

    def test_problems_and_map_show_collections(self):
        w = self.window
        w.project.metadata.update(programming="blocks", logic_version=1)
        w.project.metadata["collections"] = [
            {
                "id": "c1",
                "name": "Livros",
                "fields": [{"id": "f1", "name": "titulo", "type": "text"}],
            }
        ]
        lit = {"id": "v", "op": "literal", "value": "x"}
        w.project.workflows = [
            {
                "id": "flow-a",
                "name": "Start",
                "event": {"kind": "start", "component": w.project.root.id},
                "body": [
                    {"id": "b1", "op": "data_add", "collection": "Livros", "values": []},
                    {"id": "b2", "op": "data_add", "collection": "Fantasma", "values": []},
                    {
                        "id": "b3",
                        "op": "data_add",
                        "collection": "Livros",
                        "values": [{"field": "nada", "value": lit}],
                    },
                ],
                "workspace": {},
            }
        ]
        w.sync_problems()
        labels = [w.problems.item(i).text() for i in range(w.problems.count())]
        self.assertTrue(any("Fantasma" in label for label in labels), labels)
        self.assertTrue(any("nada" in label for label in labels), labels)
        self.assertFalse(any("b1" in label for label in labels))
        w.history.push(w.project)
        w.set_mode("map")
        w.map_panel.sync()
        outline = w.map_panel.outline
        group = next(
            outline.topLevelItem(i)
            for i in range(outline.topLevelItemCount())
            if outline.topLevelItem(i).text(0) == "Collections"
        )
        self.assertTrue(group.child(0).text(0).startswith("Livros"))
        self.assertEqual(group.child(0).child(0).text(0).split(" →")[0], "Start")

    def test_logic_area_opens_blocks_or_python_by_project(self):
        w = self.window
        self.assertNotIn("code", w.mode_buttons)
        w.project.metadata.update(programming="python")
        w.set_mode("logic")
        self.assertEqual(w.tabs.currentIndex(), 2)
        self.assertTrue(w.mode_buttons["logic"].isChecked())
        w.project.metadata.update(programming="blocks", logic_version=1)
        w.project.workflows = [
            {
                "id": "flow-a",
                "name": "Start",
                "event": {"kind": "start", "component": w.project.root.id},
                "body": [],
                "workspace": {},
            }
        ]
        w.set_mode("logic")
        self.assertEqual(w.tabs.currentIndex(), 1)
        w.logic.sync()
        events = w.logic.outline.topLevelItem(0)
        self.assertEqual(events.childCount(), 1)
        self.assertEqual(events.child(0).data(0, 256), "flow-a")
        self.assertFalse(w.logic.code_box.isVisibleTo(w.logic))
        w.logic.view_python.setChecked(True)
        self.assertTrue(w.logic.code_box.isVisibleTo(w.logic))

    def test_python_events_create_functions_list_them_and_flag_missing_ones(self):
        w = self.window
        w.project.metadata["programming"] = "python"
        button = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        button.properties["text"] = "Save"
        w._refresh()
        w.source_editor.setPlainText("")
        w.edit_logic(button.id)
        flow = w.project.workflows[0]
        self.assertEqual(flow["function"], "on_save_click")
        self.assertIn("def on_save_click(ctx):", w.source_editor.toPlainText())
        self.assertEqual(w.tabs.currentIndex(), 2)
        self.assertEqual(w.code_events.count(), 1)
        self.assertIn("on_save_click()", w.code_events.item(0).text())
        w.source_editor.setPlainText("")
        w._update_code()
        w.sync_problems()
        labels = [w.problems.item(i).text() for i in range(w.problems.count())]
        self.assertTrue(any("on_save_click() not found" in label for label in labels))

    def test_block_functions_are_created_listed_and_protected_while_called(self):
        w = self.window
        w.project.metadata["programming"] = "blocks"
        button = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        w._refresh()
        w.save_block_function("", "total", ["price", "amount"])
        function = w.project.metadata["functions"][0]
        self.assertEqual(w.logic.flow_id, function["id"])
        groups = [
            w.logic.outline.topLevelItem(i) for i in range(w.logic.outline.topLevelItemCount())
        ]
        self.assertEqual(groups[-1].child(0).text(0), "total(price, amount)")
        self.assertFalse(w.logic.state_filter.isEnabled())
        from makebench.core.logic import create_flow

        create_flow(w.project, button.id)["body"] = [
            {
                "id": "c",
                "op": "call_function",
                "function": function["id"],
                "args": [
                    {"id": "a", "op": "literal", "value": 2},
                    {"id": "b", "op": "literal", "value": 3},
                ],
            }
        ]
        w.history.push(w.project)
        with patch.object(w, "_show_error") as shown:
            w.save_block_function(function["id"], "total", ["price"])
            w.remove_flow(function["id"])
        self.assertEqual(shown.call_count, 2)
        w.save_block_function(function["id"], "sum_up", ["x", "y"])
        self.assertEqual(function["name"], "sum_up")
        self.assertIn("fn_sum_up(ctx, 2, 3)", w.logic.generated.text)
        w.project.workflows.clear()
        w.remove_flow(function["id"])
        self.assertNotIn("functions", w.project.metadata)

    def test_block_modules_group_events_and_functions_in_the_sidebar(self):
        w = self.window
        w.project.metadata["programming"] = "blocks"
        button = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        from makebench.core.logic import create_flow, modules

        flow = create_flow(w.project, button.id)
        w.history.push(w.project)
        w._refresh()
        w.save_block_function("", "total", [])
        function = w.project.metadata["functions"][0]
        w.move_to_module(flow["id"], "  Checkout   page ")
        w.move_to_module(function["id"], "Checkout page")
        self.assertEqual(flow["module"], "Checkout page")
        self.assertEqual(modules(w.project), ["Checkout page"])
        outline = w.logic.outline
        groups = [outline.topLevelItem(i) for i in range(outline.topLevelItemCount())]
        self.assertEqual(groups[-1].text(0), "Modules")
        folder = groups[-1].child(0)
        self.assertEqual(folder.text(0), "Checkout page")
        self.assertEqual(folder.childCount(), 2)
        self.assertEqual(groups[0].childCount(), 0)
        with patch.object(w, "_show_error") as shown:
            w.move_to_module(flow["id"], "x" * 61)
        shown.assert_called_once()
        self.assertEqual(flow["module"], "Checkout page")
        w.move_to_module(flow["id"], "")
        self.assertNotIn("module", flow)

    def test_map_lists_events_and_the_functions_they_call(self):
        w = self.window
        w.project.metadata["programming"] = "blocks"
        button = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        w._refresh()
        w.save_block_function("", "greet", ["name"])
        function = w.project.metadata["functions"][0]
        from makebench.core.logic import create_flow

        flow = create_flow(w.project, button.id)
        flow["body"] = [
            {
                "id": "c",
                "op": "call_function",
                "function": function["id"],
                "args": [{"id": "a", "op": "literal", "value": "Ada"}],
            }
        ]
        w.history.push(w.project)
        w.set_mode("map")
        w.map_panel.sync()
        outline = w.map_panel.outline
        window_item = outline.topLevelItem(0)
        from makebench.editor.map_panel import LOGIC_ROLE

        event = next(
            window_item.child(i)
            for i in range(window_item.childCount())
            if window_item.child(i).data(0, LOGIC_ROLE) == flow["id"]
        )
        self.assertEqual(event.child(0).text(0), "greet(name)")
        functions = outline.topLevelItem(outline.topLevelItemCount() - 1)
        self.assertEqual(functions.text(0), "Functions")
        w.map_panel.outline_open(event.child(0))
        self.assertEqual(w._mode, "logic")
        self.assertEqual(w.logic.flow_id, function["id"])
        w.set_mode("map")
        w.map_panel.outline_open(event)
        self.assertEqual(w.logic.flow_id, flow["id"])

    def test_convert_to_python_keeps_a_copy_of_the_blocks(self):
        w = self.window
        w.project.metadata["programming"] = "blocks"
        button = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        from makebench.core.logic import create_flow

        create_flow(w.project, button.id)["body"] = [
            {"id": "b1", "op": "log", "value": {"id": "b2", "op": "literal", "value": "hi"}}
        ]
        w.history.push(w.project)
        w._refresh()
        path = self.root / "project.makebench.json"
        self.assertTrue(w.save_to(path))
        self.assertTrue(w.convert_to_python(confirm=False))
        self.assertEqual(w.project.programming, "python")
        self.assertIn("function", w.project.workflows[0])
        self.assertIn("def on_new_button_click(ctx):", w.source_editor.toPlainText())
        self.assertTrue((self.root / "project.makebench.json.bak-blocks").exists())
        self.assertEqual(load_project(path).programming, "python")

    def test_completion_enter_undo_and_component_suggestions(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        w = self.window
        w.show()
        w.set_mode("code")
        editor = w.source_editor
        editor.setPlainText("def action(ctx, value):\n    ctx.term")
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        editor.setFocus()
        QTest.qWait(20)
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(w._entry_assist.popup.isVisible())
        self.assertEqual(w._entry_assist.popup.count(), 3)
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.assertIn("ctx.terminal_send", editor.toPlainText())
        self.assertFalse(w._entry_assist.popup.isVisible())
        w.undo()
        self.assertTrue(editor.toPlainText().endswith("ctx.term"))
        node = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        node.properties["code_name"] = "executar"
        editor.setPlainText("ctx.set_text('exe")
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w._entry_assist.popup.count(), 1)
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.assertIn(node.id, editor.toPlainText())

    def test_f12_and_outline_use_active_module(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        w = self.window
        w.show()
        w.add_code_module(
            "makebench_user/helpers.py", "def calculate(value):\n    return value+1\n"
        )
        w.source_editor.setPlainText(
            "from makebench_user.helpers import calculate\n\ndef action(ctx, value):\n    return calculate(value)\n"
        )
        w.open_code_file("@actions", 4)
        cursor = w.source_editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.Right, cursor.MoveMode.MoveAnchor, 15)
        w.source_editor.setTextCursor(cursor)
        QTest.keyClick(w.source_editor, Qt.Key.Key_F12)
        self.assertIs(w.active_code_editor(), w.module_editors["makebench_user/helpers.py"])
        self.assertIn("calculate", w.function_outline.item(0).text())
        self.assertEqual(
            w.code_tree.currentItem().data(0, Qt.ItemDataRole.UserRole), "makebench_user/helpers.py"
        )
        with patch(
            "makebench.editor.development.QInputDialog.getText", return_value=("other", True)
        ):
            w.new_function()
        self.assertIn("def other", w.source.modules["makebench_user/helpers.py"].text)
        self.assertNotIn("def other", w.source.text)

    def test_batch_defaults_enabled_and_grid_keyboard(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QCheckBox

        w = self.window
        w.project.root.layout = LayoutKind.FREE
        a = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        b = w.project.add(w.project.root.id, ComponentKind.BUTTON)
        w._refresh()
        w.set_mode("design")
        w.select_multiple([a.id, b.id])
        self.assertIsNotNone(w.inspector.findChild(QCheckBox, "batch_enabled"))
        w.change_multiple_properties("enabled", False)
        self.assertFalse(w.project.find(a.id).properties["enabled"])
        self.assertFalse(w.project.find(b.id).properties["enabled"])
        w.select_multiple([a.id])
        before = w.project.find(a.id).geometry["x"]
        w.snap_check.setChecked(True)
        QTest.keyClick(w.canvas, Qt.Key.Key_Right)
        self.assertEqual(w.project.find(a.id).geometry["x"], before + 8)
        w.snap_check.setChecked(False)
        QTest.keyClick(w.canvas, Qt.Key.Key_Right)
        self.assertEqual(w.project.find(a.id).geometry["x"], before + 9)
