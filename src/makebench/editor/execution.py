"""Test supervision in the editor's drawer, using the real runtime's signals."""

from datetime import datetime
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from makebench.runtime.window import append_output
from .theme import manager
from makebench.i18n import tr


class ExecutionMixin:
    """Present logs, tasks and origin without running code in the editor process."""

    def install_execution(self):
        """Add filters and commands over the same shared log."""
        self.log_entries = []
        self.task_items = {}
        self.task_running = {}
        self.test_started = None
        # Removing before reparenting avoids shifting and deleting the Problems tab.
        self.drawer.removeTab(self.drawer.indexOf(self.output_log))
        self.drawer.setMinimumHeight(145)
        output = QWidget()
        layout = QVBoxLayout(output)
        layout.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.output_filter = QComboBox()
        for label, key in [
            (tr("Everything"), None),
            (tr("Standard output"), "stdout"),
            (tr("Warnings / stderr"), "stderr"),
            (tr("Errors"), "error"),
            (tr("Execution"), "status"),
        ]:
            self.output_filter.addItem(label, key)
        self.output_filter.currentIndexChanged.connect(self.rebuild_output)
        row.addWidget(self.output_filter)
        self.process_info = QLabel(tr("No test started"))
        row.addWidget(self.process_info, 1)
        # Empty state with a direct action; hidden once the first test starts.
        self.test_now = QPushButton(tr("Test now · F5"))
        self.test_now.setToolTip(tr("Run the application in a separate test window"))
        self.test_now.clicked.connect(lambda: self.run_action.trigger())
        row.addWidget(self.test_now)
        for label, callback in [
            (
                tr("Copy"),
                lambda: (
                    __import__("PySide6.QtWidgets", fromlist=["QApplication"])
                    .QApplication.clipboard()
                    .setText(self.output_log.toPlainText())
                ),
            ),
            (tr("Clear"), self.clear_output),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(self.output_log, 1)
        self.output_log.show()
        self.drawer.insertTab(0, output, tr("Output"))
        tasks = QWidget()
        tl = QVBoxLayout(tasks)
        self.task_tree = QTreeWidget()
        self.task_tree.setHeaderLabels([tr("Task"), tr("Type"), tr("State"), tr("Duration")])
        tl.addWidget(self.task_tree)
        self.task_empty = QLabel(
            tr("Tasks started by the application appear here, with their result and duration.")
        )
        self.task_empty.setWordWrap(True)
        tl.addWidget(self.task_empty)
        self.cancel_task_button = QPushButton(tr("Cancel ordinary task and end test"))
        self.cancel_task_button.setEnabled(False)
        self.cancel_task_button.clicked.connect(self.stop_test)
        tl.addWidget(self.cancel_task_button)
        self.drawer.addTab(tasks, tr("Tasks"))
        error = QWidget()
        er = QVBoxLayout(error)
        self.run_error_label = QLabel()
        self.run_error_label.setWordWrap(True)
        er.addWidget(self.run_error_label)
        locate = QPushButton(tr("Go to source"))
        locate.clicked.connect(self.locate_test_error)
        er.addWidget(locate, 0, Qt.AlignmentFlag.AlignLeft)
        details = QPushButton(tr("Technical details"))
        details.setCheckable(True)
        er.addWidget(details, 0, Qt.AlignmentFlag.AlignLeft)
        self.run_trace = QPlainTextEdit()
        self.run_trace.setReadOnly(True)
        self.run_trace.hide()
        details.toggled.connect(self.run_trace.setVisible)
        er.addWidget(self.run_trace)
        self.drawer.addTab(error, tr("Error"))
        from makebench.terminal.qt import TerminalPanel

        self.terminal_panel = TerminalPanel(self)
        from pathlib import Path

        self.terminal_panel.directory_provider = lambda: (
            self.path.parent if self.path else Path.home()
        )
        self.drawer.addTab(self.terminal_panel, tr("Terminal"))
        from .debug import DebugPanel

        self.debug_panel = DebugPanel(self)
        self.drawer.addTab(self.debug_panel, tr("Debug"))
        self.debug_panel.command.connect(self.debug_command)
        self.debug_panel.locate.connect(self.locate_debug)
        self.source_editor.breakpoints_enabled = True
        self.generated_editor.breakpoints_enabled = True
        self.source_editor.breakpoint_requested.connect(self.toggle_source_breakpoint)
        self.generated_editor.breakpoint_requested.connect(self.toggle_generated_breakpoint)
        self.logic.breakpoint_requested.connect(self.toggle_block_breakpoint)
        self._next_debug = False
        self._debug_restart = False

        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self.update_test_time)
        self.clock.start()
        self._runtime_project_fingerprint = None
        self._debug_active = False
        manager().changed.connect(self.rebuild_output)

    def execution_fingerprint(self):
        """Compare the snapshot's code and document, excluding debug marks."""
        import hashlib, json

        data = self.project.to_dict()
        data["metadata"].pop("debug_breakpoints", None)
        from makebench.core.source import source_signature

        return hashlib.sha256(
            (json.dumps(data, sort_keys=True) + repr(source_signature(self.source.text))).encode()
        ).hexdigest()

    def monitor_runtime(self, window):
        """Connect a real process before its explicit start."""
        from .settings import preference

        if preference("test/clear"):
            self.clear_output()
        self.run_number += 1
        self.test_now.hide()
        self.test_started = time.monotonic()
        self._runtime_project_fingerprint = self.execution_fingerprint()
        self.process_info.setText(
            tr("Run {number} · {time}").format(
                number=self.run_number, time=f"{datetime.now():%H:%M:%S}"
            )
        )
        self.task_empty.setVisible(not self.task_items)
        self.add_output(
            "status",
            "\n──────── "
            + tr("Run {number} · {time}").format(
                number=self.run_number, time=f"{datetime.now():%H:%M:%S}"
            )
            + " ────────\n",
        )
        process = getattr(window.session, "process", None) or getattr(window, "process", None)
        if process:
            process.started.connect(
                lambda: self.process_info.setText(
                    tr("Run {number} · Python · PID {pid}").format(
                        number=self.run_number, pid=process.processId()
                    )
                )
            )
        if self._debug_active:
            self.debug_panel.changed({"state": "running"})
        window.session.debug_changed.connect(self.debug_changed)
        window.session.output.connect(self.add_output)
        window.session.busy_changed.connect(lambda _: self._update_actions())
        window.session.error.connect(self.show_test_error)
        window.status_changed.connect(self.set_test_status)
        window.session.task_changed.connect(self.update_task)
        window.session.admin_changed.connect(lambda active: self.stop_action.setEnabled(not active))
        window.session.stopped.connect(self.runtime_stopped)
        self.drawer.show()
        self.drawer.setCurrentIndex(0)

    def debug_project(self):
        """Start a new debuggable snapshot through an action separate from Run."""
        self._next_debug = True
        self.run_project()

    def debug_command(self, action):
        """Send only known controls to the process that owns the snapshot."""
        window = self.runtime_window
        if window is None or window.session.closed:
            return
        if action == "stop":
            self.stop_test()
            return
        window.session.debug_command(action)

    def breakpoints(self):
        """Read the project's declarative marks, never running them on open."""
        return self.project.metadata.get("debug_breakpoints", [])

    def toggle_source_breakpoint(self, line, path="@actions"):
        """Toggle one of your own lines and update the worker if debugging is active."""
        self._toggle_breakpoint(
            {"file": "source", "line": line, **({"path": path} if path != "@actions" else {})}
        )

    def toggle_generated_breakpoint(self, line):
        """Resolve a generated line to the original ID instead of storing an unstable line."""
        key = next(
            (key for key, number in self.logic.generated.lines.items() if number == line), None
        )
        if key:
            self.toggle_block_breakpoint(*key)

    def toggle_block_breakpoint(self, flow, block):
        """Store the origin by ID so breakpoints survive saves."""
        self._toggle_breakpoint({"file": "block", "flow": flow, "block": block})

    def _toggle_breakpoint(self, point):
        """Change marks through a transaction, keeping history and the Blockly workspace."""
        points = [dict(p) for p in self.breakpoints()]
        if point in points:
            points.remove(point)
        else:
            points.append(point)
        self._edit(lambda: self.project.metadata.update(debug_breakpoints=points), refresh=False)
        self.sync_breakpoints()
        window = self.runtime_window
        if window and not window.session.closed:
            window.session.debug_command("breakpoints", items=points)

    def sync_breakpoints(self):
        """Update margins without rebuilding the code or the Designer controls."""
        if not hasattr(self, "debug_panel"):
            return
        points = self.breakpoints()
        self.source_editor.breakpoints = {
            p["line"]
            for p in points
            if p.get("file") == "source"
            and p.get("path", "@actions") == "@actions"
            and type(p.get("line")) is int
        }
        for name, editor in getattr(self, "module_editors", {}).items():
            editor.breakpoints = {
                p["line"] for p in points if p.get("file") == "source" and p.get("path") == name
            }
            editor.numbers.update()
        block_keys = {(p.get("flow"), p.get("block")) for p in points if p.get("file") == "block"}
        blocks = {block for flow, block in block_keys if flow == self.logic.flow_id}
        self.generated_editor.breakpoints = {
            line
            for (flow, block), line in self.logic.generated.lines.items()
            if (flow, block) in block_keys
        }
        self.source_editor.numbers.update()
        self.generated_editor.numbers.update()
        self.logic.graph_panel.breakpoints = blocks
        for card in self.logic.graph_panel.cards.values():
            card.update()
        if self.logic.ready and self.logic.editor_kind.currentData() != "nodes":
            self.logic.page.runJavaScript(
                "window.makebench.setBreakpoints(" + __import__("json").dumps(list(blocks)) + ")"
            )

    def debug_changed(self, message):
        """Show the snapshot's observations and highlight their origin without editing the project."""
        message = dict(message)
        window = self.runtime_window
        if window:
            component = window.project.find(message.get("component"))
            flow = next(
                (f for f in window.project.workflows if f["id"] == message.get("flow")), None
            )
            if component:
                message["component_label"] = component.display_name
            if flow:
                message["flow_label"] = flow["name"]
        self.debug_panel.changed(message)
        if message.get("state") != "paused":
            for card in self.logic.graph_panel.cards.values():
                card.active = False
                card.update()
        if message.get("state") == "paused":
            self.test_status.setText(tr("Paused"))
            self.drawer.show()
            self.drawer.setCurrentWidget(self.debug_panel)
            self.locate_debug(message)

    def locate_debug(self, message):
        """Navigate only if the origin still matches the document being edited."""
        window = self.runtime_window
        if not window or self.project.id != window.project.id:
            return
        if self.execution_fingerprint() != self._runtime_project_fingerprint:
            self.debug_panel.status.setText(
                tr("Snapshot paused · project changed; restart to apply the changes.")
            )
            return
        if message.get("source_line"):
            self.open_code_file(message.get("source_file", "@actions"), message["source_line"])
        elif message.get("block"):
            self.set_mode("logic")
            self.logic.focus_block(message["flow"], message["block"])

    def add_output(self, channel, text):
        """Keep channels separate; stderr is a warning, an explicit failure is an error."""
        self.log_entries.append((channel, text))
        if sum(len(t) for _, t in self.log_entries) > 500000:
            self.log_entries = self.log_entries[-1000:]
        if self.output_filter.currentData() is None or channel == self.output_filter.currentData():
            tokens = manager().tokens
            color = (
                tokens["warning"]
                if channel == "stderr"
                else tokens["error"]
                if channel == "error"
                else tokens["muted"]
                if channel == "status"
                else None
            )
            append_output(self.output_log, text, color)

    def rebuild_output(self):
        """Filter the presentation, keeping the received history."""
        entries = list(self.log_entries)
        self.output_log.clear()
        self.log_entries = []
        for channel, text in entries:
            self.add_output(channel, text)

    def clear_output(self):
        """Clear only the run's observation, never deleting files or logic."""
        self.log_entries = []
        self.output_log.clear()

    def update_task(self, data):
        """Show the duration and result of ordinary or administrative tasks."""
        self.task_empty.hide()
        key = f"{self.run_number}:{data['id']}"
        item = self.task_items.get(key)
        if item is None:
            item = QTreeWidgetItem()
            self.task_tree.addTopLevelItem(item)
            self.task_items[key] = item
        if data["state"] == "running":
            self.task_running[key] = time.monotonic() - data.get("duration", 0)
        else:
            self.task_running.pop(key, None)
        item.setText(0, data["program"])
        item.setText(1, tr("Administrative") if data["admin"] else tr("Ordinary"))
        item.setText(
            2,
            {
                "running": tr("Running"),
                "completed": tr("Completed"),
                "failed": tr("Not completed"),
            }.get(data["state"], data["state"]),
        )
        item.setText(3, f"{data.get('duration', 0):.1f} s")
        self.cancel_task_button.setEnabled(not data["admin"] and data["state"] == "running")
        if data["admin"]:
            self.cancel_task_button.setToolTip(
                tr(
                    "Wait for the task authorized by the system to finish; there is no forced administrative interruption."
                )
            )

    def show_test_error(self, error):
        """Show the cause and origin, keeping the traceback collapsed by default."""
        self._test_error = error
        self.run_error_label.setText(error["message"])
        self.run_trace.setPlainText(error.get("traceback", ""))
        self.run_trace.hide()
        self.add_output("error", tr("[Error]") + " " + error["message"] + "\n")
        self.drawer.show()
        self.drawer.setCurrentIndex(4)
        self.test_status.setText(tr("Error"))

    def locate_test_error(self):
        """Reuse the snapshot's block/line map, never guessing the origin."""
        if self.runtime_window and hasattr(self, "_test_error"):
            self._locate_runtime_error(self._test_error, self.runtime_window)

    def update_test_time(self):
        """Warn when editing drifts away from the snapshot that is running."""
        for key, started in self.task_running.items():
            self.task_items[key].setText(3, f"{time.monotonic() - started:.1f} s")
        window = self.runtime_window
        from .settings import preference

        if (
            window
            and not window.session.closed
            and self.test_started
            and preference("test/duration")
        ):
            self.statusBar().showMessage(
                tr("Test running · {seconds} s").format(
                    seconds=f"{time.monotonic() - self.test_started:.0f}"
                )
            )
        if (
            window
            and not window.session.closed
            and self._runtime_project_fingerprint != self.execution_fingerprint()
        ):
            self.set_test_status(tr("Project changed · F5 to restart"))

    def set_test_status(self, text):
        """Keep the header compact, with the full text available in the tooltip."""
        compact = text
        for phrase, label in [
            (tr("administrative"), tr("System authorization")),
            (tr("Waiting for an answer"), tr("Waiting for an answer")),
            (tr("Starting"), tr("Starting")),
            (tr("Flow completed"), tr("Completed")),
            (tr("Flow cancelled"), tr("Interrupted")),
            (tr("error"), tr("Error")),
            (tr("Running flow"), tr("Running")),
            (tr("Application running"), tr("Running")),
            (tr("Stopping"), tr("Stopping")),
            (tr("ended"), tr("Stopped")),
            (tr("Project changed"), tr("Changes · F5 to restart")),
        ]:
            if phrase.casefold() in text.casefold():
                compact = label
                break
        self.test_status.setText(compact)
        self.test_status.setToolTip(text)

    def runtime_stopped(self):
        """Record the end with the real duration, without mixing in editing diagnostics."""
        self.debug_panel.changed({"state": "stopped"})
        for card in self.logic.graph_panel.cards.values():
            card.active = False
            card.update()
        elapsed = time.monotonic() - self.test_started if self.test_started else 0
        for key in list(self.task_running):
            if key.startswith(str(self.run_number) + ":"):
                self.task_items[key].setText(2, tr("Interrupted"))
                self.task_items[key].setText(
                    3, f"{time.monotonic() - self.task_running.pop(key):.1f} s"
                )
        self.test_status.setText(tr("Stopped"))
        self.process_info.setText(
            tr("Run {number} · ended · {seconds} s").format(
                number=self.run_number, seconds=f"{elapsed:.1f}"
            )
        )
        self.cancel_task_button.setEnabled(False)
        self.add_output(
            "status", "\n" + tr("Run ended · {seconds} s").format(seconds=f"{elapsed:.1f}") + "\n"
        )
