# SPDX-License-Identifier: GPL-3.0-or-later
"""Regressions of real redesign flows: references, assets and text editing."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
import unittest
from makebench.core.project import Project, ComponentKind, ProjectError
from makebench.core.navigation import (
    add_window,
    add_state,
    connect_navigation,
    find_navigation_block,
    remove_navigation_block,
)
from makebench.core.logic import create_flow, validate
from makebench.core.behaviors import TEMPLATES, behavior_template, append_behavior


class WorkflowTests(unittest.TestCase):
    """The map and the templates edit the same document as the runnable handlers."""

    def setUp(self):
        """A window with a field/button and a second interface are known references."""
        self.project = Project.empty()
        self.field = self.project.add(self.project.root.id, ComponentKind.TEXT_INPUT)
        self.button = self.project.add(self.project.root.id, ComponentKind.BUTTON)
        self.other = add_window(self.project, "Painel")
        self.state = add_state(self.project, self.project.root.id, "Etapa 2")

    def test_templates_validate_roundtrip_and_preserve_comments(self):
        """Every template is a valid, portable, independent and inert action."""
        p = self.project
        flow = create_flow(p, self.button.id)
        flow["workspace"] = {"workspaceComments": [{"text": "Comentário preservado", "id": "note"}]}
        for kind, _ in TEMPLATES:
            append_behavior(flow, behavior_template(kind, p, p.root.id))
        validate(p)
        copy = Project.from_dict(p.to_dict())
        self.assertEqual(copy.to_dict(), p.to_dict())
        self.assertEqual(flow["workspace"]["workspaceComments"][0]["text"], "Comentário preservado")
        text = p.to_dict().__repr__()
        self.assertIn(self.field.id, text)
        self.assertIn(self.other.id, text)
        blocks = behavior_template("run", p, p.root.id)
        self.assertFalse(blocks[0]["admin"])
        with self.assertRaises(ProjectError):
            behavior_template("read_field", p, self.other.id)

    def test_nested_transition_edit_and_delete_preserve_other_actions(self):
        """Editing a general connection changes no filters and destroys no conditions/comments."""
        p = self.project
        flow = create_flow(p, self.button.id)
        condition = behavior_template("validate_input", p, p.root.id)[0]
        flow["body"] = [condition]
        original = {
            "id": "existing-navigation",
            "op": "open_window",
            "window": self.other.id,
            "close_current": False,
            "comment": "depois da validação",
        }
        condition["then"].append(original)
        flow["workspace"] = {
            "workspaceComments": [{"text": "Nota da área", "id": "workspace-note"}]
        }
        updated = connect_navigation(
            p,
            p.root.id + "|@default",
            self.button.id,
            p.root.id + "|" + self.state["id"],
            replace=(flow["id"], original["id"]),
        )
        self.assertIs(updated, flow)
        self.assertNotIn("states", flow)
        self.assertEqual(len(p.workflows), 1)
        self.assertEqual(original["comment"], "depois da validação")
        self.assertEqual(original["op"], "go_state")
        self.assertIs(find_navigation_block(p, flow["id"], original["id"])[1], original)
        validate(p)
        remove_navigation_block(p, flow["id"], original["id"])
        validate(p)
        self.assertEqual(len(condition["then"]), 1)
        self.assertEqual(flow["workspace"]["workspaceComments"][0]["text"], "Nota da área")

    def test_cross_window_targets_only_initial_state_and_existing_scope(self):
        """A window opens in its initial state; the map never invents unrunnable transitions."""
        p = self.project
        other_state = add_state(p, self.other.id, "Ready")
        with self.assertRaises(ProjectError):
            connect_navigation(
                p, p.root.id + "|@default", self.button.id, self.other.id + "|" + other_state["id"]
            )
        self.assertEqual(p.workflows, [])
        flow = create_flow(p, self.button.id)
        connect_navigation(
            p, p.root.id + "|@default", self.button.id, self.other.id + "|@default", True
        )
        self.assertEqual(len(p.workflows), 1)
        self.assertEqual(flow["body"][0]["window"], self.other.id)
        validate(p)

    def test_state_specific_connections_match_the_runtime_priority(self):
        """A connection is not added to the general handler when another one serves the state."""
        from makebench.core.navigation import navigation_edges, effective_edge_states

        p = self.project
        general = create_flow(p, self.button.id)
        general["body"] = behavior_template("open_window", p, p.root.id)
        specific = create_flow(p, self.button.id, states=[self.state["id"]])
        result = connect_navigation(
            p, p.root.id + "|" + self.state["id"], self.button.id, p.root.id + "|@default"
        )
        self.assertIs(result, specific)
        validate(p)
        edge = next(e for e in navigation_edges(p) if e["flow"] == general["id"])
        self.assertEqual(effective_edge_states(p, edge), ["@default"])

    def test_button_icons_survive_portable_bundle(self):
        """Save/share includes button icons, not only images and window icons."""
        from makebench.core.bundle import write_bundle, read_bundle
        from makebench.core.storage import load_project

        p = self.project
        self.button.properties.update(icon="assets/button.svg", tooltip="Abrir painel")
        image = b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16"/></svg>'
        self.assertIn("assets/button.svg", p.asset_paths())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "shared.zip"
            write_bundle(p, "# fonte preservada\n", lambda _: image, archive)
            path = read_bundle(archive, root / "imported")
            copy = load_project(path)
            self.assertEqual(copy.to_dict(), p.to_dict())
            self.assertEqual((path.parent / "assets/button.svg").read_bytes(), image)


class CodeToolsTests(unittest.TestCase):
    """Replacement, history, delimiters and own text stay local and inert."""

    @classmethod
    def setUpClass(cls):
        """Widgets use the existing application or an offscreen one."""
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_replace_all_is_literal_and_one_undo(self):
        """Text containing the search causes no loop or extra replacements; undo is single."""
        from makebench.editor.code import CodeEditor

        editor = CodeEditor()
        editor.setPlainText('valor = "a"\n# a\n')
        editor.find_text.setText("a")
        editor.replace_text.setText("a$()\\n")
        before = editor.toPlainText()
        editor.replace_all()
        self.assertIn("a$()\\n", editor.toPlainText())
        editor.undo()
        self.assertEqual(editor.toPlainText(), before)
        editor.close()

    def test_delimiters_ignore_strings_comments_and_handle_unicode(self):
        """Quotes/comments do not break pairing; Qt positions account for UTF-16."""
        from makebench.editor.code import CodeEditor

        editor = CodeEditor()
        editor.setPlainText('s = "😀 ["\nx = (1 + [2]) # )\n')
        pairs = editor.delimiters()
        self.assertEqual(len(pairs), 4)
        for start, end in pairs.items():
            self.assertEqual(pairs[end], start)
        editor.setPlainText("x = (1 + [2])\ny = (\n")
        self.assertEqual(len(editor.delimiters()), 4)
        editor.close()

    def test_indentation_keeps_multiline_selection_and_undo(self):
        """Tab on a selection keeps every line and undoes in one operation."""
        from makebench.editor.code import CodeEditor
        from PySide6.QtGui import QTextCursor

        editor = CodeEditor()
        before = "valor = 1\nprint(valor)\n"
        editor.setPlainText(before)
        editor.selectAll()
        editor.indent_selection()
        self.assertEqual(editor.toPlainText(), "    valor = 1\n    print(valor)\n")
        editor.undo()
        self.assertEqual(editor.toPlainText(), before)
        editor.close()

    def test_drawer_keeps_all_pages_and_visible_output_after_reparenting(self):
        """Output stays visible and does not erase Problems/Script when the drawer is rebuilt."""
        from makebench.editor.window import MainWindow

        window = MainWindow(Project.empty())
        window.recovery_timer.stop()
        window.show()
        window.drawer.show()
        window.drawer.setCurrentIndex(0)
        self.app.processEvents()
        try:
            self.assertEqual(
                [window.drawer.tabText(i) for i in range(window.drawer.count())],
                ["Output", "Problems", "Script", "Tasks", "Error", "Terminal", "Debug", "Search"],
            )
            window.add_output("stdout", "saída real\n")
            window.add_output("stderr", "aviso real\n")
            self.assertTrue(window.output_log.isVisible())
            self.assertIn("saída real", window.output_log.toPlainText())
            window.output_filter.setCurrentIndex(window.output_filter.findData("stderr"))
            self.assertIn("aviso real", window.output_log.toPlainText())
            self.assertNotIn("saída real", window.output_log.toPlainText())
            window.drawer.setCurrentIndex(2)
            self.assertTrue(window.script_editor.isVisible())
            window.drawer.setCurrentIndex(1)
            self.assertTrue(window.problems.isVisible())
        finally:
            window.history.mark_saved()
            window.source.mark_saved()
            window.close()
            window.deleteLater()
            self.app.processEvents()
