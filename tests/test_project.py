# SPDX-License-Identifier: GPL-3.0-or-later
"""Document integrity, compatibility and change history."""

import support  # noqa: F401  (first: isolates settings and data)
import unittest

from makebench.core.history import History
from makebench.core.project import ComponentKind, LayoutKind, Project, ProjectError


class ProjectTests(unittest.TestCase):
    def test_roundtrip_preserves_layout_ids_and_future_data(self):
        project = Project.empty("Boas-vindas — Linux")
        container = project.add(project.root.id, ComponentKind.CONTAINER)
        container.layout = LayoutKind.FREE
        button = project.add(container.id, ComponentKind.BUTTON)
        button.properties["text"] = "Começar"
        button.geometry.update(x=31, y=47)
        project.workflows = [{"id": "on_click", "comment": "Não executar ao abrir"}]
        project.metadata = {"author_notes": ["Preservar", "acentuação"]}

        restored = Project.from_dict(project.to_dict())

        self.assertEqual(restored.to_dict(), project.to_dict())
        restored.find(button.id).properties["text"] = "Alterado"
        self.assertEqual(button.properties["text"], "Começar")

    def test_number_and_slider_validate_limits_and_write_format_10(self):
        from makebench.core.project import clamp_range

        project = Project.empty("Ranges")
        number = project.add(project.root.id, ComponentKind.NUMBER)
        slider = project.add(project.root.id, ComponentKind.SLIDER)
        self.assertEqual(project.to_dict()["format_version"], 10)
        self.assertEqual(Project.from_dict(project.to_dict()).find(number.id).kind, "number")
        for node, bad in [
            (number, {"value": 500}),
            (number, {"minimum": 5, "maximum": 1}),
            (number, {"step": 0}),
            (number, {"decimals": 7}),
            (number, {"value": 1.5}),  # a fraction while decimals is 0
            (number, {"value": True}),
            (slider, {"decimals": 1}),
        ]:
            before = dict(node.properties)
            node.properties.update(bad)
            with self.assertRaises(ProjectError):
                Project.from_dict(project.to_dict())
            node.properties = before
        number.properties.update(decimals=2, value=1.25, step=0.25)
        self.assertEqual(
            Project.from_dict(project.to_dict()).find(number.id).properties["value"], 1.25
        )
        number.properties.update(maximum=1)  # the value no longer fits
        clamp_range(number)
        self.assertEqual(number.properties["value"], 1)
        Project.from_dict(project.to_dict())

    def test_choice_options_are_validated(self):
        project = Project.empty("Choice")
        choice = project.add(project.root.id, ComponentKind.CHOICE)
        self.assertEqual(choice.properties["text"], "")
        choice.properties.update(options=["a", "b"], text="b")
        Project.from_dict(project.to_dict())
        for bad in ({"text": "z"}, {"options": "ab"}, {"options": ["a", 3]}):
            before = dict(choice.properties)
            choice.properties.update(bad)
            with self.assertRaises(ProjectError):
                Project.from_dict(project.to_dict())
            choice.properties = before

    def test_date_must_be_a_real_iso_day(self):
        project = Project.empty("Date")
        date = project.add(project.root.id, ComponentKind.DATE)
        date.properties["text"] = "2026-02-28"
        Project.from_dict(project.to_dict())
        for bad in ("2026-02-30", "28/02/2026", "", "20260228", 5):
            date.properties["text"] = bad
            with self.assertRaises(ProjectError):
                Project.from_dict(project.to_dict())

    def test_future_version_is_rejected_without_migrating_silently(self):
        data = Project.empty().to_dict()
        data["format_version"] = 99
        with self.assertRaisesRegex(ProjectError, "Unsupported project version"):
            Project.from_dict(data)

    def test_node_editor_projects_are_refused_with_a_clear_message(self):
        data = Project.empty().to_dict()
        data["format_version"] = 7
        data["workflows"] = [{"id": "f", "name": "Old", "editor": "nodes", "graph": {}}]
        with self.assertRaisesRegex(ProjectError, "node editor"):
            Project.from_dict(data)

    def test_programming_choice_writes_format_9_and_is_validated(self):
        project = Project.empty()
        self.assertIsNone(project.programming)
        self.assertLess(project.to_dict()["format_version"], 9)
        project.metadata["programming"] = "python"
        data = project.to_dict()
        self.assertEqual(data["format_version"], 9)
        self.assertEqual(Project.from_dict(data).programming, "python")
        data["metadata"]["programming"] = "nodes"
        with self.assertRaisesRegex(ProjectError, "programming"):
            Project.from_dict(data)
        data["metadata"]["programming"] = "blocks"
        data["format_version"] = 8
        with self.assertRaisesRegex(ProjectError, "programming"):
            Project.from_dict(data)

    def test_old_projects_infer_blocks_python_or_ask(self):
        from makebench.core.project import infer_programming
        from makebench.core.source import DEFAULT_SOURCES

        project = Project.empty()
        self.assertIsNone(infer_programming(project, DEFAULT_SOURCES["pt_BR"]))
        self.assertIsNone(infer_programming(project, ""))
        self.assertEqual(infer_programming(project, "def salvar(ctx):\n    pass\n"), "python")
        project.python_files = ["tools"]
        self.assertEqual(infer_programming(project), "python")
        project.workflows = [{"id": "f", "name": "Start", "body": None}]
        self.assertEqual(infer_programming(project, "def salvar(ctx):\n    pass\n"), "blocks")
        project.metadata["programming"] = "python"
        self.assertEqual(infer_programming(project), "python")

    def test_duplicate_component_ids_are_rejected(self):
        project = Project.empty()
        project.add(project.root.id, ComponentKind.BUTTON)
        data = project.to_dict()
        data["ui"]["children"][0]["id"] = project.root.id
        with self.assertRaisesRegex(ProjectError, "repeated"):
            Project.from_dict(data)

    def test_invalid_property_and_geometry_types_are_rejected(self):
        project = Project.empty()
        button = project.add(project.root.id, ComponentKind.BUTTON)
        for invalid_geometry in (
            {"x": -1},
            {"width": 0},
            {"height": True},
            {"x": 2**100},
        ):
            with self.subTest(invalid_geometry=invalid_geometry):
                data = project.to_dict()
                data["ui"]["children"][0]["geometry"].update(invalid_geometry)
                with self.assertRaises(ProjectError):
                    Project.from_dict(data)
        button.properties["text"] = 42
        with self.assertRaisesRegex(ProjectError, "must be text"):
            Project.from_dict(project.to_dict())

    def test_leaf_cannot_contain_children_and_window_cannot_be_nested(self):
        project = Project.empty()
        button = project.add(project.root.id, ComponentKind.BUTTON)
        with self.assertRaises(ProjectError):
            project.add(button.id, ComponentKind.LABEL)
        with self.assertRaises(ProjectError):
            project.add(project.root.id, ComponentKind.WINDOW)

    def test_removing_container_removes_descendants_but_not_siblings(self):
        project = Project.empty()
        container = project.add(project.root.id, ComponentKind.CONTAINER)
        nested = project.add(container.id, ComponentKind.BUTTON)
        sibling = project.add(project.root.id, ComponentKind.LABEL)

        self.assertEqual(project.remove(container.id), project.root.id)
        self.assertIsNone(project.find(nested.id))
        self.assertIsNotNone(project.find(sibling.id))
        with self.assertRaises(ProjectError):
            project.remove(project.root.id)

    def test_history_handles_save_undo_redo_and_divergent_edits(self):
        project = Project.empty()
        history = History(project)
        button = project.add(project.root.id, ComponentKind.BUTTON)
        history.push(project)
        history.mark_saved()
        button.properties["text"] = "Executar"
        history.push(project)
        self.assertTrue(history.dirty)
        project = history.undo()
        self.assertFalse(history.dirty)
        self.assertEqual(project.find(button.id).properties["text"], "New button")
        project = history.redo()
        self.assertTrue(history.dirty)
        project = history.undo()
        project.name = "Outro caminho"
        history.push(project)
        self.assertFalse(history.can_redo)

    def test_deletion_with_unvalidated_workflow_references_is_blocked(self):
        project = Project.empty()
        button = project.add(project.root.id, ComponentKind.BUTTON)
        project.workflows = [{"component_id": button.id}]
        with self.assertRaisesRegex(ProjectError, "reference validation"):
            project.remove(button.id)
        self.assertIsNotNone(project.find(button.id))


class HistoryLabelTests(unittest.TestCase):
    def test_labels_follow_undo_and_redo(self):
        project = Project.empty("Labels")
        history = History(project)
        self.assertEqual((history.undo_label, history.redo_label), ("", ""))
        project.add(project.root.id, ComponentKind.BUTTON)
        history.push(project, "Add button")
        project.name = "Renamed"
        history.push(project, "Rename project")
        self.assertEqual(history.undo_label, "Rename project")
        history.undo()
        self.assertEqual((history.undo_label, history.redo_label), ("Add button", "Rename project"))

    def test_limit_drops_oldest_changes_without_touching_saved_state(self):
        project = Project.empty("Limit")
        history = History(project, limit=3)
        for number in range(6):
            project.name = f"Name {number}"
            history.push(project, f"Change {number}")
        undone = 0
        while history.can_undo:
            history.undo()
            undone += 1
        self.assertEqual(undone, 3)
        self.assertEqual(history.redo_label, "Change 3")
        self.assertTrue(history.dirty)


if __name__ == "__main__":
    unittest.main()
