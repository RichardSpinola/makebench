# SPDX-License-Identifier: GPL-3.0-or-later
"""The promises in docs/compatibility.md: old files open, new features are explicit."""

import support  # noqa: F401  (first: isolates settings and data)
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from makebench.core.project import FORMAT_VERSION, Project, ProjectError
from makebench.editor.plugins import API_VERSION, SUPPORTED_APIS, PluginManager

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class FormatPolicyTests(unittest.TestCase):
    def test_a_plain_project_stays_at_the_oldest_format_that_can_hold_it(self):
        """Saving never promotes a project beyond what its features need."""
        project = Project.empty("Plain")
        self.assertLess(project.to_dict()["format_version"], FORMAT_VERSION)
        again = Project.from_dict(json.loads(json.dumps(project.to_dict())))
        self.assertEqual(again.to_dict(), project.to_dict())

    def test_every_older_version_is_read_and_a_newer_one_is_refused_clearly(self):
        data = Project.empty("Old").to_dict()
        for version in range(1, FORMAT_VERSION + 1):
            data["format_version"] = version
            Project.from_dict(json.loads(json.dumps(data)))
        for bad in (0, FORMAT_VERSION + 1, "12", None):
            data["format_version"] = bad
            with self.assertRaises(ProjectError) as caught:
                Project.from_dict(data)
            self.assertIn("compatible version", str(caught.exception))

    def test_shipped_examples_open_and_save_without_changes(self):
        """Examples are real projects: opening and saving them is lossless (formats below 4 are saved as 4)."""
        files = sorted(EXAMPLES.glob("*/project.makebench.json"))
        self.assertTrue(files)
        for path in files:
            with self.subTest(path.parent.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                saved = Project.from_dict(data).to_dict()
                if data["format_version"] < 4:  # formats 1 to 3 are saved as 4
                    saved["format_version"] = data["format_version"]
                self.assertEqual(saved, data)


class PluginApiPolicyTests(unittest.TestCase):
    def test_the_current_api_is_supported_and_an_unknown_one_is_never_loaded(self):
        self.assertIn(API_VERSION, SUPPORTED_APIS)
        with tempfile.TemporaryDirectory() as tmp:
            for plugin_id, api in (("future", API_VERSION + 1), ("past", 0), ("text", "2")):
                folder = Path(tmp) / plugin_id
                folder.mkdir()
                (folder / "plugin.json").write_text(json.dumps({"id": plugin_id, "api": api}))
                (folder / "plugin.py").write_text("raise SystemExit('must not run')\n")
            manager = PluginManager(Path(tmp), official=None)
            for plugin_id in ("future", "past", "text"):
                self.assertTrue(manager.plugins[plugin_id].incompatible, plugin_id)
                self.assertFalse(manager.plugins[plugin_id].enabled)


if __name__ == "__main__":
    unittest.main()
