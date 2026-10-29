# SPDX-License-Identifier: GPL-3.0-or-later
"""Static checks for user Python: syntax with hints, names, ctx and component ids."""

import support  # noqa: F401  (first: isolates settings and data)
import unittest

from makebench.core.code_index import CodeIndex
from makebench.core.python_check import ctx_api, diagnose, explain


def messages(text, ids=()):
    return [item["message"] for item in diagnose(text, ids)]


class PythonCheckTests(unittest.TestCase):
    def test_syntax_error_is_explained_and_marked_as_error(self):
        found = diagnose("if x\n    pass\n")
        self.assertEqual(found[0]["line"], 1)
        self.assertEqual(found[0]["severity"], "error")
        self.assertIn("colon", found[0]["hint"])
        self.assertTrue(explain("unterminated string literal (detected at line 1)"))
        self.assertEqual(explain("something nobody knows"), "")

    def test_several_syntax_errors_are_listed(self):
        found = diagnose('def a(:\n    pass\n\n\nprint("x"\n\n\nz = 1 +\n')
        self.assertGreaterEqual(len(found), 2)
        self.assertEqual(found, sorted(found, key=lambda e: (e["line"], e["column"])))

    def test_undefined_names_and_suggestions(self):
        self.assertEqual(messages("def f(ctx):\n    print(nome)\n"), ["Name not defined: nome"])
        self.assertEqual(messages("import os\ndef f(ctx, a=1):\n    return os, a, len\n"), [])
        self.assertEqual(messages("from os import *\nprint(zz)\n"), [])

    def test_ctx_methods_data_and_component_ids(self):
        context, data = ctx_api()
        self.assertIn("message", context)
        self.assertIn("add", data)
        found = diagnose('def f(ctx):\n    ctx.mesage("x")\n')
        self.assertEqual(found[0]["message"], "ctx has no mesage")
        self.assertIn("message", found[0]["hint"])
        self.assertEqual(messages('def f(ctx):\n    ctx.data.ad("x")\n'), ["ctx.data has no ad"])
        text = 'def f(ctx):\n    ctx.set_text("lable1", "a")\n    ctx.set_text("label1", "b")\n'
        found = diagnose(text, {"label1"})
        self.assertEqual([e["message"] for e in found], ["No component with the id lable1"])
        self.assertIn("label1", found[0]["hint"])

    def test_code_index_lists_every_check_and_caches_them(self):
        index = CodeIndex()
        index.update("def f(ctx):\n    ctx.mesage(nome)\n")
        self.assertEqual(len(index.errors), 2)
        self.assertTrue(all(e["file"] and "severity" in e for e in index.errors))
        cached = index.checks["@actions"]
        index.update("def f(ctx):\n    ctx.mesage(nome)\n")
        self.assertIs(index.checks["@actions"], cached)

    def test_tidy_cleans_lines_but_keeps_strings_and_broken_files(self):
        from makebench.core.python_check import tidy

        text = 'def f():\t\n\tx = 1   \n\n\n\n\n\ts = """a  \n\tb\t\n"""\n\n\n'
        self.assertEqual(tidy(text), 'def f():\n    x = 1\n\n\n\ts = """a  \n\tb\t\n"""\n')
        self.assertEqual(tidy('x = f"""{1}  \n"""'), 'x = f"""{1}  \n"""\n')
        self.assertEqual(tidy("def (\n  "), "def (\n  ")
        self.assertEqual(tidy(""), "")


class ExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_every_recipe_is_valid_python_inside_a_function(self):
        from makebench.editor.code_examples import examples

        recipes = examples()
        self.assertGreaterEqual(len(recipes), 12)
        for title, code in recipes:
            with self.subTest(title=title):
                body = "".join("    " + line + "\n" for line in code.splitlines())
                found = diagnose("def go(ctx):\n" + body)
                self.assertEqual([e for e in found if e["severity"] == "error"], [])
                self.assertFalse(any("ctx" in e["message"] for e in found))

    def test_insert_example_follows_the_cursor_indentation(self):
        from PySide6.QtGui import QTextCursor

        from makebench.editor.code import CodeEditor

        editor = CodeEditor()
        recipe = "if ok:\n    done()\n"
        editor.setPlainText("def go(ctx):\n    ")
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.insert_example(recipe)
        self.assertEqual(editor.toPlainText(), "def go(ctx):\n    if ok:\n        done()")
        editor.setPlainText("def go(ctx):\n    x = 1")
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.insert_example(recipe)
        self.assertEqual(
            editor.toPlainText(), "def go(ctx):\n    x = 1\n    if ok:\n        done()"
        )
        editor.undo()
        self.assertEqual(editor.toPlainText(), "def go(ctx):\n    x = 1")
        cursor = editor.textCursor()
        cursor.setPosition(len("def go(ctx):\n"))
        editor.setTextCursor(cursor)
        editor.insert_example(recipe)
        self.assertEqual(
            editor.toPlainText(), "def go(ctx):\n    if ok:\n        done()\n    x = 1"
        )
        editor.deleteLater()


if __name__ == "__main__":
    unittest.main()
