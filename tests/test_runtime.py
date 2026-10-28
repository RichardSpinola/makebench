# SPDX-License-Identifier: GPL-3.0-or-later
"""Real execution of local fixtures, with no authentication or system changes."""

import support  # noqa: F401  (first: isolates settings and data)
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox, QLineEdit
from makebench.core.logic import create_flow
from makebench.core.project import ComponentKind, Project
from makebench.runtime.window import RuntimeWindow


def literal(identifier, value):
    return {"id": identifier, "op": "literal", "value": value}


def log(identifier, text):
    return {"id": identifier, "op": "log", "value": literal(identifier + "_value", text)}


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = Project.empty("Teste de execução")
        self.button = self.project.add(self.project.root.id, ComponentKind.BUTTON)
        self.label = self.project.add(self.project.root.id, ComponentKind.LABEL)
        self.flow = create_flow(self.project, self.button.id)
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            for dialog in list(window.dialogs):
                dialog.reject()
            if not window.session.closed:
                self.assertFalse(
                    window.session.admin_active,
                    "Teste não pode deixar tarefa administrativa pendente.",
                )
                window.stop()
                self.wait(lambda: window.session.closed)
            window.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def wait(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), "Tempo esgotado aguardando a execução.")

    def window(self, source="", start=True):
        w = RuntimeWindow(
            self.project, source, lambda path: b"", self.root, self.root / "actions.py"
        )
        self.windows.append(w)
        w.show()
        if start:
            w.start()
            self.wait(lambda: w.session.active and not w.session.busy)
        return w

    def click(self, w):
        w.view.widgets[self.button.id].click()
        self.wait(lambda: not w.session.busy)

    def test_construction_does_not_execute_source_and_explicit_start_does(self):
        source = "from pathlib import Path\nPath('started').write_text('ok')\n"
        w = self.window(source, start=False)
        self.assertFalse((self.root / "started").exists())
        w.start()
        self.wait(lambda: w.session.active)
        self.assertEqual((self.root / "started").read_text(), "ok")

    def test_fields_pages_functions_and_persistent_enabled_state(self):
        pages = self.project.add(self.project.root.id, ComponentKind.PAGES)
        page = self.project.add(pages.id, ComponentKind.PAGE)
        field = self.project.add(page.id, ComponentKind.TEXT_INPUT)
        create_flow(self.project, self.project.root.id)["body"] = [log("start", "Início")]
        self.flow["body"] = [
            {"id": "page", "op": "show_page", "component": page.id},
            {
                "id": "text",
                "op": "set_text",
                "component": self.label.id,
                "value": {"id": "read", "op": "read", "component": field.id, "attribute": "text"},
            },
            {"id": "call", "op": "call", "function": "greet", "value": literal("arg", "Linux")},
            {
                "id": "disabled",
                "op": "set_enabled",
                "component": self.button.id,
                "value": literal("false", False),
            },
        ]
        w = self.window('def greet(ctx, valor):\n    print("Olá",valor)\n')
        w.view.widgets[field.id].setText("Meu nome")
        self.click(w)
        self.assertEqual(w.view.tabs[pages.id].currentIndex(), 1)
        self.assertEqual(w.view.widgets[self.label.id].text(), "Meu nome")
        self.assertIn("Olá Linux", w.output.toPlainText())
        self.assertFalse(w.view.widgets[self.button.id].isEnabled())
        self.assertEqual(self.label.properties["text"], "New text")
        self.assertEqual(pages.properties["initial_page"], pages.children[0].id)

    def test_argument_boundaries_and_stderr_zero_exit(self):
        value = '$(touch SHOULD_NOT_EXIST); espaço "aspas"'
        self.flow["body"] = [
            {
                "id": "run",
                "op": "run",
                "admin": False,
                "program": literal("program", sys.executable),
                "arguments": {
                    "id": "args",
                    "op": "list",
                    "items": [
                        literal("flag", "-c"),
                        literal(
                            "code", 'import sys; print(sys.argv[1]); print("aviso",file=sys.stderr)'
                        ),
                        literal("arg", value),
                    ],
                },
            },
            log("after", "CONTINUOU"),
        ]
        w = self.window()
        self.click(w)
        text = w.output.toPlainText()
        self.assertIn(value, text)
        self.assertIn("aviso", text)
        self.assertIn("CONTINUOU", text)
        self.assertEqual(w.state.text(), "Flow completed.")
        self.assertFalse((self.root / "SHOULD_NOT_EXIST").exists())

    def test_nonzero_and_missing_executable_stop_sequence_with_origin(self):
        self.flow["body"] = [
            {
                "id": "script",
                "op": "script",
                "admin": False,
                "source": literal("source", 'printf "Antes\\n"; printf "Erro\\n" >&2; exit 7'),
                "arguments": {"id": "args", "op": "list", "items": []},
            },
            log("after", "NAO_CONTINUAR"),
        ]
        w = self.window()
        self.click(w)
        self.assertEqual(w.last_error["block"], "script")
        self.assertIn("code 7", w.last_error["message"])
        self.assertNotIn("NAO_CONTINUAR", w.output.toPlainText())
        self.assertTrue(w.locate.isEnabled())
        self.flow["body"][0] = {
            "id": "missing",
            "op": "run",
            "admin": False,
            "program": literal("p", "makebench-missing-executable"),
            "arguments": {"id": "a", "op": "list", "items": []},
        }
        other = self.window()
        self.click(other)
        self.assertEqual(other.last_error["block"], "missing")
        self.assertIn("not found", other.last_error["message"])

    def test_own_function_traceback_and_worker_remains_available(self):
        self.flow["body"] = [
            {"id": "function", "op": "call", "function": "fail", "value": literal("arg", "")}
        ]
        w = self.window('def fail(ctx, valor):\n    raise ValueError("Falha própria")\n')
        self.click(w)
        self.assertEqual(w.last_error["block"], "function")
        self.assertEqual(w.last_error["source_line"], 2)
        self.assertIn("Falha própria", w.output.toPlainText())
        self.assertTrue(w.session.active)

    def test_python_event_runs_its_function_and_converted_blocks_behave_the_same(self):
        from makebench.core.codegen import convert_to_python

        self.flow["body"] = [log("hello", "From blocks")]
        source = convert_to_python(self.project, "")
        self.assertEqual(self.project.programming, "python")
        self.assertEqual(self.flow["function"], "on_new_button_click")
        self.assertNotIn("body", self.flow)
        w = self.window(source + "\n\ndef unused(ctx):\n    print('no')\n")
        self.click(w)
        self.assertIn("From blocks", w.output.toPlainText())
        self.assertNotIn("no", w.output.toPlainText().split("From blocks")[-1])

    def test_python_flow_stores_and_reads_records_through_ctx_data(self):
        from makebench.core.codegen import convert_to_python
        from makebench.core.datastore import data_path

        self.project.metadata["collections"] = [
            {
                "id": "authors",
                "name": "Autores",
                "fields": [{"id": "n", "name": "nome", "type": "text"}],
            },
            {
                "id": "books",
                "name": "Livros",
                "fields": [
                    {"id": "t", "name": "titulo", "type": "text"},
                    {"id": "a", "name": "autor", "type": "ref", "target": "authors"},
                ],
            },
        ]
        self.flow["body"] = [log("hello", "x")]
        convert_to_python(self.project, "")
        source = (
            "def on_new_button_click(ctx):\n"
            "    author = ctx.data.add('Autores', nome='Ana')\n"
            "    ctx.data.add('Livros', titulo='Um', autor=author)\n"
            "    ctx.log(ctx.data.count('Livros'))\n"
            "    try:\n"
            "        ctx.data.delete('Autores', author)\n"
            "    except Exception as error:\n"
            "        ctx.log(type(error).__name__ + ': ' + str(error))\n"
        )
        w = self.window(source)
        self.click(w)
        text = w.output.toPlainText()
        self.assertIn("1\n", text)
        self.assertIn("TaskError: Cannot delete: 1 record of Livros still points to it.", text)
        self.assertTrue(data_path(self.project, True).is_file())

    def test_table_and_choice_show_records_and_read_the_selected_record(self):
        from PySide6.QtWidgets import QComboBox, QTableWidget

        table = self.project.add(self.project.root.id, ComponentKind.TABLE)
        choice = self.project.add(self.project.root.id, ComponentKind.CHOICE)
        self.project.metadata["collections"] = [
            {
                "id": "authors",
                "name": "Autores",
                "fields": [{"id": "n", "name": "nome", "type": "text"}],
            },
            {
                "id": "books",
                "name": "Livros",
                "fields": [
                    {"id": "t", "name": "titulo", "type": "text"},
                    {"id": "a", "name": "autor", "type": "ref", "target": "authors"},
                ],
            },
        ]
        picked = {"id": "r0", "op": "read", "component": table.id, "attribute": "record"}
        create_flow(self.project, table.id)["body"] = [{"id": "l1", "op": "log", "value": picked}]
        add = lambda name, collection, values: {  # noqa: E731
            "id": name,
            "op": "data_add",
            "collection": collection,
            "values": [
                {
                    "field": field,
                    "value": value if isinstance(value, dict) else literal(name + field, value),
                }
                for field, value in values.items()
            ],
        }
        self.flow["body"] = [
            add("a1", "authors", {"n": "Ana"}),
            add("b1", "books", {"t": "Um", "a": {"id": "last", "op": "data_last_id"}}),
            add("b2", "books", {"t": "Dois", "a": {"id": "last2", "op": "data_last_id"}}),
            {"id": "s1", "op": "show_records", "component": table.id, "collection": "books"},
            {"id": "s2", "op": "show_records", "component": choice.id, "collection": "authors"},
        ]
        w = self.window("")
        widget, combo = w.view.widgets[table.id], w.view.widgets[choice.id]
        self.assertIsInstance(widget, QTableWidget)
        self.assertIsInstance(combo, QComboBox)
        self.click(w)
        self.assertEqual(widget.columnCount(), 2)
        self.assertEqual(widget.horizontalHeaderItem(1).text(), "autor")
        self.assertEqual([widget.item(r, 1).text() for r in range(2)], ["Ana", "Ana"])
        self.assertEqual(combo.itemText(0), "Ana")
        self.assertEqual(combo.currentData(), 1)
        widget.selectRow(1)
        self.wait(lambda: "2" in w.output.toPlainText().split("\n"))

    def test_files_and_csv_round_trip_through_blocks(self):
        import tempfile
        from pathlib import Path

        table = self.project.add(self.project.root.id, ComponentKind.TABLE)
        self.project.metadata["collections"] = [
            {
                "id": "authors",
                "name": "Autores",
                "fields": [{"id": "n", "name": "nome", "type": "text"}],
            }
        ]
        with tempfile.TemporaryDirectory() as folder:
            seen, shown, text = (str(Path(folder) / name) for name in ("a.csv", "b.csv", "t.txt"))
            path = lambda name, value: {"id": name, "op": "literal", "value": value}  # noqa: E731
            self.flow["body"] = [
                {
                    "id": "a1",
                    "op": "data_add",
                    "collection": "authors",
                    "values": [{"field": "n", "value": path("v", 'Zé, o "bom"')}],
                },
                {"id": "s1", "op": "show_records", "component": table.id, "collection": "authors"},
                {"id": "e1", "op": "export_table", "component": table.id, "path": path("p1", seen)},
                {
                    "id": "e2",
                    "op": "export_records",
                    "collection": "authors",
                    "path": path("p2", shown),
                },
                {
                    "id": "w1",
                    "op": "write_file",
                    "path": path("p3", text),
                    "value": path("t", "olá"),
                },
                {
                    "id": "l1",
                    "op": "log",
                    "value": {"id": "r1", "op": "csv_rows", "path": path("p4", seen)},
                },
                {
                    "id": "l2",
                    "op": "log",
                    "value": {"id": "r2", "op": "file_text", "path": path("p5", text)},
                },
            ]
            w = self.window("")
            self.click(w)
            self.wait(lambda: "olá" in w.output.toPlainText())
            expected = 'nome\r\n"Zé, o ""bom"""\r\n'
            self.assertEqual(Path(seen).read_bytes().decode(), expected)
            self.assertEqual(Path(shown).read_bytes().decode(), expected)
            self.assertIn("[['Zé, o \"bom\"']]", w.output.toPlainText())

    def test_set_chart_block_draws_the_given_data(self):
        chart = self.project.add(self.project.root.id, ComponentKind.CHART)
        chart.properties["chart_type"] = "pie"
        lit = lambda i, v: {"id": i, "op": "literal", "value": v}  # noqa: E731
        items = lambda i, *v: {  # noqa: E731
            "id": i,
            "op": "list",
            "items": [lit(f"{i}{n}", x) for n, x in enumerate(v)],
        }
        self.flow["body"] = [
            {
                "id": "c1",
                "op": "set_chart",
                "component": chart.id,
                "labels": items("l", "A", "B"),
                "value": items("v", 3, 5),
            },
            log("done", "done"),
        ]
        w = self.window("")
        self.click(w)
        self.wait(lambda: "done" in w.output.toPlainText())
        _, widget = w.widget_for(chart.id)
        self.assertEqual((widget.labels, widget.values), (["A", "B"], [3, 5]))
        self.assertEqual(widget.chart_type, "pie")
        self.assertTrue(widget.grab().toImage().width() > 0)

    def test_change_timer_and_close_events_run_their_flows(self):
        field = self.project.add(self.project.root.id, ComponentKind.TEXT_INPUT)
        window = self.project.root
        window.properties["timer_seconds"] = 1
        create_flow(self.project, field.id)["body"] = [log("c", "changed")]
        create_flow(self.project, window.id, kind="timer")["body"] = [log("t", "tick")]
        create_flow(self.project, window.id, kind="close")["body"] = [log("x", "bye")]
        w = self.window("")
        edit = w.view.widgets[field.id]
        edit.textEdited.emit("a")
        self.wait(lambda: "changed" in w.output.toPlainText() and not w.session.busy)
        self.wait(lambda: "tick" in w.output.toPlainText(), timeout=4)
        seen = []
        w.session.output.connect(lambda _channel, text: seen.append(text))
        w.close()
        self.wait(lambda: w.session.closed)
        self.assertIn("bye\n", seen)
        self.windows.remove(w)  # closing the last window already deleted it

    def test_window_frame_position_and_stacking(self):
        self.project.root.properties.update(frame="none", on_top=True, centered=True)
        w = self.window("")
        flags = w.windowFlags()
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)
        self.project.root.properties.update(frame="no_buttons", on_top=False)
        w2 = self.window("")
        flags = w2.windowFlags()
        self.assertTrue(flags & Qt.WindowType.CustomizeWindowHint)
        self.assertFalse(flags & Qt.WindowType.WindowCloseButtonHint)
        self.assertFalse(flags & Qt.WindowType.WindowStaysOnTopHint)

    def test_menu_item_fires_its_flow(self):
        from makebench.core.menus import parse_menus

        self.project.root.properties["menus"] = parse_menus("File\n  Save | Ctrl+S")
        create_flow(self.project, self.project.root.id, kind="menu:save")["body"] = [
            log("m", "saved")
        ]
        w = self.window("")
        action = w.findChild(QAction, "menu_save")
        self.assertEqual(action.shortcut().toString(), "Ctrl+S")
        action.trigger()
        self.wait(lambda: "saved" in w.output.toPlainText())

    def test_number_and_slider_read_set_and_fire_change(self):
        root = self.project.root.id
        number = self.project.add(root, ComponentKind.NUMBER)
        number.properties.update(value=5, maximum=10, decimals=1, step=0.5)
        slider = self.project.add(root, ComponentKind.SLIDER)
        for node in (number, slider):
            create_flow(self.project, node.id)["body"] = [log("c", "changed " + node.id[:6])]

        def read(node):
            return {"id": "r" + node.id, "op": "read", "component": node.id, "attribute": "value"}

        self.flow["body"] = [
            {"id": "s1", "op": "set_value", "component": number.id, "value": literal("v", 7.5)},
            {"id": "s2", "op": "set_value", "component": slider.id, "value": literal("w", 40)},
            {"id": "l1", "op": "log", "value": read(number)},
            {"id": "l2", "op": "log", "value": read(slider)},
        ]
        w = self.window("")
        self.click(w)
        out = w.output.toPlainText()
        self.assertIn("7.5", out)
        self.assertIn("40", out)
        self.assertNotIn("changed", out)  # the ctx API never fires change
        w.view.widgets[slider.id].setValue(55)
        self.wait(lambda: "changed " + slider.id[:6] in w.output.toPlainText())
        w.view.widgets[number.id].setValue(2.0)
        self.wait(lambda: "changed " + number.id[:6] in w.output.toPlainText())

    def test_text_area_reads_sets_and_fires_change_only_for_the_person(self):
        area = self.project.add(self.project.root.id, ComponentKind.TEXT_AREA)
        area.properties["text"] = "one\ntwo"
        create_flow(self.project, area.id)["body"] = [log("c", "changed")]
        self.flow["body"] = [
            {"id": "s", "op": "set_text", "component": area.id, "value": literal("v", "a\nb")},
            {
                "id": "l",
                "op": "log",
                "value": {"id": "r", "op": "read", "component": area.id, "attribute": "text"},
            },
        ]
        w = self.window("")
        edit = w.view.widgets[area.id]
        self.assertEqual(edit.toPlainText(), "one\ntwo")
        self.click(w)
        self.assertEqual(edit.toPlainText(), "a\nb")
        self.assertIn("a\nb", w.output.toPlainText())
        self.assertNotIn("changed", w.output.toPlainText())
        edit.insertPlainText("!")
        self.wait(lambda: "changed" in w.output.toPlainText())

    def test_choice_selects_changes_options_and_fires_change_for_the_person(self):
        from PySide6.QtWidgets import QComboBox

        choice = self.project.add(self.project.root.id, ComponentKind.CHOICE)
        choice.properties.update(options=["a", "b", "c"], text="b")
        create_flow(self.project, choice.id)["body"] = [log("c", "changed")]

        def read(name):
            return {"id": name, "op": "read", "component": choice.id, "attribute": "text"}

        self.flow["body"] = [
            {"id": "l0", "op": "log", "value": read("r0")},
            {"id": "s1", "op": "set_text", "component": choice.id, "value": literal("v", "c")},
            {"id": "l1", "op": "log", "value": read("r1")},
            {
                "id": "o",
                "op": "set_options",
                "component": choice.id,
                "value": {
                    "id": "lst",
                    "op": "list",
                    "items": [literal("x", "c"), literal("y", "z")],
                },
            },
            {"id": "l2", "op": "log", "value": read("r2")},
        ]
        w = self.window("")
        combo = w.view.widgets[choice.id]
        self.assertIsInstance(combo, QComboBox)
        self.click(w)
        self.assertEqual(w.output.toPlainText().split()[:3], ["b", "c", "c"])
        self.assertEqual([combo.itemText(i) for i in range(combo.count())], ["c", "z"])
        self.assertNotIn("changed", w.output.toPlainText())
        combo.activated.emit(1)
        self.wait(lambda: "changed" in w.output.toPlainText())

    def test_date_reads_sets_and_fires_change_for_the_person(self):
        from PySide6.QtCore import QDate
        from PySide6.QtWidgets import QDateEdit

        date = self.project.add(self.project.root.id, ComponentKind.DATE)
        date.properties["text"] = "2026-03-04"
        create_flow(self.project, date.id)["body"] = [log("c", "changed")]

        def read(name):
            return {"id": name, "op": "read", "component": date.id, "attribute": "text"}

        self.flow["body"] = [
            {"id": "l0", "op": "log", "value": read("r0")},
            {
                "id": "s1",
                "op": "set_text",
                "component": date.id,
                "value": literal("v", "2027-12-31"),
            },
            {"id": "l1", "op": "log", "value": read("r1")},
        ]
        w = self.window("")
        edit = w.view.widgets[date.id]
        self.assertIsInstance(edit, QDateEdit)
        self.click(w)
        self.assertEqual(w.output.toPlainText().split()[:2], ["2026-03-04", "2027-12-31"])
        self.assertNotIn("changed", w.output.toPlainText())
        edit.setDate(QDate(2028, 1, 2))
        self.wait(lambda: "changed" in w.output.toPlainText())

    def test_table_sets_adds_and_reads_rows_and_fires_change_for_the_person(self):
        from PySide6.QtWidgets import QTableWidget

        table = self.project.add(self.project.root.id, ComponentKind.TABLE)
        table.properties["headers"] = ["Name", "Age"]
        create_flow(self.project, table.id)["body"] = [log("c", "picked")]

        def rows(name, *cells):
            return {
                "id": name,
                "op": "list",
                "items": [
                    {
                        "id": f"{name}{i}",
                        "op": "list",
                        "items": [literal(f"{name}{i}{j}", c) for j, c in enumerate(row)],
                    }
                    for i, row in enumerate(cells)
                ],
            }

        selected = {"id": "r0", "op": "read", "component": table.id, "attribute": "selected"}
        self.flow["body"] = [
            {"id": "l0", "op": "log", "value": selected},
            {
                "id": "op_set",
                "op": "set_rows",
                "component": table.id,
                "value": rows("a", ["Ann", "3"], ["Bob", "5"]),
            },
            {
                "id": "op_add",
                "op": "add_row",
                "component": table.id,
                "value": rows("b", ["Cy", 7])["items"][0],
            },
        ]
        w = self.window("")
        widget = w.view.widgets[table.id]
        self.assertIsInstance(widget, QTableWidget)
        self.click(w)
        self.assertEqual(widget.rowCount(), 3)
        self.assertEqual(widget.item(2, 1).text(), "7")
        self.assertNotIn("picked", w.output.toPlainText())
        widget.selectRow(1)
        self.wait(lambda: "picked" in w.output.toPlainText())

    def test_block_function_returns_a_value_to_the_event(self):
        from makebench.core.logic import create_block_function

        greet = create_block_function(self.project, "greet", ["who"])
        greet["body"] = [
            {
                "id": "ret",
                "op": "return",
                "value": {
                    "id": "join",
                    "op": "join",
                    "left": literal("hi", "Hello, "),
                    "right": {"id": "who", "op": "variable", "name": "who", "scope": "local"},
                },
            }
        ]
        self.flow["body"] = [
            {
                "id": "out",
                "op": "log",
                "value": {
                    "id": "call",
                    "op": "call_function",
                    "function": greet["id"],
                    "args": [literal("name", "Ada")],
                },
            }
        ]
        w = self.window("")
        self.click(w)
        self.assertIn("Hello, Ada", w.output.toPlainText())

    def test_missing_event_function_reports_its_name(self):
        self.project.metadata["programming"] = "python"
        self.flow.pop("body")
        self.flow.pop("workspace")
        self.flow["function"] = "gone"
        w = self.window("")
        self.click(w)
        self.assertIn("gone", w.output.toPlainText())
        self.assertTrue(w.session.active)

    def test_text_choice_and_cancel_do_not_run_following_actions(self):
        self.flow["body"] = [
            {
                "id": "ask",
                "op": "ask",
                "kind": "text",
                "name": "name",
                "prompt": literal("prompt", "Seu nome?"),
                "options": {"id": "opts", "op": "list", "items": []},
            },
            {
                "id": "choice",
                "op": "ask",
                "kind": "choice",
                "name": "choice",
                "prompt": literal("question", "Uma opção?"),
                "options": {
                    "id": "options",
                    "op": "list",
                    "items": [literal("one", "A"), literal("two", "B")],
                },
            },
            {
                "id": "result",
                "op": "log",
                "value": {"id": "name", "op": "variable", "name": "name"},
            },
            log("after", "NAO_APOS_CANCELAR"),
        ]
        w = self.window()
        w.view.widgets[self.button.id].click()
        self.wait(lambda: bool(w.dialogs))
        dialog = next(iter(w.dialogs))
        self.assertIsInstance(dialog, QInputDialog)
        dialog.setTextValue("Richard")
        dialog.accept()
        self.wait(lambda: bool(w.dialogs))
        dialog = next(iter(w.dialogs))
        self.assertEqual(dialog.comboBoxItems(), ["A", "B"])
        dialog.reject()
        self.wait(lambda: not w.session.busy)
        self.assertEqual(w.state.text(), "Flow cancelled.")
        self.assertNotIn("NAO_APOS_CANCELAR", w.output.toPlainText())

    def test_confirmation_no_cancels_flow(self):
        self.flow["body"] = [
            {"id": "confirm", "op": "confirm", "prompt": literal("prompt", "Continuar?")},
            log("after", "NAO"),
        ]
        w = self.window()
        w.view.widgets[self.button.id].click()
        self.wait(lambda: bool(w.dialogs))
        dialog = next(iter(w.dialogs))
        dialog.button(QMessageBox.StandardButton.No).click()
        self.wait(lambda: not w.session.busy)
        self.assertEqual(w.state.text(), "Flow cancelled.")
        self.assertNotIn("NAO", w.output.toPlainText())

    def test_infinite_python_is_cancellable_and_gui_ticks(self):
        self.flow["body"] = [
            {"id": "call", "op": "call", "function": "infinite", "value": literal("arg", "")}
        ]
        w = self.window("def infinite(ctx, valor):\n    while True: pass\n")
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)
        w.view.widgets[self.button.id].click()
        QTest.qWait(120)
        self.assertTrue(w.session.busy)
        self.assertGreater(len(ticks), 3)
        started = time.monotonic()
        w.stop()
        self.wait(lambda: w.session.closed, 3)
        timer.stop()
        self.assertLess(time.monotonic() - started, 2)

    def test_cancelling_task_kills_ordinary_descendants(self):
        code = """import os,signal,subprocess,sys,time
signal.signal(signal.SIGTERM,signal.SIG_IGN)
p=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'])
open('child.pid','w').write(str(p.pid))
print('Pronto',flush=True)
time.sleep(60)
"""
        self.flow["body"] = [
            {
                "id": "run",
                "op": "run",
                "admin": False,
                "program": literal("p", sys.executable),
                "arguments": {
                    "id": "args",
                    "op": "list",
                    "items": [literal("flag", "-u"), literal("flag2", "-c"), literal("code", code)],
                },
            }
        ]
        w = self.window()
        w.view.widgets[self.button.id].click()
        self.wait(lambda: (self.root / "child.pid").exists())
        child = int((self.root / "child.pid").read_text())
        w.stop()
        self.wait(lambda: w.session.closed)

        def gone():
            status = Path(f"/proc/{child}/status")
            return not status.exists() or "\nState:\tZ" in status.read_text()

        self.wait(gone)

    def test_admin_protocol_with_disposable_fake_agent(self):
        # A disposable executable simulates the agent's result; never calls the real pkexec.
        original = shutil.which
        fake = self.root / "pkexec-test"
        fake.write_text("#!/bin/sh\nsleep 0.15\nexit 126\n")
        fake.chmod(0o700)
        self.flow["body"] = [
            {
                "id": "admin",
                "op": "run",
                "admin": True,
                "program": literal("p", "/usr/bin/true"),
                "arguments": {"id": "args", "op": "list", "items": []},
            },
            log("after", "NAO_CONTINUAR"),
        ]
        with patch(
            "makebench.runtime.process.shutil.which",
            side_effect=lambda value: str(fake) if value == "pkexec" else original(value),
        ):
            w = self.window()
            w.view.widgets[self.button.id].click()
            self.wait(lambda: w.session.admin_active)
            self.assertFalse(w.stop())
            self.assertFalse(w.stop_button.isEnabled())
            self.wait(lambda: not w.session.busy)
        self.assertFalse(w.session.admin_active)
        self.assertEqual(w.state.text(), "Flow cancelled.")
        self.assertNotIn("NAO_CONTINUAR", w.output.toPlainText())

    def test_top_level_function_source_error_keeps_original_traceback(self):
        w = self.window('raise ValueError("Falha ao carregar funções")\n', start=False)
        w.start()
        self.wait(lambda: w.session.closed)
        self.assertIn("Falha ao carregar funções", w.last_error["message"])
        self.assertEqual(w.last_error["source_line"], 1)
        self.assertTrue(w.locate.isEnabled())

    def test_choice_and_file_directory_dialogs_return_explicit_values(self):
        from PySide6.QtWidgets import QFileDialog

        chosen = self.root / "file.txt"
        chosen.write_text("fixture")
        self.flow["body"] = [
            {
                "id": "ask",
                "op": "ask",
                "kind": "file",
                "name": "file",
                "prompt": literal("p", "Arquivo?"),
                "options": {"id": "o", "op": "list", "items": []},
            },
            {"id": "log", "op": "log", "value": {"id": "var", "op": "variable", "name": "file"}},
        ]
        w = self.window()
        w.view.widgets[self.button.id].click()
        self.wait(lambda: bool(w.dialogs))
        dialog = next(iter(w.dialogs))
        self.assertIsInstance(dialog, QFileDialog)
        QTest.qWait(100)
        edit = dialog.findChild(QLineEdit, "fileNameEdit")
        edit.setFocus()
        edit.selectAll()
        QTest.keyClicks(edit, str(chosen))
        QTest.keyClick(edit, Qt.Key.Key_Return)
        self.wait(lambda: not w.session.busy)
        self.assertIn(str(chosen), w.output.toPlainText())
        self.flow["body"][0]["kind"] = "directory"
        other = self.window()
        other.view.widgets[self.button.id].click()
        self.wait(lambda: bool(other.dialogs))
        dialog = next(iter(other.dialogs))
        QTest.qWait(100)
        edit = dialog.findChild(QLineEdit, "fileNameEdit")
        edit.setFocus()
        edit.selectAll()
        QTest.keyClicks(edit, str(self.root))
        QTest.keyClick(edit, Qt.Key.Key_Return)
        self.wait(lambda: not other.session.busy)
        self.assertIn(str(self.root), other.output.toPlainText())

    def test_admin_success_and_denial_using_only_fake_disposable_agent(self):
        original = shutil.which
        fake = self.root / "pkexec-test"
        self.flow["body"] = [
            {
                "id": "admin",
                "op": "run",
                "admin": True,
                "program": literal("p", "/usr/bin/true"),
                "arguments": {"id": "args", "op": "list", "items": []},
            },
            log("after", "APOS_AUTORIZAR"),
        ]
        for code in (0, 127):
            with self.subTest(code=code):
                fake.write_text(f"#!/bin/sh\nexit {code}\n")
                fake.chmod(0o700)
                with patch(
                    "makebench.runtime.process.shutil.which",
                    side_effect=lambda value: str(fake) if value == "pkexec" else original(value),
                ):
                    w = self.window()
                    self.click(w)
                if code == 0:
                    self.assertIn("APOS_AUTORIZAR", w.output.toPlainText())
                else:
                    self.assertNotIn("APOS_AUTORIZAR", w.output.toPlainText())
                    self.assertEqual(w.last_error["block"], "admin")

    def test_script_center_simulation_completes_with_stderr_and_progress(self):
        from makebench.core.storage import load_project
        from makebench.core.source import SourceBuffer

        self.project = load_project("examples/script-center/app.makebench.json")
        self.button = self.project.find("button_setup")
        w = self.window(SourceBuffer.load(Path("examples/script-center/app.makebench.json")).text)
        w.view.widgets[self.button.id].click()
        self.wait(lambda: bool(w.dialogs))
        dialog = next(iter(w.dialogs))
        dialog.setTextValue("Reprodutor de música")
        dialog.accept()
        self.wait(lambda: bool(w.dialogs))
        dialog = next(iter(w.dialogs))
        dialog.button(QMessageBox.StandardButton.Yes).click()
        self.wait(lambda: not w.session.busy)
        self.assertEqual(w.view.widgets["progress_task"].value(), 100)
        self.assertIn("Aviso de exemplo", w.output.toPlainText())
        self.assertIn("Nenhum aplicativo foi instalado", w.output.toPlainText())
        self.assertEqual(w.state.text(), "Flow completed.")

    def test_editor_does_not_abandon_admin_task_when_closing(self):
        from makebench.editor.window import MainWindow

        original = shutil.which
        fake = self.root / "pkexec-test"
        fake.write_text("#!/bin/sh\nsleep 0.35\nexit 0\n")
        fake.chmod(0o700)
        self.flow["body"] = [
            {
                "id": "admin",
                "op": "run",
                "admin": True,
                "program": literal("p", "/usr/bin/true"),
                "arguments": {"id": "args", "op": "list", "items": []},
            }
        ]
        editor = MainWindow(self.project)
        editor.show()
        try:
            with patch(
                "makebench.runtime.process.shutil.which",
                side_effect=lambda value: str(fake) if value == "pkexec" else original(value),
            ):
                editor.run_project()
                runtime = editor.runtime_window
                self.wait(lambda: runtime.session.active and not runtime.session.busy)
                runtime.view.widgets[self.button.id].click()
                self.wait(lambda: runtime.session.admin_active)
                editor.close()
                self.assertTrue(editor.isVisible())
                runtime.close()
                self.assertFalse(runtime.close_pending)
                self.wait(lambda: not runtime.session.busy)
            editor.close()
            self.wait(lambda: not editor.isVisible())
            self.assertTrue(runtime.session.closed)
        finally:
            if editor.runtime_window is not None and not editor.runtime_window.session.closed:
                editor.runtime_window.stop()
                self.wait(
                    lambda: editor.runtime_window is None or editor.runtime_window.session.closed
                )
            editor.history.mark_saved()
            editor.source.mark_saved()
            editor.close()
            editor.deleteLater()


if __name__ == "__main__":
    unittest.main()
