# SPDX-License-Identifier: GPL-3.0-or-later
"""Interface language: English source strings, complete pt-BR catalog and switching."""

import support  # noqa: F401  (first: isolates settings and data)
import ast
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

from makebench import i18n

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "makebench"
CATALOG = SOURCE / "locale" / "pt_BR" / "makebench.po"
PORTUGUESE = re.compile(r"[ãõçáéíóúâêôàÃÕÇÁÉÍÓÚÂÊÔ]")
# Files that intentionally contain Portuguese data (starter source, Qt fallback labels).
PORTUGUESE_DATA = {"i18n.py", "core/source.py", "ui/dialogs.py", "editor/settings.py"}


def tr_literals(tree):
    """Ids of string literals passed to tr()/ntr(), which are English msgids."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            count = {"tr": 1, "ntr": 2}.get(node.func.id, 0)
            ids.update(id(arg) for arg in node.args[:count])
    return ids


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(i18n.set_language, "en")

    def test_every_source_msgid_has_a_portuguese_translation(self):
        catalog = i18n.read_po(CATALOG)
        missing = []
        for path in SOURCE.rglob("*.py"):
            if path == SOURCE / "i18n.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    count = {"tr": 1, "ntr": 2}.get(node.func.id, 0)
                    for arg in node.args[:count]:
                        self.assertIsInstance(arg, ast.Constant, f"{path}:{node.lineno}")
                        if arg.value not in catalog:
                            missing.append(f"{path.relative_to(ROOT)}:{node.lineno} {arg.value!r}")
        self.assertEqual(missing, [])

    def test_placeholders_and_edges_match_between_languages(self):
        for msgid, msgstr in i18n.read_po(CATALOG).items():
            self.assertEqual(
                sorted(re.findall(r"\{[^}]*\}", msgid)),
                sorted(re.findall(r"\{[^}]*\}", msgstr)),
                msgid,
            )
            self.assertEqual(
                msgid[: len(msgid) - len(msgid.lstrip())],
                msgstr[: len(msgstr) - len(msgstr.lstrip())],
                msgid,
            )
            self.assertEqual(msgid[len(msgid.rstrip()) :], msgstr[len(msgstr.rstrip()) :], msgid)

    def test_no_untranslated_portuguese_literal_outside_tr(self):
        found = []
        for path in SOURCE.rglob("*.py"):
            relative = path.relative_to(SOURCE).as_posix()
            if relative in PORTUGUESE_DATA or relative.startswith("templates/"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            wrapped = tr_literals(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if id(node) not in wrapped and PORTUGUESE.search(node.value):
                        found.append(f"{relative}:{node.lineno} {node.value[:60]!r}")
        self.assertEqual(found, [])

    def test_switching_language_translates_and_unknown_falls_back_to_english(self):
        self.assertEqual(i18n.set_language("pt_BR"), "pt_BR")
        self.assertEqual(i18n.tr("Open project…"), "Abrir projeto…")
        self.assertEqual(
            i18n.ntr("{count} event", "{count} events", 2).format(count=2), "2 eventos"
        )
        self.assertEqual(
            i18n.tr("A text that is not in the catalog"), "A text that is not in the catalog"
        )
        self.assertEqual(i18n.set_language("xx_YY"), "en")
        self.assertEqual(i18n.tr("Open project…"), "Open project…")

    def test_blockly_page_has_portuguese_for_every_label(self):
        text = (SOURCE / "web" / "logic.js").read_text(encoding="utf-8")
        # Compare decoded string values, exactly as JavaScript sees them at run time.
        labels = {
            ast.literal_eval("'" + raw + "'")
            for raw in re.findall(r"T\('((?:[^'\\]|\\.)*)'\)", text)
        }
        dictionary = json.loads(re.search(r"const PT_BR = (\{.*?\});\n", text, re.S).group(1))
        self.assertEqual(sorted(labels - set(dictionary)), [])
        for entry, locale in (("index.html", "en.js"), ("index.pt_BR.html", "pt-br.js")):
            self.assertIn(
                "vendor/blockly/" + locale, (SOURCE / "web" / entry).read_text(encoding="utf-8")
            )

    def test_editor_starts_in_portuguese_when_chosen(self):
        """A fresh process applies the language before any translated label is built."""
        script = (
            "from makebench.__main__ import configure_language\n"
            "configure_language()\n"
            "from PySide6.QtWidgets import QApplication\n"
            "app = QApplication([])\n"
            "from makebench.editor.window import MainWindow\n"
            "w = MainWindow()\n"
            "print(w.mode_buttons['logic'].text(), '|', w.run_action.text(), '|', w.project.name)\n"
            "w.close()\n"
        )
        env = dict(os.environ, MAKEBENCH_LANGUAGE="pt_BR", QT_QPA_PLATFORM="offscreen")
        env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=120
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("Lógica | Testar aplicativo | Novo aplicativo", result.stdout)


if __name__ == "__main__":
    unittest.main()
