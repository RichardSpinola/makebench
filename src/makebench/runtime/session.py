# SPDX-License-Identifier: MIT
"""Qt coordination of the Python worker, tasks and interface calls."""

from __future__ import annotations
import json
import codecs
from pathlib import Path
import os
import signal
import sys
import time

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from makebench.i18n import language, tr
from .process import TaskProcess, signal_group


class RuntimeSession(QObject):
    """Run a snapshot without importing functions into the editor process."""

    ready = Signal()
    busy_changed = Signal(bool)
    output = Signal(str, str)
    request = Signal(dict)
    error = Signal(dict)
    event_done = Signal(dict)
    stopped = Signal()
    debug_changed = Signal(dict)
    admin_changed = Signal(bool)
    task_changed = Signal(dict)

    def __init__(self, project, source, root, source_filename, parent=None, testing=True):
        """Keep the snapshot and transport; construction does not start execution."""
        super().__init__(parent)
        self.project = project
        self.root = Path(root)
        from makebench.core.source import source_files

        self.snapshot = {
            "source_files": source_files(source),
            "project": project.to_dict(),
            "source": source,
            "root": str(self.root),
            "source_filename": str(source_filename),
            "language": language(),
        }
        if project.metadata.get("collections"):
            from makebench.core.datastore import data_path

            self.snapshot["data_path"] = str(data_path(project, testing))
        self.process = QProcess(self)
        self.process.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession)
        environment = QProcessEnvironment.systemEnvironment()
        package_root = str(Path(__file__).resolve().parents[2])
        old = environment.value("PYTHONPATH")
        environment.insert("PYTHONPATH", package_root + (os.pathsep + old if old else ""))
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("PYTHONDONTWRITEBYTECODE", "1")
        self.process.setProcessEnvironment(environment)
        self.process.setProgram(sys.executable)
        self.process.setArguments(["-u", "-m", "makebench.runtime.worker"])
        self.process.setWorkingDirectory(str(self.root))
        self.process.started.connect(self._started)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self._stderr)
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._finished)
        self.stderr_decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.buffer = b""
        self.reported_error = False
        self.pgid = 0
        self.task = None
        self.tasks = []
        self.busy = False
        self.active = False
        self.closed = True
        self.stopping = False
        self.admin_active = False
        self.kill_timer = QTimer(self)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.setInterval(700)
        self.kill_timer.timeout.connect(self._force_stop)

    def start(self):
        """Start the explicit run, including loading the user's own functions."""
        self.closed = False
        self.active = False
        self.stopping = False
        self.busy = True
        self.busy_changed.emit(True)
        self.process.start()

    def _started(self):
        """Deliver the snapshot once the input channel is available."""
        self.pgid = int(self.process.processId())
        if self.stopping:
            signal_group(self.pgid, signal.SIGTERM)
        else:
            self.send(self.snapshot)

    def send(self, value):
        """Send a message without blocking the Qt event loop."""
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.write(
                (json.dumps(value, ensure_ascii=True, allow_nan=False) + "\n").encode()
            )

    def debug_command(self, action, **values):
        """Send control to the worker's independent reader, even during dialogs."""
        self.send({"type": "debug", "action": action, **values})

    def reply(self, identifier, value=None, *, ok=True, cancelled=False, error=""):
        """Reply to a UI request or an external task."""
        self.send(
            {
                "type": "response",
                "id": identifier,
                "value": value,
                "ok": ok,
                "cancelled": cancelled,
                "error": error,
            }
        )

    def dispatch(self, flow_id):
        """Accept one event at a time; clicks during work do not queue installations."""
        if not self.active or self.busy or self.stopping:
            return False
        self.busy = True
        self.busy_changed.emit(True)
        flow = next(f for f in self.project.workflows if f["id"] == flow_id)
        self.send(
            {
                "type": "event",
                "flow": flow_id,
                "window": self.project.window_of(flow["event"]["component"]).id,
            }
        )
        return True

    def _read(self):
        """Reassemble messages split in the pipe and keep a per-message limit."""
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if len(line) > 2_000_000:
                self.error.emit({"message": tr("The process reply exceeded the limit.")})
                self.stop()
                return
            try:
                self._message(json.loads(line))
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                self.error.emit(
                    {"message": tr("Invalid execution protocol: {error}").format(error=exc)}
                )
                self.stop()
                return
        if len(self.buffer) > 2_000_000:
            self.error.emit({"message": tr("Incomplete reply exceeded the limit.")})
            self.stop()

    def _message(self, message):
        """Forward only known protocol types; messages are never evaluated."""
        if self.stopping:
            return
        kind = message.get("type")
        if kind == "ready":
            self.active = True
            self.busy = False
            self.busy_changed.emit(False)
            self.ready.emit()
        elif kind == "busy":
            self.reported_error = False
            self.busy = True
            self.busy_changed.emit(True)
        elif kind == "done":
            self.busy = False
            self.busy_changed.emit(False)
            self.event_done.emit(message)
        elif kind == "debug":
            self.debug_changed.emit(message)
        elif kind == "log":
            self.output.emit(message["channel"], message["text"])
        elif kind == "error":
            self.reported_error = True
            self.error.emit(message)
        elif kind == "request":
            if message["method"] == "run":
                self._run_task(message)
            else:
                self.request.emit(message)

    def _stderr(self, final=False):
        """Forward direct descriptor output and interpreter errors."""
        text = self.stderr_decoder.decode(bytes(self.process.readAllStandardError()), final=final)
        if text:
            self.output.emit("stderr", text)

    def _run_task(self, message):
        """Keep the task in the Qt supervisor, even if the worker fails."""
        if self.task is not None:
            self.reply(message["id"], ok=False, error=tr("A task is already running."))
            return
        try:
            task = TaskProcess(
                message["program"], message["arguments"], self.root, message["admin"], self
            )
        except (ValueError, OSError) as exc:
            self.reply(message["id"], ok=False, error=str(exc))
            return
        task.started_at = time.monotonic()
        task.identifier = message["id"]
        task.program_label = str(message["program"])
        self.task = task
        self.tasks.append(task)
        self.task_changed.emit(
            {
                "id": task.identifier,
                "program": task.program_label,
                "admin": task.admin,
                "state": "running",
                "duration": 0,
            }
        )
        self.admin_active = task.admin
        self.admin_changed.emit(self.admin_active)
        task.output.connect(self.output)
        task.completed.connect(lambda result: self._task_finished(task, message["id"], result))
        task.start()

    def _task_finished(self, task, identifier, result):
        """Release the administrative lock only after the observed end."""
        self.task_changed.emit(
            {
                "id": task.identifier,
                "program": task.program_label,
                "admin": task.admin,
                "state": "completed"
                if result.get("ok") and result.get("value", {}).get("code") == 0
                else "failed",
                "duration": time.monotonic() - task.started_at,
            }
        )
        if self.task is task:
            self.task = None
        if not self.stopping and task in self.tasks:
            self.tasks.remove(task)
            task.pgid = 0
            task.deleteLater()
        self.admin_active = False
        self.admin_changed.emit(False)
        if result.get("ok"):
            self.output.emit(
                "status",
                tr("Task ended with code {code}.").format(code=result["value"]["code"]) + "\n",
            )
        if not self.stopping:
            self.send({"type": "response", "id": identifier, **result})
        if self.process.state() == QProcess.ProcessState.NotRunning and not self.stopping:
            self.stop()
        self._maybe_stopped()

    def _process_error(self, error):
        """Explain a start failure without waiting for a finished signal that will not come."""
        if error == QProcess.ProcessError.FailedToStart:
            self.error.emit({"message": self.process.errorString()})
            self.stop()

    def _finished(self, code, status):
        """Record an unexpected exit and clean up remaining user tasks."""
        self._read()
        self._stderr(True)
        self.active = False
        if not self.stopping:
            if not self.reported_error:
                self.error.emit(
                    {"message": tr("The Python process ended (code {code}).").format(code=code)}
                )
            if not self.admin_active:
                self.stop()
        self._maybe_stopped()

    def stop(self):
        """Cancel the worker and ordinary groups; block closing while an elevated task runs."""
        if self.admin_active:
            return False
        if self.closed or self.stopping:
            return True
        self.stopping = True
        self.active = False
        signal_group(self.pgid, signal.SIGTERM)
        if not self.pgid:
            self.process.terminate()
        for task in self.tasks:
            task.terminate()
        self.kill_timer.start()
        return True

    def _force_stop(self):
        """After a short delay, end groups that ignored TERM, including descendants."""
        signal_group(self.pgid, signal.SIGKILL)
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        for task in self.tasks:
            task.terminate(force=True)
        self._maybe_stopped()

    def _maybe_stopped(self):
        """Finish only after cleaning up the groups and supervised processes."""
        if not self.stopping or self.kill_timer.isActive():
            return
        running = self.process.state() != QProcess.ProcessState.NotRunning or any(
            task.process.state() != QProcess.ProcessState.NotRunning for task in self.tasks
        )
        if not running and not self.closed:
            self.closed = True
            self.busy = False
            self.busy_changed.emit(False)
            self.stopped.emit()
