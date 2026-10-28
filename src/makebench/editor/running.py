# SPDX-License-Identifier: GPL-3.0-or-later
"""Running the project from the editor and showing its errors."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QMessageBox,
)

from makebench.core.project import (
    ProjectError,
)
from makebench.i18n import tr


class RunMixin:
    """Running the project from the editor and showing its errors. Mixed into MainWindow."""

    def run_project(self):
        """Test an explicit snapshot; editing and opening still never run code."""
        if self.runtime_window is not None and not self.runtime_window.session.closed:
            if self.runtime_window.session.admin_active:
                self.statusBar().showMessage(
                    tr("Wait for the administrative task to finish before restarting."), 7000
                )
                return
            from .settings import preference

            if self.runtime_window.session.busy and preference("test/confirm_restart"):
                choice = QMessageBox.warning(
                    self,
                    tr("Restart test?"),
                    tr(
                        "A task is in progress. Restarting ends the test and the ordinary processes."
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if choice != QMessageBox.StandardButton.Yes:
                    return
            if not self.runtime_window.stop():
                self.statusBar().showMessage(
                    tr("Wait for the administrative task to finish before restarting."), 7000
                )
                return
            self._restart_pending = True
            return
        if not self._finish_field_edit():
            return
        if not self.confirm_trust():
            return
        from makebench.runtime.window import RuntimeWindow

        if self.project.application.get("backend", "qt") == "gtk":
            from makebench.runtime.gtk_bridge import GtkRuntimeBridge as RuntimeWindow
        try:
            window = RuntimeWindow(
                self.project,
                self.source.text,
                self.assets.read,
                self.path.parent if self.path else None,
                self.source.path,
                self,
                supervision=False,
            )
        except (ProjectError, OSError) as exc:
            if self.project.application.get("backend", "qt") == "gtk":
                self._show_error(exc, tr("Could not start the test"))
            self.sync_problems()
            self.drawer.show()
            self.drawer.setCurrentIndex(1)
            self.statusBar().showMessage(tr("Test blocked: resolve the items in Problems."), 7000)
            return
        if self.runtime_window is not None:
            self.runtime_window.close()
        self.runtime_window = window
        window.locate_requested.connect(lambda error: self._locate_runtime_error(error, window))
        window.shutdown_finished.connect(self._runtime_stopped)
        window.destroyed.connect(lambda: self._runtime_destroyed(window))
        self._debug_active = getattr(self, "_next_debug", False)
        self._next_debug = False
        config = {"enabled": self._debug_active, "breakpoints": self.breakpoints()}
        if hasattr(window.session, "snapshot"):
            window.session.snapshot["debug"] = config
        else:
            window.debug_config = config
        self.monitor_runtime(window)
        window.show()
        window.start()

    def _runtime_destroyed(self, window):
        """Remove only the reference of the window that was actually destroyed."""
        if self.runtime_window is window:
            self.runtime_window = None

    def _runtime_stopped(self):
        """Resume closing after the supervisor finishes cleaning up the processes."""
        self._update_actions()
        if self._closing_after_runtime:
            QTimer.singleShot(0, self.close)
        elif getattr(self, "_restart_pending", False):
            self._restart_pending = False
            QTimer.singleShot(0, self.run_project)

    def _locate_runtime_error(self, error, window):
        """Find the current block; own lines only count if the text did not change."""
        if self.project.id != window.project.id:
            self.statusBar().showMessage(
                tr("The error belongs to another project open in the run."), 7000
            )
            return
        from makebench.core.source import source_signature

        if error.get("source_line") and source_signature(self.source.text) == source_signature(
            window.source
        ):
            self.open_code_file(error.get("source_file", "@actions"), error["source_line"])
        elif error.get("block"):
            flow = next((f for f in self.project.workflows if f["id"] == error.get("flow")), None)
            if flow:
                self.logic.sync(flow["id"])
                self.tabs.setCurrentIndex(1)
                self.logic.focus_block(flow["id"], error["block"])
        self.raise_()
        self.activateWindow()

    def _show_error(self, error, action: str | None = None) -> None:
        """Show recoverable failures without closing the editor.

        `error` is a message or an exception; `action` names what failed and becomes
        the title, while technical details stay collapsed.
        """
        from .errors import show_error

        show_error(self.project_dialog_parent(), error, action)
