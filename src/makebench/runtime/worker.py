# SPDX-License-Identifier: MIT
"""Python execution process. Started only by an explicit user action.

The JSON protocol uses its own descriptor; the code's stdout/stderr are user
output. This isolates editor crashes, but it is not a sandbox for untrusted code.
"""

from __future__ import annotations

import io
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import traceback
from .debugger import Debugger, DebugStopped, WorkerTransport

from makebench.core.codegen import generate
from makebench.core.project import Project
from makebench.i18n import set_language, tr


class Cancelled(Exception):
    """Stop the flow when a dialog is cancelled or a confirmation is declined."""


class TaskError(Exception):
    """External task failure; later actions are not run."""


def table_rows(rows):
    """Rows as lists of texts, the only shape tables accept."""
    if isinstance(rows, (str, bytes)) or any(isinstance(row, (str, bytes)) for row in rows):
        raise ValueError("Table rows must be lists of cells.")
    return [[str(cell) for cell in row] for row in rows]


class Context:
    """Synchronous application API, with requests served by the UI process."""

    def __init__(self, send, receive):
        """Receive the JSON transport; every UI interaction happens in the other process."""
        self.send, self.receive = send, receive
        self.variables = {}
        self.actions = {}
        self.window_scopes = {}
        self.window_defaults = {}
        self.current_window = None
        self.sequence = 0
        self.receive_response = None
        self.debugger = None

    def request(self, method, **values):
        """Wait for the matching reply, aborting on cancellation/failure."""
        self.sequence += 1
        identifier = self.sequence
        self.send({"type": "request", "id": identifier, "method": method, **values})
        reply = self.receive_response(identifier) if self.receive_response else self.receive()
        if reply.get("type") != "response" or reply.get("id") != identifier:
            raise RuntimeError(tr("Unexpected reply from the application."))
        if reply.get("cancelled"):
            raise Cancelled(reply.get("error", tr("Operation cancelled.")))
        if not reply.get("ok"):
            raise TaskError(reply.get("error", tr("The task failed.")))
        return reply.get("value")

    def terminal_start(self, component, program=None, arguments=None):
        """Start the PTY of a Terminal component during the explicit run."""
        return self.request(
            "terminal_start", component=component, program=program, arguments=arguments or []
        )

    def terminal_send(self, component, value):
        """Send input to the terminal; the text is never interpolated into another command."""
        return self.request("terminal_send", component=component, value=str(value))

    def terminal_stop(self, component):
        """Stop the processes owned by the selected terminal."""
        return self.request("terminal_stop", component=component)

    def read(self, component, attribute):
        """Read the current text/selection/progress, including user-edited input."""
        return self.request("read", component=component, attribute=attribute)

    def set_text(self, component, value):
        """Update a control's text without replacing the document in the editor."""
        return self.request("set_text", component=component, value=str(value))

    def set_enabled(self, component, value):
        """Enable/disable a control of the running instance."""
        return self.request("set_enabled", component=component, value=bool(value))

    def set_theme(self, theme, accent=""):
        """Switch the current window between system, light and dark, with an optional accent."""
        return self.request("set_theme", theme=str(theme), accent=str(accent))

    def set_background(self, color):
        """Paint the current window's background with a #rrggbb color ("" restores it)."""
        return self.request("set_background", color=str(color))

    def set_value(self, component, value):
        """Update a progress bar (0–100), a number or a slider (within its limits)."""
        return self.request("set_value", component=component, value=value)

    def set_rows(self, component, rows):
        """Replace all rows of a table; each row is a list of cells."""
        return self.request("set_rows", component=component, value=table_rows(rows))

    def add_row(self, component, row):
        """Append one row (a list of cells) to a table."""
        return self.request("add_row", component=component, value=table_rows([row])[0])

    def set_options(self, component, options):
        """Replace the options of a choice list, keeping the selection when it remains."""
        return self.request("set_options", component=component, value=[str(x) for x in options])

    @property
    def window_variables(self):
        """Data of the current window, kept between its events."""
        return self.window_scopes.setdefault(self.current_window, {})

    def go_state(self, state):
        """Apply a variation of the current window without copying its structure."""
        return self.request("go_state", state=state)

    def open_window(self, window, close_current=False):
        """Open another real window, optionally closing the current interface."""
        result = self.request("open_window", window=window, close_current=close_current)
        if result and result.get("reset"):
            self.window_scopes[window] = deepcopy(self.window_defaults.get(window, {}))

    def close_window(self):
        """Close the event's window; the last window ends the application."""
        return self.request("close_window")

    def show_page(self, component):
        """Reveal a page and its ancestors in the application window."""
        return self.request("show_page", component=component)

    def log(self, value):
        """Send text output immediately, without blocking the editor."""
        self.send({"type": "log", "channel": "stdout", "text": str(value) + "\n"})

    def message(self, value):
        """Show a message and wait for it to close before continuing the flow."""
        return self.request("message", prompt=str(value))

    def ask(self, kind, prompt, options=None):
        """Get declared input; Cancel ends the flow before the next action."""
        return self.request("ask", kind=kind, prompt=str(prompt), options=options or [])

    def confirm(self, prompt):
        """Continue only if the user answers Yes."""
        return self.request("confirm", prompt=str(prompt))

    def run(self, program, arguments=None, *, admin=False, check=True):
        """Run a separate argv with live output; a non-zero exit fails by default.

        stderr does not decide success. admin asks the application for pkexec; the
        editor never receives passwords. check=False lets your own functions handle
        a non-zero exit code explicitly.
        """
        if arguments is None:
            arguments = []
        if not isinstance(arguments, list) or any(not isinstance(arg, str) for arg in arguments):
            raise TypeError(tr("Arguments must be a list of texts."))
        result = self.request("run", program=program, arguments=arguments, admin=admin)
        code = result["code"]
        if result.get("crashed") or (check and code != 0):
            raise TaskError(tr("Task ended with code {code}.").format(code=code))
        return code

    def run_script(self, source, arguments=None, *, admin=False, check=True):
        """Run explicit Bash; arguments become $1… and are never concatenated into the script."""
        if not isinstance(source, str):
            raise TypeError(tr("The script must be text."))
        if arguments is None:
            arguments = []
        if not isinstance(arguments, list) or any(not isinstance(arg, str) for arg in arguments):
            raise TypeError(tr("Arguments must be a list of texts."))
        return self.run(
            "/bin/bash", ["-c", source, "makebench-script", *arguments], admin=admin, check=check
        )

    def handle_event(self, name):
        """Run the actions-file function bound to an event."""
        function = self.actions.get(name)
        if not callable(function):
            raise RuntimeError(tr("Event function not found: {name}.").format(name=name))
        return function(self)

    def call_action(self, name, value):
        """Resolve your own function only in this explicit run."""
        function = self.actions.get(name)
        if not callable(function):
            raise RuntimeError(tr("Function not found: {name}.").format(name=name))
        return function(self, value)


class Output(io.TextIOBase):
    """Turn print into output messages, keeping the JSON channel intact."""

    def __init__(self, send, channel):
        """Bind text writes to the application's stdout or stderr."""
        self.send, self.channel = send, channel

    def write(self, value):
        """Split large output into bounded messages so the editor stays responsive."""
        for offset in range(0, len(value), 8192):
            self.send(
                {"type": "log", "channel": self.channel, "text": value[offset : offset + 8192]}
            )
        return len(value)

    def flush(self):
        """The transport already writes immediately; there is no buffer to flush."""


def main():
    """Initialize a snapshot and serve events in order, outside the UI process."""
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())

    def send(value):
        """Serialize only protocol messages, one UTF-8 line each."""
        protocol.write(json.dumps(value, ensure_ascii=True, allow_nan=False) + "\n")
        protocol.flush()

    def receive():
        """Read one message; EOF ends the instance so no worker is orphaned."""
        line = sys.stdin.readline()
        if not line:
            raise EOFError(tr("The application was closed."))
        return json.loads(line)

    sys.stdout = Output(send, "stdout")
    sys.stderr = Output(send, "stderr")
    context = Context(send, receive)
    debugger = Debugger(send)
    generated = None
    source_filename = "<makebench-actions>"
    flow_id = None
    file_names = {}

    def failure(exc):
        """Locate an error in a generated block and/or a line of your own function."""
        line = source_line = None
        source_file = None
        for frame in traceback.extract_tb(exc.__traceback__):
            if frame.filename == "<makebench-generated>":
                line = frame.lineno
            if frame.filename in file_names or frame.filename == source_filename:
                source_line = frame.lineno
                source_file = file_names.get(frame.filename, "@actions")
        # The deepest generated line may sit in a block function called by the event.
        origin = next(
            (
                key
                for key, number in (generated.lines.items() if generated else [])
                if number == line
            ),
            (flow_id, None),
        )
        send(
            {
                "type": "error",
                "message": f"{type(exc).__name__}: {exc}",
                "flow": origin[0],
                "block": origin[1],
                "line": line,
                "source_line": source_line,
                "source_file": source_file,
                "traceback": traceback.format_exc(),
            }
        )

    try:
        snapshot = receive()
        set_language(snapshot.get("language"))
        project = Project.from_dict(snapshot["project"])
        for variable in project.variables:
            scope = (
                context.variables
                if variable.get("scope", "project") == "project"
                else context.window_scopes.setdefault(variable["window"], {})
            )
            scope[variable["name"]] = variable.get("initial")
        context.window_defaults = deepcopy(context.window_scopes)
        source = snapshot["source"]
        source_filename = snapshot.get("source_filename", source_filename)
        from makebench.core.source import SourceText
        from makebench.core.source_runtime import SnapshotImporter

        modules = {
            name: text
            for name, text in snapshot.get("source_files", {}).items()
            if name != "@actions"
        }
        if set(modules) != set(project.python_files):
            raise ValueError(tr("The snapshot does not contain all declared modules."))
        importer = SnapshotImporter(modules, Path(snapshot["root"]).resolve())
        importer.install()
        file_names = {source_filename: "@actions", **importer.filenames}
        source = SourceText(source, modules)
        generated = generate(project, source)
        if generated.diagnostics:
            raise ValueError("\n".join(generated.diagnostics))
        context.debugger = debugger
        debugger.configure(
            snapshot.get("debug", {}), source_filename, generated, context, file_names
        )
        transport = WorkerTransport(receive, debugger)
        context.receive_response = lambda identifier: transport.receive(response=identifier)
        root = Path(snapshot["root"]).resolve()
        os.chdir(root)
        sys.path.insert(0, str(root))
        namespace = {"__name__": "makebench_project_actions", "__file__": source_filename}
        exec(compile(source, source_filename, "exec"), namespace)
        context.actions = namespace
        handlers = {}
        compiled = {}
        exec(compile(generated.text, "<makebench-generated>", "exec"), compiled)
        for index, flow in enumerate(project.workflows, 1):
            handlers[flow["id"]] = compiled[f"on_event_{index}"]
        send({"type": "ready"})
        while True:
            message = transport.receive()
            if message.get("type") == "shutdown":
                break
            if message.get("type") != "event" or message.get("flow") not in handlers:
                continue
            context.current_window = message.get("window", project.root.id)
            flow_id = message["flow"]
            debugger.flow = flow_id
            debugger.component = next(
                f["event"]["component"] for f in project.workflows if f["id"] == flow_id
            )
            send({"type": "busy", "flow": flow_id})
            outcome = "success"
            try:
                if debugger.enabled:
                    sys.settrace(debugger.trace)
                handlers[flow_id](context)
            except Cancelled as exc:
                outcome = "cancelled"
                send({"type": "log", "channel": "status", "text": str(exc) + "\n"})
            except Exception as exc:
                outcome = "error"
                failure(exc)
            finally:
                sys.settrace(None)
                debugger.last_frame = None
            send({"type": "done", "flow": flow_id, "outcome": outcome})
    except (EOFError, DebugStopped):
        pass
    except BaseException as exc:
        failure(exc)
    finally:
        protocol.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
