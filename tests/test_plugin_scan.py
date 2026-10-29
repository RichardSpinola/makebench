# SPDX-License-Identifier: GPL-3.0-or-later
import support  # noqa: F401  (first: isolates settings and data)
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from makebench.core import plugin_scan
from makebench.editor.plugins import PluginManager


class ScanTests(unittest.TestCase):
    def test_finds_plain_uses_without_running_the_code(self):
        source = (
            "import subprocess, socket\nfrom urllib.request import urlopen\n"
            "import os\ndef f():\n    os.system('x')\n    eval('1')\n    shutil.rmtree('d')\n"
        )
        self.assertEqual(
            plugin_scan.permissions_of(source),
            {"programs", "network", "dynamic-code", "files-outside"},
        )
        self.assertEqual(plugin_scan.permissions_of("def register(api):\n    pass\n"), set())
        self.assertEqual(plugin_scan.permissions_of("def ("), {"dynamic-code"})

    def test_fingerprint_changes_with_content_and_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "plugin.py").write_text("a = 1\n")
            first = plugin_scan.folder_hash(folder)
            self.assertEqual(first, plugin_scan.folder_hash(folder))
            (folder / "plugin.py").write_text("a = 2\n")
            self.assertNotEqual(first, plugin_scan.folder_hash(folder))

    def test_manager_lists_license_declared_and_undeclared_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "net"
            folder.mkdir()
            (folder / "plugin.json").write_text(
                json.dumps({"id": "net", "api": 2, "license": "MIT", "permissions": ["programs"]})
            )
            (folder / "plugin.py").write_text("import socket, subprocess\n")
            plugin = PluginManager(Path(tmp), official=None).plugins["net"]
            self.assertEqual(plugin.license, "MIT")
            self.assertEqual(plugin.detected, ["network", "programs"])
            self.assertEqual(plugin_scan.undeclared(folder, plugin.declared), ["network"])
            self.assertFalse(plugin.enabled)


if __name__ == "__main__":
    unittest.main()
