# SPDX-License-Identifier: GPL-3.0-or-later
"""Document integrity, compatibility and change history."""

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

    def test_future_version_is_rejected_without_migrating_silently(self):
        data = Project.empty().to_dict()
        data["format_version"] = 99
        with self.assertRaisesRegex(ProjectError, "Unsupported project version"):
            Project.from_dict(data)

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
