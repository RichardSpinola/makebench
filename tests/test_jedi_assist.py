# SPDX-License-Identifier: GPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path

from makebench.editor import jedi_assist as assist


@unittest.skipUnless(assist.available(), "jedi is not installed")
class JediAssistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def names(self, source, line, column):
        return {s.name for s in assist.completions(source, self.root, None, line, column)}

    def test_ctx_methods_are_suggested_with_docs(self):
        source = "def on_click(ctx, value):\n    ctx.se\n"
        names = self.names(source, 2, 9)
        self.assertTrue({"set_text", "set_enabled", "set_value"} <= names)
        text = assist.documentation("def f(ctx):\n    ctx.set_text\n", self.root, None, 2, 10)
        self.assertIn("text of a control", text)

    def test_signature_and_definition_in_local_module(self):
        (self.root / "helpers.py").write_text("def double(number):\n    return number * 2\n")
        source = "from helpers import double\ndouble(\n"
        path = self.root / "actions.py"
        self.assertIn("number", assist.signature(source, self.root, path, 2, 7))
        target = assist.definition(source, self.root, path, 2, 2)
        self.assertEqual(target.path, self.root / "helpers.py")
        self.assertEqual(target.line, 0)

    def test_rename_within_file(self):
        path = self.root / "a.py"
        source = "total = 1\nprint(total)\n"
        result = assist.rename(source, self.root, path, 1, 1, "amount")
        self.assertEqual(result, "amount = 1\nprint(amount)\n")

    def test_analysis_never_runs_project_code(self):
        marker = self.root / "written.txt"
        (self.root / "sneaky.py").write_text(f"open({str(marker)!r}, 'w').write('x')\nvalue = 1\n")
        assist.completions("import sneaky\nsneaky.", self.root, None, 2, 7)
        assist.definition("import sneaky\nsneaky.value", self.root, None, 2, 8)
        self.assertFalse(marker.exists())

    def test_snippets(self):
        self.assertIn("on_click", assist.snippets("on_"))
        self.assertEqual(assist.snippets(""), {})


if __name__ == "__main__":
    unittest.main()
