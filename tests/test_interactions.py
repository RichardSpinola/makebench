# SPDX-License-Identifier: GPL-3.0-or-later
"""Real Qt interactions: dragging, resizing, pages and portable images."""

import support  # noqa: F401  (first: isolates settings and data)
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from makebench.core.project import ComponentKind as Kind, LayoutKind, Project
from makebench.core.storage import load_project
from makebench.editor.assets import AssetStore
from makebench.editor.drag import mime_for
from makebench.editor.window import MainWindow


class InteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._finish_field_edit()
        self.window.history.mark_saved()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def load(self, project):
        self.window._replace_project(project, None)
        self.app.processEvents()

    def drop(self, widget, payload, point, action=Qt.DropAction.CopyAction):
        mime = mime_for(payload)
        enter = QDragEnterEvent(
            point, action, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
        )
        self.app.sendEvent(widget, enter)
        event = QDropEvent(
            QPointF(point), action, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
        )
        self.app.sendEvent(widget, event)
        self.app.processEvents()
        return event.isAccepted()

    def move_mouse(self, widget, global_point):
        local = widget.mapFromGlobal(global_point)
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(local),
            QPointF(global_point),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.app.sendEvent(widget, event)
        self.app.processEvents()

    def release_mouse(self, widget, global_point):
        event = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(widget.mapFromGlobal(global_point)),
            QPointF(global_point),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.app.sendEvent(widget, event)
        self.app.processEvents()

    def test_palette_drop_adds_a_component_and_one_undo_removes_it(self):
        project = self.window.project
        frame = self.window.canvas._frames[project.root.id]
        self.assertTrue(self.drop(frame, {"mode": "new", "kind": "button"}, QPoint(40, 30)))
        self.assertEqual(len(self.window.project.root.children), 1)
        button_id = self.window.project.root.children[0].id
        self.assertEqual(self.window.selected_id, button_id)
        self.window.undo()
        self.assertIsNone(self.window.project.find(button_id))
        self.assertFalse(self.window.history.dirty)

    def test_canvas_reorders_and_tree_reparents_without_losing_ids(self):
        project = Project.empty()
        first = project.add(project.root.id, Kind.BUTTON)
        second = project.add(project.root.id, Kind.BUTTON)
        group = project.add(project.root.id, Kind.CONTAINER)
        self.load(project)
        payload = {"mode": "move", "id": second.id, "project": project.id}
        frame = self.window.canvas._frames[first.id]
        self.assertTrue(self.drop(frame, payload, QPoint(12, 2), Qt.DropAction.MoveAction))
        self.assertEqual(self.window.project.root.children[0].id, second.id)
        item = self.window._tree_items[group.id]
        point = self.window.tree.visualItemRect(item).center()
        self.assertTrue(
            self.drop(self.window.tree.viewport(), payload, point, Qt.DropAction.MoveAction)
        )
        self.assertEqual(self.window.project.parent_of(second.id).id, group.id)
        self.window.undo()
        self.assertEqual(self.window.project.parent_of(second.id).id, project.root.id)

    def test_free_move_is_live_then_committed_as_one_history_entry(self):
        project = Project.empty()
        project.root.layout = LayoutKind.FREE
        button = project.add(project.root.id, Kind.BUTTON)
        self.load(project)
        frame = self.window.canvas._frames[button.id]
        origin = frame.mapToGlobal(QPoint(30, 20))
        QTest.mousePress(frame, Qt.MouseButton.LeftButton, pos=QPoint(30, 20))
        self.move_mouse(frame, origin + QPoint(40, 32))
        self.move_mouse(frame, origin + QPoint(72, 56))
        self.assertEqual(self.window.project.find(button.id).geometry["x"], 16)
        self.assertFalse(self.window.history.dirty)
        self.release_mouse(frame, origin + QPoint(72, 56))
        self.assertEqual(self.window.project.find(button.id).geometry["x"], 88)
        self.assertEqual(self.window.project.find(button.id).geometry["y"], 72)
        self.window.undo()
        self.assertEqual(self.window.project.find(button.id).geometry["x"], 16)
        self.assertFalse(self.window.history.can_undo)

    def test_resize_handle_changes_size_and_escape_cancels_the_next_gesture(self):
        project = Project.empty()
        project.root.layout = LayoutKind.FREE
        button = project.add(project.root.id, Kind.BUTTON)
        self.load(project)
        self.window._select(button.id)
        frame = self.window.canvas._frames[button.id]
        handle = next(h for h in frame.handles if h.property("resizeEdge") == "se")
        origin = handle.mapToGlobal(QPoint(4, 4))
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))
        self.move_mouse(handle, origin + QPoint(68, 36))
        self.release_mouse(handle, origin + QPoint(68, 36))
        current = self.window.project.find(button.id).geometry
        self.assertEqual((current["width"], current["height"]), (288, 80))
        before = self.window.project.to_dict()
        frame = self.window.canvas._frames[button.id]
        minimum = frame.parentWidget().minimumSize()
        origin = frame.mapToGlobal(QPoint(30, 20))
        QTest.mousePress(frame, Qt.MouseButton.LeftButton, pos=QPoint(30, 20))
        self.move_mouse(frame, origin + QPoint(1200, 900))
        QTest.keyClick(self.window.canvas, Qt.Key.Key_Escape)
        self.release_mouse(frame, origin + QPoint(1200, 900))
        self.assertEqual(self.window.project.to_dict(), before)
        self.assertEqual(frame.parentWidget().minimumSize(), minimum)

    def test_duplicate_and_keyboard_nudge_are_saved_and_undoable(self):
        project = Project.empty()
        project.root.layout = LayoutKind.FREE
        button = project.add(project.root.id, Kind.BUTTON)
        self.load(project)
        self.window._select(button.id)
        self.window.duplicate_action.trigger()
        clone_id = self.window.selected_id
        self.assertNotEqual(clone_id, button.id)
        original_x = self.window.project.find(clone_id).geometry["x"]
        QTest.keyClick(self.window.canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.window.project.find(clone_id).geometry["x"], original_x + 80)
        path = self.root / "document.makebench.json"
        self.assertTrue(self.window.save_to(path))
        self.assertEqual(load_project(path).find(clone_id).geometry["x"], original_x + 80)
        self.window.undo()
        self.assertEqual(self.window.project.find(clone_id).geometry["x"], original_x)
        self.window.undo()
        self.assertIsNone(self.window.project.find(clone_id))

    def test_page_navigation_is_not_an_edit_and_tree_reveals_hidden_page(self):
        project = Project.empty()
        pages = project.add(project.root.id, Kind.PAGES)
        second = project.add(pages.id, Kind.PAGE)
        button = project.add(second.id, Kind.BUTTON)
        initial_id = pages.properties["initial_page"]
        self.load(project)
        tabs = self.window.canvas._tabs[pages.id]
        QTest.mouseClick(
            tabs.tabBar(), Qt.MouseButton.LeftButton, pos=tabs.tabBar().tabRect(1).center()
        )
        self.assertEqual(self.window.selected_id, second.id)
        self.assertFalse(self.window.history.dirty)
        self.assertEqual(self.window.project.find(pages.id).properties["initial_page"], initial_id)
        tabs.setCurrentIndex(0)
        self.window._select(button.id)
        self.assertEqual(tabs.currentIndex(), 1)
        self.window.add_page()
        new_page_id = self.window.selected_id
        self.assertEqual(self.window.canvas._tabs[pages.id].count(), 3)
        self.assertEqual(len(self.window.project.find(pages.id).children), 3)
        self.window.undo()
        self.assertIsNone(self.window.project.find(new_page_id))

    def test_delete_in_text_field_does_not_remove_a_component(self):
        project = Project.empty()
        button = project.add(project.root.id, Kind.BUTTON)
        self.load(project)
        self.window._select(button.id)
        field = self.window.inspector.findChild(QLineEdit, "property_text")
        field.setFocus()
        field.setCursorPosition(0)
        QTest.keyClick(field, Qt.Key.Key_Delete)
        self.assertIsNotNone(self.window.project.find(button.id))

    def test_image_survives_original_deletion_save_as_reopen_and_undo(self):
        source = self.root / "original.png"
        image = QImage(32, 24, QImage.Format.Format_RGB32)
        image.fill(QColor("seagreen"))
        self.assertTrue(image.save(str(source)))
        project = Project.empty()
        node = project.add(project.root.id, Kind.IMAGE)
        self.load(project)
        self.window._select(node.id)
        with patch(
            "makebench.editor.window.QFileDialog.getOpenFileName", return_value=(str(source), "")
        ):
            self.window.choose_image(node.id)
        original = source.read_bytes()
        source.unlink()
        first = self.root / "first"
        second = self.root / "second"
        first.mkdir()
        second.mkdir()
        source_path = self.window.project.find(node.id).properties["source"]
        self.assertTrue(self.window.save_to(first / "project.makebench.json"))
        self.assertTrue(self.window.save_to(second / "project.makebench.json"))
        self.assertEqual((second / source_path).read_bytes(), original)
        restored = load_project(second / "project.makebench.json")
        self.assertEqual(
            AssetStore(second).read(restored.find(node.id).properties["source"]), original
        )
        self.window.clear_image(node.id)
        self.window.undo()
        self.assertEqual(self.window.project.find(node.id).properties["source"], source_path)

    def test_invalid_and_cross_document_drags_are_ignored(self):
        frame = self.window.canvas._frames[self.window.project.root.id]
        payload = {"mode": "move", "id": self.window.project.root.id, "project": "another"}
        self.assertFalse(self.drop(frame, payload, QPoint(20, 20), Qt.DropAction.MoveAction))
        mime = QMimeData()
        mime.setText("not a Makebench component")
        event = QDragEnterEvent(
            QPoint(20, 20),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.app.sendEvent(frame, event)
        self.assertFalse(event.isAccepted())
        self.assertFalse(self.window.history.dirty)

    def test_drop_on_free_area_preserves_pointer_offset_and_snaps_to_grid(self):
        project = Project.empty()
        project.root.layout = LayoutKind.FREE
        container = project.add(project.root.id, Kind.CONTAINER)
        button = project.add(container.id, Kind.BUTTON)
        self.load(project)
        payload = {
            "mode": "move",
            "project": project.id,
            "id": button.id,
            "offset_x": 20,
            "offset_y": 8,
        }
        frame = self.window.canvas._frames[project.root.id]
        self.assertTrue(self.drop(frame, payload, QPoint(500, 280), Qt.DropAction.MoveAction))
        moved = self.window.project.find(button.id)
        self.assertEqual(self.window.project.parent_of(button.id).id, project.root.id)
        self.assertEqual((moved.geometry["x"], moved.geometry["y"]), (480, 272))
        self.window.undo()
        self.assertEqual(self.window.project.parent_of(button.id).id, container.id)
