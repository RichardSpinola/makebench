# SPDX-License-Identifier: GPL-3.0-or-later
"""The exported runtime stays small: no editor, plugins, themes or MIT-incompatible code."""

import support  # noqa: F401  (first: isolates settings and data)
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
FOOTPRINT = ROOT / "checks" / "footprint.py"


class RuntimeContentsTests(unittest.TestCase):
    def test_exported_source_leaves_the_editor_side_out(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("footprint", FOOTPRINT)
        footprint = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(footprint)
        for backend in ("qt", "gtk"):
            with self.subTest(backend), tempfile.TemporaryDirectory() as target:
                with zipfile.ZipFile(footprint.export(backend, target)) as archive:
                    names = archive.namelist()
                for forbidden in ("editor/", "pluginpack/", "themepack/"):
                    self.assertFalse(
                        [n for n in names if f"makebench/{forbidden}" in n], (backend, forbidden)
                    )
                own = "runtime" if backend == "qt" else "gtk_runtime"
                self.assertTrue([n for n in names if f"makebench/{own}/" in n], backend)


if __name__ == "__main__":
    unittest.main()
