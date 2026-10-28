# SPDX-License-Identifier: GPL-3.0-or-later
"""Real GTK validation: wizard, ctx API, tasks, error and exported source."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile
from makebench.core.navigation import welcome_template
from makebench.core.project import Project, ComponentKind
from makebench.core.logic import create_flow
from makebench.core.exporter import export_source
from makebench.gtk_runtime.application import GtkRuntime


def check_runtime():
    """Exercise three states, two windows, a GTK question and a task with stdout/stderr."""
    with tempfile.TemporaryDirectory(prefix="makebench-gtk-runtime-test-") as directory:
        root = Path(directory)
        os.environ["XDG_DATA_HOME"] = str(root / "data")  # test records never touch the real home
        p = welcome_template()
        p.metadata["collections"] = [
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
        entry = p.add(p.root.id, ComponentKind.TEXT_INPUT)
        progress = p.add(p.root.id, ComponentKind.PROGRESS)
        number = p.add(p.root.id, ComponentKind.NUMBER)
        number.properties.update(decimals=1, step=0.5)
        slider = p.add(p.root.id, ComponentKind.SLIDER)
        area = p.add(p.root.id, ComponentKind.TEXT_AREA)
        choice = p.add(p.root.id, ComponentKind.CHOICE)
        choice.properties.update(options=["um", "dois"], text="dois")
        table = p.add(p.root.id, ComponentKind.TABLE)
        table.properties["headers"] = ["A", "B"]
        date = p.add(p.root.id, ComponentKind.DATE)
        date.properties["text"] = "2026-03-04"
        p.root.properties["frame"] = "no_buttons"
        p.root.properties["menus"] = [
            {"text": "File", "items": [{"id": "save", "text": "Save", "shortcut": "Ctrl+S"}]}
        ]
        create_flow(p, p.root.id, kind="menu:save")["body"] = [
            {
                "id": "menu_log",
                "op": "log",
                "value": {"id": "ml", "op": "literal", "value": "menu"},
            }
        ]
        output = p.add(p.root.id, ComponentKind.OUTPUT)
        launch = p.add(p.root.id, ComponentKind.BUTTON)
        launch.properties.update(text="API ctx", icon="assets/button.svg", tooltip="Testar API ctx")
        flow = create_flow(p, launch.id)
        flow["body"] = [
            {
                "id": "call",
                "op": "call",
                "function": "exercise",
                "value": {"id": "arg", "op": "literal", "value": ""},
            }
        ]
        source = f"""def exercise(ctx, valor):
    ctx.set_text({launch.id!r}, 'Ícone preservado')
    assert ctx.read({launch.id!r}, 'text') == 'Ícone preservado'
    ctx.set_text({entry.id!r}, 'GTK real')
    assert ctx.read({entry.id!r}, 'text') == 'GTK real'
    ctx.set_value({progress.id!r}, 75)
    assert ctx.read({progress.id!r}, 'value') == 75
    ctx.set_text({area.id!r}, 'linha 1\\nlinha 2')
    assert ctx.read({area.id!r}, 'text') == 'linha 1\\nlinha 2'
    assert ctx.read({choice.id!r}, 'text') == 'dois'
    ctx.set_text({choice.id!r}, 'um')
    ctx.set_options({choice.id!r}, ['tres', 'um'])
    assert ctx.read({choice.id!r}, 'text') == 'um'
    assert ctx.read({date.id!r}, 'text') == '2026-03-04'
    ctx.set_text({date.id!r}, '2027-12-31')
    assert ctx.read({date.id!r}, 'text') == '2027-12-31'
    ctx.set_rows({table.id!r}, [['a', 1], ['b', 2]])
    ctx.add_row({table.id!r}, ['c', 3])
    assert ctx.read({table.id!r}, 'selected') == []
    ana = ctx.data.add('Autores', nome='Ana')
    ctx.data.add('Livros', titulo='Um', autor=ana)
    ctx.show_records({table.id!r}, 'Livros')
    assert ctx.read({table.id!r}, 'record') is None
    shown = ctx.read({table.id!r}, 'table')
    assert shown['headers'] == ['titulo', 'autor'] and shown['rows'] == [['Um', 'Ana']], shown
    ctx.export_table_csv({str(root / "livros.csv")!r}, {table.id!r})
    assert ctx.read_csv({str(root / "livros.csv")!r}) == [['Um', 'Ana']]
    ctx.show_records({choice.id!r}, 'Autores')
    assert ctx.read({choice.id!r}, 'text') == 'Ana'
    assert ctx.read({choice.id!r}, 'record') == ana
    ctx.set_value({number.id!r}, 2.5)
    assert ctx.read({number.id!r}, 'value') == 2.5
    ctx.set_value({slider.id!r}, 30)
    assert ctx.read({slider.id!r}, 'value') == 30
    assert ctx.ask('text', 'Pergunta de teste') == 'resposta'
    ctx.run('/bin/sh', ['-c', 'printf saida; printf aviso >&2'])
    ctx.run('/bin/sh', ['-c', 'exit 3'])
"""
        messages = []
        runtime = GtkRuntime(
            p,
            source,
            lambda _: (
                b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16"/></svg>'
            ),
            root,
            None,
            messages.append,
        )
        step = [0]
        failure = []

        def tick():
            """Answer the dialog through the GTK API and advance only after each flow."""
            try:
                if runtime.dialogs:
                    dialog = next(iter(runtime.dialogs))
                    child = dialog.get_content_area().get_first_child()
                    while child:
                        if isinstance(child, runtime.Gtk.Entry):
                            child.set_text("resposta")
                        child = child.get_next_sibling()
                    dialog.response(runtime.Gtk.ResponseType.OK)
                    return True
                if not runtime.active or runtime.busy:
                    return True
                if step[0] == 0:
                    assert runtime.menu_bar(p.root, p.root.id), "The menu bar is missing"
                    assert not runtime.windows[p.root.id].get_deletable(), "The close button stayed"
                    runtime.queue_event(launch.id)
                    step[0] = 1
                    return True
                if step[0] == 1:
                    assert hasattr(
                        runtime.views[p.root.id].widgets[launch.id], "_makebench_label"
                    ), "The button lost its icon"
                    assert any(
                        m["type"] == "error" and "3" in m.get("message", "") for m in messages
                    ), messages
                    assert any(
                        m["type"] == "log" and m.get("channel") == "stderr" and "aviso" in m["text"]
                        for m in messages
                    )
                    text = runtime.views[p.root.id].read(output.id, "text")
                    assert "saida" in text and "aviso" in text and "[Error]" in text, text
                    step[0] = 2
                next_button = next(n for n in p.root.walk() if n.properties.get("text") == "Next")
                if step[0] in (2, 3, 4):
                    runtime.queue_event(next_button.id)
                    step[0] += 1
                    return True
                assert runtime.open_windows == {p.windows[0].id}
                runtime.stop()
                step[0] = 6
                return False
            except BaseException as exc:
                failure.append(exc)
                runtime.stop()
                return False

        runtime.GLib.timeout_add(100, tick)

        def timeout():
            """A failure does not leave the test application running forever."""
            if step[0] != 6:
                failure.append(AssertionError("GTK excedeu 15 segundos."))
                runtime.stop()
            return False

        timer = runtime.GLib.timeout_add_seconds(15, timeout)
        runtime.run()
        if step[0] == 6:
            runtime.GLib.source_remove(timer)
        if failure:
            raise failure[0]
        assert step[0] == 6
        print(
            "OK: real GTK4, three steps/two windows, read/change, progress, question, stdout/stderr and failure origin."
        )


def check_export():
    """Run the GTK source outside Makebench and check that it ends at the last window."""
    with tempfile.TemporaryDirectory(prefix="makebench-export-gtk-test-") as directory:
        root = Path(directory)
        p = Project.empty("GTK export")
        p.application = {
            "backend": "gtk",
            "name": "GTK export",
            "id": "br.exemplo.exportado",
            "version": "0.1.0",
            "icon": "assets/icon.svg",
        }
        create_flow(p, p.root.id)["body"] = [{"id": "close", "op": "close_window"}]
        source = "from pathlib import Path\nPath('executou.txt').write_text('GTK independente')\n"
        export_source(
            p,
            source,
            lambda _: b'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"/>',
            root / "source.zip",
        )
        with zipfile.ZipFile(root / "source.zip") as z:
            z.extractall(root / "app")
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, "run.py"],
            cwd=root / "app",
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert (root / "app/executou.txt").read_text() == "GTK independente"
        print("OK: GTK source run outside the editor; closing the last window ends it.")


if __name__ == "__main__":
    check_runtime()
    check_export()
