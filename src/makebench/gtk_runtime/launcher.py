# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent GTK entry point and optional transport for the workbench."""

import json
from pathlib import Path
import sys
import threading
from makebench.core.storage import load_project
from makebench.core.source import SourceBuffer
from .application import GtkRuntime


def main():
    """Explicitly start a test snapshot or an exported application."""
    import argparse
    import os

    from makebench.i18n import set_language

    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--supervised", action="store_true")
    parser.add_argument("--working-directory", type=Path)
    parser.add_argument("--source-filename")
    args = parser.parse_args()
    path = args.project.resolve()
    supervised = args.supervised
    project = load_project(path)
    # Tests follow the editor's language; exported apps use their own setting.
    set_language(os.environ.get("MAKEBENCH_LANGUAGE") or project.application.get("language"))
    source = SourceBuffer.load(path)

    def observe(value):
        """Supervision exists only in the test transport, never in the created window."""
        if supervised:
            print(json.dumps(value, ensure_ascii=True), flush=True)
        elif value["type"] == "log":
            print(
                value["text"],
                end="",
                file=sys.stderr if value["channel"] == "stderr" else sys.stdout,
                flush=True,
            )
        elif value["type"] == "error":
            print(value["message"], file=sys.stderr, flush=True)

    runtime = GtkRuntime(
        project,
        source.text,
        lambda name: (path.parent / name).read_bytes(),
        args.working_directory or path.parent,
        args.source_filename or source.path,
        observe,
    )
    if supervised:
        config = path.parent / "debug.json"
        if config.is_file():
            runtime.debug_config = json.loads(config.read_text(encoding="utf-8"))

        def commands():
            """Accept only supervision commands on the test's private stdin."""
            for line in sys.stdin:
                try:
                    value = json.loads(line)
                    runtime.GLib.idle_add(control, value)
                except ValueError:
                    pass
            runtime.GLib.idle_add(runtime.stop)

        def control(value):
            """Test commands never load additional Python code."""
            command = value.get("command")
            if command == "stop":
                runtime.stop()
            elif command == "debug":
                runtime.send(
                    {"type": "debug", **{k: v for k, v in value.items() if k != "command"}}
                )
            elif command == "raise":
                for identifier in runtime.open_windows:
                    runtime.windows[identifier].present()
            elif command == "click":
                runtime.queue_event(value["component"])
            elif command == "inspect":
                controls = {}
                for view in runtime.views.values():
                    for identifier, node in ((n.id, n) for n in view.root.walk()):
                        if node.kind.value in {
                            "label",
                            "button",
                            "text_input",
                            "checkbox",
                            "progress",
                            "output",
                        }:
                            attribute = (
                                "checked"
                                if node.kind.value == "checkbox"
                                else "value"
                                if node.kind.value == "progress"
                                else "text"
                            )
                            controls[identifier] = view.read(identifier, attribute)
                terminals = {
                    identifier: {
                        "screen": widget.terminal.screen.display,
                        "running": widget.terminal.running,
                        "pid": widget.terminal.pid,
                    }
                    for view in runtime.views.values()
                    for identifier, widget in view.widgets.items()
                    if hasattr(widget, "terminal")
                }
                observe(
                    {
                        "type": "inspection",
                        "terminals": terminals,
                        "windows": sorted(runtime.open_windows),
                        "states": runtime.states,
                        "controls": controls,
                    }
                )

        threading.Thread(target=commands, daemon=True).start()
    return runtime.run()


if __name__ == "__main__":
    raise SystemExit(main())
