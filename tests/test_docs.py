# SPDX-License-Identifier: GPL-3.0-or-later
"""The documentation check finds real mistakes and the site has none."""

import support  # noqa: F401  (first: isolates settings and data)
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docs_check", ROOT / "checks" / "docs.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)

PLUGIN = '```json\n{"id": "%s", "name": "X", "api": %d}\n```\n'


class DocsCheckTests(unittest.TestCase):
    def check(self, files: dict[str, str]) -> list[str]:
        """Run the static checks over a small docs folder."""
        with tempfile.TemporaryDirectory() as folder:
            for name, text in files.items():
                path = Path(folder) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            with mock.patch.object(docs, "DOCS", Path(folder)):
                return docs.missing_twins() + docs.missing_images() + docs.broken_examples()

    def test_the_site_has_no_problems(self):
        """Every page has its twin, images exist and examples are valid."""
        self.assertEqual(docs.missing_twins() + docs.missing_images() + docs.broken_examples(), [])

    def test_finds_missing_translations(self):
        problems = self.check({"a.md": "", "b.pt-BR.md": "", "c.md": "", "c.pt-BR.md": ""})
        self.assertEqual(len(problems), 2)
        self.assertIn("a.md", problems[0])
        self.assertIn("b.pt-BR.md", problems[1])

    def test_finds_missing_images(self):
        problems = self.check({"a.md": "![x](images/none.png)", "a.pt-BR.md": ""})
        self.assertEqual(problems, ["a.md: missing image images/none.png"])

    def test_finds_broken_python_but_skips_generated_reference(self):
        broken = "Text\n\n!!! note\n    ```python\n    def f(:\n    ```\n"
        good = "```python\nif True:\n    pass\n```\n"
        problems = self.check(
            {
                "a.md": broken,
                "a.pt-BR.md": good,
                "reference/r.md": "```python\nctx.f(x: str) -> int\n```\n",
                "reference/r.pt-BR.md": "",
            }
        )
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("a.md:4:"), problems)

    def test_validates_plugin_and_theme_examples(self):
        theme = '```json\n{"format": "mbtheme", "version": 1, "name": "T"}\n```\n'
        problems = self.check(
            {"a.md": PLUGIN % ("good", 1), "a.pt-BR.md": PLUGIN % ("Bad id", 1) + theme}
        )
        self.assertEqual(len(problems), 2, problems)
        self.assertEqual(
            self.check({"a.md": PLUGIN % ("old", 99), "a.pt-BR.md": ""})[0][:7], "a.md:1:"
        )


if __name__ == "__main__":
    unittest.main()
