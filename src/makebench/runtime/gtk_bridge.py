# SPDX-License-Identifier: MIT
"""Qt adapter for the GTK test: supervision only, no Qt controls in the application."""

import json
from pathlib import Path
import sys
import tempfile
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal
from makebench.core.project import Project, ProjectError
from makebench.core.codegen import generate
from makebench.core.environment import gtk_support, GTK_HELP
from makebench.core.lines import LineReader
from makebench.i18n import language, tr


class GtkSession(QObject):
    """Signals compatible with the workbench's existing test drawer."""

    output = Signal(str, str)
    busy_changed = Signal(bool)
    error = Signal(dict)
    task_changed = Signal(dict)
    debug_changed = Signal(dict)
    inspection = Signal(dict)
    admin_changed = Signal(bool)
    stopped = Signal()
    ready = Signal()
    event_done = Signal(dict)

    def __init__(self, parent):
        """Only store the observed state of the GTK process."""
        super().__init__(parent)
        self.closed = True
        self.active = False
        self.busy = False
        self.admin_active = False

    def debug_command(self, action, **values):
        """Forward commands to the neutral worker through the GTK bridge."""
        self.parent().command({"command": "debug", "action": action, **values})


class GtkRuntimeBridge(QObject):
    """Launch GTK only on start/F5 and keep references until it really ends."""

    locate_requested = Signal(dict)
    shutdown_finished = Signal()
    status_changed = Signal(str)

    def __init__(
        self,
        project,
        source,
        read_asset,
        root=None,
        source_filename=None,
        parent=None,
        supervision=False,
    ):
        """Validate and copy the snapshot to staging without running project content."""
        super().__init__(parent)
        if not gtk_support()["gtk4"]:
            raise ProjectError(GTK_HELP)
        diagnostics = generate(project, source).diagnostics
        if diagnostics:
            raise ProjectError("\n".join(diagnostics))
        self.project = Project.from_dict(project.to_dict())
        self.source = source
        self.session = GtkSession(self)
        self.temp = tempfile.TemporaryDirectory(prefix="makebench-gtk-")
        directory = Path(self.temp.name)
        self.path = directory / "project.makebench.json"
        self.path.write_text(json.dumps(project.to_dict(), ensure_ascii=False), encoding="utf-8")
        (directory / "project.actions.py").write_text(source, encoding="utf-8")
        from makebench.core.source import source_files, ENTRY_FILE

        for name, text in source_files(source).items():
            if name != ENTRY_FILE:
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
        for name in project.asset_paths():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read_asset(name))
        self.process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert(
            "PYTHONPATH", str(Path(__file__).resolve().parents[2]) + ":" + env.value("PYTHONPATH")
        )
        self.process.setProcessEnvironment(env)
        env.insert("MAKEBENCH_LANGUAGE", language())
        self.process.setProcessEnvironment(env)
        self.process.setProgram(sys.executable)
        self.process.setArguments(
            [
                "-u",
                "-m",
                "makebench.gtk_runtime.launcher",
                str(self.path),
                "--supervised",
                "--working-directory",
                str(Path(root).resolve() if root else directory),
                "--source-filename",
                str(source_filename or directory / "project.actions.py"),
            ]
        )
        self.lines = LineReader()
        self._stderr = b""
        self.debug_config = None
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)

    def start(self):
        """Start the explicit GTK process, keeping the editor free to respond."""
        if self.debug_config:
            (self.path.parent / "debug.json").write_text(
                json.dumps(self.debug_config), encoding="utf-8"
            )
        self.session.closed = False
        self.session.busy = True
        self.session.busy_changed.emit(True)
        self.process.start()

    def command(self, value):
        """Send supervision commands to the independent GTK process."""
        self.process.write((json.dumps(value) + "\n").encode())

    def show(self):
        """Re-show GTK windows already open without creating another instance."""
        if self.process.state() == QProcess.ProcessState.Running:
            self.command({"command": "raise"})

    def raise_(self):
        """Compatibility with the editor's focus commands."""
        self.show()

    def activateWindow(self):
        """Ask the toolkit and compositor of the GTK application to present it."""
        self.show()

    def read(self):
        """Reassemble the JSON protocol; project code is never evaluated in the editor."""
        try:
            lines = self.lines.feed(bytes(self.process.readAllStandardOutput()))
        except ValueError:
            self.session.error.emit({"message": tr("GTK reply exceeded the limit.")})
            self.stop()
            return
        for line in lines:
            try:
                self.message(json.loads(line))
            except (ValueError, KeyError, TypeError) as exc:
                self.session.error.emit(
                    {"message": tr("Invalid GTK protocol: {error}").format(error=exc)}
                )

    def message(self, value):
        """Turn GTK observations into the same signals used by the Qt runtime."""
        kind = value["type"]
        session = self.session
        if kind == "log":
            session.output.emit(value["channel"], value["text"])
        elif kind == "status":
            self.status_changed.emit(value["text"])
        elif kind == "error":
            session.error.emit(value)
        elif kind == "ready":
            session.active = True
            session.ready.emit()
        elif kind == "busy":
            session.busy = value["value"]
            session.busy_changed.emit(session.busy)
        elif kind == "admin":
            session.admin_active = value["value"]
            session.admin_changed.emit(session.admin_active)
        elif kind == "task":
            session.task_changed.emit(value)
        elif kind == "debug":
            session.debug_changed.emit(value)
        elif kind == "inspection":
            session.inspection.emit(value)
        elif kind == "done":
            session.event_done.emit(value)

    def read_error(self):
        """Forward native GTK messages as diagnostic stderr."""
        text = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if text:
            self.session.output.emit("stderr", text)

    def stop(self):
        """Never force GTK or an administrative task; wait for ordinary groups to be cleaned up."""
        if self.session.admin_active:
            return False
        if not self.session.closed:
            self.command({"command": "stop"})
        return True

    def close(self):
        """Close through the protocol without abandoning test processes."""
        return self.stop()

    def setEnabled(self, _enabled):
        """Lifecycle compatibility; sensitivity belongs to GTK."""

    def process_error(self, error):
        """A start failure gets no finished signal from QProcess."""
        if error == QProcess.ProcessError.FailedToStart:
            self.session.error.emit({"message": self.process.errorString()})
            self.finished()

    def finished(self, *_args):
        """Release the snapshot only after the GTK process has ended."""
        self.read()
        self.read_error()
        self.session.closed = True
        self.session.busy = False
        self.session.active = False
        self.session.busy_changed.emit(False)
        self.session.stopped.emit()
        self.shutdown_finished.emit()
        self.temp.cleanup()
