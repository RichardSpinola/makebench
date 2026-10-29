# SPDX-License-Identifier: GPL-3.0-or-later
"""The Qt table keeps rows in a model: large lists fill fast and selection still works."""

import support  # noqa: F401  (first: isolates settings and data)
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from makebench.ui.renderer import (
    append_table_row,
    configure_table,
    selected_table_record,
    selected_table_row,
    set_table_rows,
    table_contents,
)
from makebench.ui.table import RecordTable

app = QApplication.instance() or QApplication([])


class TableTests(unittest.TestCase):
    def setUp(self):
        self.table = RecordTable()
        configure_table(self.table, ["Name", "Age"])
        self.picked = []
        self.table.itemSelectionChanged.connect(lambda: self.picked.append(True))

    def tearDown(self):
        self.table.deleteLater()

    def test_rows_records_selection_and_contents(self):
        set_table_rows(self.table, [["Ana", 31], ["Bruno"]], ids=[7, 8])
        append_table_row(self.table, ["Caio", 5], record=9)
        self.assertEqual((self.table.rowCount(), self.table.columnCount()), (3, 2))
        self.assertEqual(selected_table_record(self.table), None)
        self.assertEqual(selected_table_row(self.table), [])
        self.table.selectRow(1)
        self.assertEqual(self.picked, [True])
        self.assertEqual(selected_table_record(self.table), 8)
        self.assertEqual(selected_table_row(self.table), ["Bruno", ""])
        self.assertEqual(
            table_contents(self.table),
            {"headers": ["Name", "Age"], "rows": [["Ana", "31"], ["Bruno", ""], ["Caio", "5"]]},
        )

    def test_application_changes_do_not_count_as_the_person_choosing(self):
        set_table_rows(self.table, [["Ana"], ["Bruno"]])
        self.table.selectRow(0)
        self.picked.clear()
        set_table_rows(self.table, [["Caio"]])
        self.assertEqual(self.picked, [])
        self.assertEqual(selected_table_record(self.table), None)

    def test_fifty_thousand_rows_fill_quickly(self):
        rows = [[f"name {i}", i, "2026-10-29", "x" * 20] for i in range(50_000)]
        configure_table(self.table, ["Name", "Number", "Date", "Note"])
        self.table.show()
        start = time.perf_counter()
        set_table_rows(self.table, rows)
        app.processEvents()
        self.assertLess(time.perf_counter() - start, 0.5)
        self.assertEqual(self.table.rowCount(), 50_000)


class LineReaderTests(unittest.TestCase):
    def test_lines_split_across_chunks_and_limit(self):
        from makebench.core.lines import LineReader

        reader = LineReader(limit=10)
        self.assertEqual(reader.feed(b"ab"), [])
        self.assertEqual(reader.feed(b"c\nde\nf"), [b"abc", b"de"])
        self.assertEqual(reader.feed(b"\n"), [b"f"])
        with self.assertRaises(ValueError):
            reader.feed(b"x" * 11)
        with self.assertRaises(ValueError):
            LineReader(limit=3).feed(b"abcd\n")


class IconCacheTests(unittest.TestCase):
    def test_vector_icons_are_rendered_once_per_color(self):
        from PySide6.QtWidgets import QApplication
        from makebench.ui import icons

        app = QApplication.instance() or QApplication([])
        theme = type("Theme", (), {"tokens": {"text": "#112233"}})()
        previous = getattr(app, "makebench_theme", None)
        app.makebench_theme = theme
        try:
            first = icons.vector_icon("save")
            self.assertIs(first, icons.vector_icon("save"))
            theme.tokens = {"text": "#ddeeff"}
            self.assertIsNot(first, icons.vector_icon("save"))
        finally:
            if previous is None:
                del app.makebench_theme
            else:
                app.makebench_theme = previous


if __name__ == "__main__":
    unittest.main()
