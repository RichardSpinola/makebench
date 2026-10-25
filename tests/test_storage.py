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

    def test_format_upgrade_reports_the_backup_actually_created(self):
        """O aviso de atualização usa o nome real da cópia, de qualquer formato anterior."""
        example = (
            Path(__file__).resolve().parents[1] / "examples/script-center/project.makebench.json"
        )
        self.path.write_bytes(example.read_bytes())
        project = load_project(self.path)
        project.application["name"] = "Atualizado"
        backup = save_project(project, self.path)
        self.assertEqual(backup, self.path.with_name(self.path.name + ".bak-v1"))
        self.assertEqual(backup.read_bytes(), example.read_bytes())
        self.assertIsNone(save_project(load_project(self.path), self.path))
        project = load_project(self.path)
        project.python_files = ["makebench_user/__init__.py"]
        backup = save_project(project, self.path)
        self.assertEqual(backup.name, self.path.name + ".bak-v5")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["format_version"], 8)

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
