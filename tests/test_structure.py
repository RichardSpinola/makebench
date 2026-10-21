"""Reorganização segura de subárvores, páginas e compatibilidade do formato."""

import unittest
from pathlib import Path

from makebench.core.project import ComponentKind as Kind, Project, ProjectError
from makebench.core.storage import load_project


class StructureTests(unittest.TestCase):
    def test_version_one_fixture_opens_and_saves_as_version_two(self):
        path = Path(__file__).resolve().parents[1] / "examples/script-center/project.makebench.json"
        project = load_project(path)
        self.assertEqual(project.id, "project_script_center")
        self.assertEqual(project.find("button_install").properties["text"], "Instalar um aplicativo")
        self.assertEqual(project.to_dict()["format_version"], 4)

    def test_move_keeps_ids_and_orders_insertions_before_and_after(self):
        project = Project.empty()
        first, second, third = [project.add(project.root.id, Kind.BUTTON) for _ in range(3)]
        project.move(first.id, project.root.id, 3)
        self.assertEqual([item.id for item in project.root.children], [second.id, third.id, first.id])
        project.move(first.id, project.root.id, 0)
        self.assertEqual([item.id for item in project.root.children], [first.id, second.id, third.id])
        self.assertFalse(project.move(first.id, project.root.id, 1))

    def test_cycles_and_invalid_targets_do_not_change_the_document(self):
        project = Project.empty()
        group = project.add(project.root.id, Kind.CONTAINER)
        nested = project.add(group.id, Kind.CONTAINER)
        button = project.add(group.id, Kind.BUTTON)
        before = project.to_dict()
        for node, target in ((group, nested), (group, group), (nested, button), (project.root, nested)):
            with self.subTest(node=node.id, target=target.id):
                with self.assertRaises(ProjectError):
                    project.move(node.id, target.id)
                self.assertEqual(project.to_dict(), before)

    def test_duplicate_pages_have_new_ids_and_remapped_initial_page(self):
        project = Project.empty()
        pages = project.add(project.root.id, Kind.PAGES)
        second = project.add(pages.id, Kind.PAGE)
        project.add(second.id, Kind.BUTTON)
        pages.properties["initial_page"] = second.id
        clone = project.duplicate(pages.id)
        old_ids = {node.id for node in pages.walk()}
        new_ids = {node.id for node in clone.walk()}
        self.assertFalse(old_ids & new_ids)
        self.assertEqual(clone.properties["initial_page"], clone.children[1].id)
        self.assertEqual(Project.from_dict(project.to_dict()).to_dict(), project.to_dict())

    def test_initial_page_recovers_and_last_page_cannot_be_removed_or_transferred(self):
        project = Project.empty()
        pages = project.add(project.root.id, Kind.PAGES)
        second = project.add(pages.id, Kind.PAGE)
        first_id = pages.children[0].id
        project.remove(first_id)
        self.assertEqual(pages.properties["initial_page"], second.id)
        other = project.add(project.root.id, Kind.PAGES)
        before = project.to_dict()
        with self.assertRaises(ProjectError):
            project.remove(second.id)
        with self.assertRaises(ProjectError):
            project.move(second.id, other.id)
        self.assertEqual(project.to_dict(), before)

    def test_page_structure_and_initial_reference_are_validated(self):
        project = Project.empty()
        pages = project.add(project.root.id, Kind.PAGES)
        with self.assertRaises(ProjectError):
            project.add(project.root.id, Kind.PAGE)
        with self.assertRaises(ProjectError):
            project.add(pages.id, Kind.BUTTON)
        for bad in ("missing", [], 123):
            data = project.to_dict()
            data["ui"]["children"][0]["properties"]["initial_page"] = bad
            with self.subTest(bad=bad), self.assertRaises(ProjectError):
                Project.from_dict(data)

    def test_invalid_image_paths_and_grid_columns_are_rejected(self):
        project = Project.empty()
        image = project.add(project.root.id, Kind.IMAGE)
        for path in ("/tmp/secret.png", "assets/../../secret.png", "https://example.com/image.png", 123):
            image.properties["source"] = path
            with self.subTest(path=path), self.assertRaises(ProjectError):
                Project.from_dict(project.to_dict())
        image.properties["source"] = ""
        project.root.properties["columns"] = 0
        with self.assertRaises(ProjectError):
            Project.from_dict(project.to_dict())
