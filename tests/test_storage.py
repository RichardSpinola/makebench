"""Persistência real e recuperação de falhas sem perder o arquivo anterior."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from makebench.core.project import ComponentKind, Project, ProjectError
from makebench.core.storage import StorageError, load_project, save_project


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "projeto.makebench.json"

    def test_saved_document_roundtrips_with_stable_bytes(self):
        project = Project.empty("Configurações — português")
        project.add(project.root.id, ComponentKind.OUTPUT)
        save_project(project, self.path)
        first = self.path.read_bytes()
        restored = load_project(self.path)
        save_project(restored, self.path)
        self.assertEqual(first, self.path.read_bytes())
        self.assertIn("Configurações", first.decode("utf-8"))

    def test_failed_atomic_replace_preserves_original_and_cleans_temporary_file(self):
        project = Project.empty("Original")
        save_project(project, self.path)
        original = self.path.read_bytes()
        project.name = "Ainda não salvo"
        with patch("makebench.core.storage.os.replace", side_effect=OSError("Sem espaço")):
            with self.assertRaises(StorageError):
                save_project(project, self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_document_never_overwrites_a_valid_file(self):
        project = Project.empty("Original")
        save_project(project, self.path)
        original = self.path.read_bytes()
        project.name = ""
        with self.assertRaises(ProjectError):
            save_project(project, self.path)
        self.assertEqual(self.path.read_bytes(), original)

    def test_missing_corrupt_and_wrong_format_files_have_actionable_errors(self):
        with self.assertRaises(StorageError):
            load_project(self.path)
        self.path.write_text("{quebrado", encoding="utf-8")
        with self.assertRaises(StorageError):
            load_project(self.path)
        self.path.write_text(json.dumps({"format": "another.tool"}), encoding="utf-8")
        with self.assertRaises(ProjectError):
            load_project(self.path)


if __name__ == "__main__":
    unittest.main()
