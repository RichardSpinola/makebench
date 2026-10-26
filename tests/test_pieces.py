# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import json
import tempfile
import unittest
from pathlib import Path

from makebench.core import pieces
from makebench.core.assets import AssetStore
from makebench.core.project import ComponentKind, Project, ProjectError, create_component


class PiecesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "lib"
        self.project = Project("Demo", create_component(ComponentKind.WINDOW))
        self.window = self.project.root
        self.box = self.project.add(self.window.id, ComponentKind.CONTAINER)
        self.project.add(self.box.id, ComponentKind.BUTTON)

    def test_save_and_insert_with_new_ids(self):
        piece = pieces.make_piece(self.project, self.box.id, "My box")
        path = pieces.save_piece(piece, self.folder)
        self.assertEqual(pieces.list_pieces(self.folder), [("My box", path)])
        copy = pieces.insert_piece(self.project, self.window.id, pieces.read_piece(path))
        old = {node.id for node in self.box.walk()}
        self.assertFalse(old & {node.id for node in copy.walk()})
        self.assertEqual(len(copy.children), 1)

    def test_invalid_name_and_selection(self):
        with self.assertRaises(ProjectError):
            pieces.make_piece(self.project, self.box.id, "  ")
        with self.assertRaises(ProjectError):
            pieces.make_piece(self.project, self.window.id, "Window")

    def test_bad_file_is_refused(self):
        self.folder.mkdir()
        bad = self.folder / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ProjectError):
            pieces.read_piece(bad)
        bad.write_text(json.dumps({"format": "other"}), encoding="utf-8")
        with self.assertRaises(ProjectError):
            pieces.read_piece(bad)
        self.assertEqual(pieces.list_pieces(self.folder), [])

    def test_assets_travel(self):
        image = Path(self.tmp.name) / "a.png"
        image.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
            )
        )
        source = AssetStore(Path(self.tmp.name) / "one")
        picture = self.project.add(self.box.id, ComponentKind.IMAGE)
        picture.properties["source"] = source.import_image(image)
        piece = pieces.make_piece(self.project, self.box.id, "With image", source)
        self.assertIn(picture.properties["source"], piece["assets"])
        target = AssetStore(Path(self.tmp.name) / "two")
        copy = pieces.insert_piece(self.project, self.window.id, piece, target)
        stored = [n for n in copy.walk() if n.kind == ComponentKind.IMAGE][0]
        self.assertTrue(target.read(stored.properties["source"]))

    def test_builtin_pieces_insert(self):
        for piece in pieces.builtin_pieces():
            pieces.insert_piece(self.project, self.window.id, piece)


if __name__ == "__main__":
    unittest.main()
