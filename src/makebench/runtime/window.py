# SPDX-License-Identifier: MIT
"""Window for testing applications, collecting input and following tasks."""

from __future__ import annotations
from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QPlainTextEdit,
    QSlider,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from makebench.core.codegen import generate
from makebench.core.project import Project, ProjectError
from .session import RuntimeSession
from makebench.core.project import ComponentKind, valid_date
from makebench.ui.renderer import (
    append_table_row,
    date_text,
    configure_table,
    fill_choice,
    selected_table_record,
    table_contents,
    selected_table_row,
    range_value,
    set_date,
    set_range_value,
    set_table_rows,
)
from makebench.ui.chart import ChartWidget
from makebench.ui.table import RecordTable
from .view import RuntimeView
from makebench.i18n import tr


def append_output(editor, text, color=None):
    """Append chunks without inventing line breaks and bound the retained text."""
    bar = editor.verticalScrollBar()
    position = bar.value()
    follow = position >= bar.maximum() - 2
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    style = QTextCharFormat()
    style.setForeground(QColor(color) if color else editor.palette().text().color())
    cursor.insertText(text, style)
    if editor.document().characterCount() > 500_000:
        trim = QTextCursor(editor.document())
        trim.setPosition(0)
        trim.setPosition(
            editor.document().characterCount() - 400_000, QTextCursor.MoveMode.KeepAnchor
        )
        trim.removeSelectedText()
    if follow:
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()
    else:
        bar.setValue(position)


from .navigation import RuntimeNavigation, apply_frame, install_menu_bar


class RuntimeWindow(RuntimeNavigation, QMainWindow):
    """Supervise an explicit run and never change the editor's project."""

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
        supervision=True,
    ):
        """Validate the snapshot; construction never imports or runs user functions."""
        super().__init__(parent, Qt.WindowType.Window)
        project = Project.from_dict(project.to_dict())
        generated = generate(project, source)
        if generated.diagnostics:
            raise ProjectError("\n".join(generated.diagnostics))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.supervision = supervision
        self.project = project
        self.source = source
        self.dialogs = set()
        self.last_error = {}
        self.close_pending = False
        self.temporary = (
            tempfile.TemporaryDirectory(prefix="makebench-run-") if root is None else None
        )
        root = Path(root or self.temporary.name).resolve()
        self.session = RuntimeSession(
            project,
            source,
            root,
            source_filename or str(root / "project.actions.py"),
            self,
            testing=supervision,
        )
        self.root_window_id = project.entry_window or project.root.id
        initial = project.find(self.root_window_id)
        self.setWindowTitle(
            (tr("[Test]") + " " if supervision else "")
            + initial.properties.get("title", project.name)
        )
        width = initial.properties.get("width", 640)
        height = initial.properties.get("height", 480) + (220 if supervision else 0)
        icon_path = initial.properties.get("icon") or project.application.get("icon")
        if icon_path:
            from PySide6.QtGui import QIcon, QPixmap

            try:
                pixmap = QPixmap()
                pixmap.loadFromData(read_asset(icon_path))
                self.setWindowIcon(QIcon(pixmap))
            except (OSError, ProjectError):
                pass
        self.resize(width, height)
        if not initial.properties.get("resizable", True) and not initial.properties.get(
            "fullscreen"
        ):
            self.setFixedSize(width, height)
        central = QWidget()
        layout = QVBoxLayout(central)
        controls = QHBoxLayout()
        self.state = QLabel(tr("Ready to start."))
        self.state.setTextFormat(Qt.TextFormat.PlainText)
        controls.addWidget(self.state, 1)
        self.stop_button = QPushButton(tr("Stop run"))
        self.stop_button.clicked.connect(self.stop)
        controls.addWidget(self.stop_button)
        layout.addLayout(controls)
        split = QSplitter(Qt.Orientation.Vertical)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.view = RuntimeView(project, read_asset, window_root=initial)
        scroll.setWidget(self.view)
        split.addWidget(scroll)
        output_box = QWidget()
        output_layout = QVBoxLayout(output_box)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(QLabel(tr("Makebench supervision · not part of your application")))
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(3000)
        output_layout.addWidget(self.output)
        error_row = QHBoxLayout()
        self.error_label = QLabel()
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.setWordWrap(True)
        error_row.addWidget(self.error_label, 1)
        self.locate = QPushButton(tr("Go to error"))
        self.locate.setEnabled(False)
        self.locate.clicked.connect(lambda: self.locate_requested.emit(self.last_error))
        error_row.addWidget(self.locate)
        output_layout.addLayout(error_row)
        self.details_button = QPushButton(tr("Error details"))
        self.details_button.setCheckable(True)
        self.details_button.setEnabled(False)
        output_layout.addWidget(self.details_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.error_details = QPlainTextEdit()
        self.error_details.setReadOnly(True)
        self.error_details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.error_details.setMaximumHeight(180)
        self.error_details.hide()
        self.details_button.toggled.connect(self.error_details.setVisible)
        output_layout.addWidget(self.error_details)
        split.addWidget(output_box)
        split.setSizes([480, 220])
        layout.addWidget(split)
        self.setCentralWidget(central)
        self.supervision_box = output_box
        if not supervision:
            output_box.hide()
            self.stop_button.hide()
            self.state.hide()
        self.install_navigation(read_asset)
        install_menu_bar(self, initial, self)
        apply_frame(self, initial, (scroll.viewport(), self.view))
        self.view.clicked.connect(self._clicked)
        self.view.changed.connect(self._changed)
        self.session.ready.connect(self._ready)
        self.session.request.connect(self._request)
        self.session.output.connect(self._output)
        self.session.error.connect(self._error)
        self.session.event_done.connect(self._done)
        self.session.busy_changed.connect(self._busy)
        self.session.admin_changed.connect(self._admin_changed)
        self.session.stopped.connect(self._stopped)

    def set_status(self, text):
        """Update local supervision and the editor without coupling the runtime to the workbench."""
        self.state.setText(text)
        self.status_changed.emit(text)

    def start(self):
        """Run your own source and prepare events only on explicit request."""
        self.set_status(tr("Starting application…"))
        self.session.start()

    def _ready(self):
        """Fire the window start once, after the functions load in the worker."""
        from makebench.terminal.components import start_components

        start_components(self.view.window_root, self.view.widgets, self.session.root)
        self.set_status(tr("Application running."))
        self.queue_event(self.root_window_id, "start")
        self.start_timer(self.root_window_id)

    def _changed(self, identifier):
        """Fire a control's change flow; edits made while a task runs are not queued."""
        if not self.session.busy:
            self.queue_event(identifier, "change")

    def _clicked(self, identifier):
        """Fire a button's flow; concurrent tasks are not queued."""
        if not self.session.busy:
            self.queue_event(identifier, "click")

    def _busy(self, busy):
        """Update the click lock while the editor stays responsive."""
        for view in self.views.values():
            view.set_busy(busy)
        if busy and self.session.active:
            for node in self.project.walk():
                if node.kind.value == "progress":
                    _, progress = self.widget_for(node.id)
                    if progress:
                        progress.setValue(0)

            self.set_status(tr("Running flow…"))
            self.last_error = {}
            self.error_label.clear()
            self.locate.setEnabled(False)
            self.details_button.setChecked(False)
            self.details_button.setEnabled(False)
            self.error_details.clear()

    def _output(self, channel, text):
        """Show stdout/stderr live in the window and in the application panels."""
        from makebench.ui.theme import PALETTES

        tokens = PALETTES["dark" if self.palette().window().color().lightness() < 128 else "light"]
        color = (
            tokens["warning"]
            if channel == "stderr"
            else tokens["error"]
            if channel == "error"
            else tokens["muted"]
            if channel == "status"
            else None
        )
        append_output(self.output, text, color)
        if channel != "status":
            view = self.views.get(self.current_window) if hasattr(self, "views") else None
            if view:
                for node in view.window_root.walk():
                    if node.kind == ComponentKind.OUTPUT:
                        append_output(view.widgets[node.id], text, color)
        if not self.supervision and self.parent() is None and channel != "status":
            import sys

            stream = sys.stderr if channel in {"stderr", "error"} else sys.stdout
            if stream:
                try:
                    stream.write(text)
                    stream.flush()
                except (OSError, ValueError):
                    pass

    def _error(self, error):
        """Keep the origin and details without closing the editor or repeating the flow."""
        self.last_error = error
        message = error["message"].removeprefix("TaskError: ")
        self.error_label.setText(message)
        self.locate.setEnabled(bool(error.get("block") or error.get("source_line")))
        self.error_details.setPlainText(error.get("traceback", ""))
        self.details_button.setEnabled(bool(error.get("traceback")))
        self._output("error", tr("[Error]") + " " + message + "\n")
        self.set_status(tr("Error while running. Check the output."))
        if not self.supervision and self.parent() is None:
            dialog = QMessageBox(self)
            dialog.setWindowTitle(tr("Could not complete the operation"))
            dialog.setTextFormat(Qt.TextFormat.PlainText)
            dialog.setText(message)
            dialog.setDetailedText(error.get("traceback", ""))
            dialog.setStandardButtons(QMessageBox.StandardButton.Close)
            from makebench.ui.dialogs import translate_buttons

            translate_buttons(dialog)
            dialog.show()
            self._error_dialog = dialog

    def _done(self, message):
        """Tell success, cancellation and failure apart, using the flow's real result."""
        labels = {
            "success": tr("Flow completed."),
            "cancelled": tr("Flow cancelled."),
            "error": tr("The flow ended with an error."),
        }
        self.set_status(labels[message["outcome"]])
        self._output("status", labels[message["outcome"]] + "\n")
        if message["outcome"] != "success":
            self._queued_flows.clear()
        QTimer.singleShot(0, self.dispatch_next)
        QTimer.singleShot(0, self.finish_closing)

    def _admin_changed(self, active):
        """Keep the elevated task supervised without offering a forced stop."""
        self.stop_button.setEnabled(not active)
        if active:
            self.set_status(
                tr(
                    "Administrative task: complete or cancel authentication in the system dialog. Wait for it to finish before closing."
                )
            )

    def _request(self, request):
        """Serve only operations declared in the context contract."""
        identifier = request["id"]
        method = request["method"]
        try:
            component = request.get("component")
            view, widget = self.widget_for(component)
            if method.startswith("terminal_"):
                from makebench.terminal.components import terminal_request

                if hasattr(widget, "terminal"):
                    widget.terminal.root = self.session.root
                self.session.reply(identifier, terminal_request(widget, method, request))
            elif method == "read":
                if widget is None:
                    raise ValueError(tr("The component does not exist."))
                attribute = request["attribute"]
                if attribute == "text":
                    value = (
                        widget.toPlainText()
                        if isinstance(widget, QPlainTextEdit)
                        else widget.currentText()
                        if isinstance(widget, QComboBox)
                        else date_text(widget)
                        if isinstance(widget, QDateEdit)
                        else widget.text()
                    )
                elif attribute == "selected":
                    if not isinstance(widget, RecordTable):
                        raise ValueError(tr("Unknown property."))
                    value = selected_table_row(widget)
                elif attribute == "table":
                    if not isinstance(widget, RecordTable):
                        raise ValueError(tr("Unknown property."))
                    value = table_contents(widget)
                elif attribute == "record":
                    if isinstance(widget, RecordTable):
                        value = selected_table_record(widget)
                    elif isinstance(widget, QComboBox):
                        value = widget.currentData()
                    else:
                        raise ValueError(tr("Unknown property."))
                elif attribute == "checked":
                    value = widget.isChecked()
                elif attribute == "value":
                    value = (
                        range_value(widget)
                        if isinstance(widget, (QDoubleSpinBox, QSlider))
                        else widget.value()
                    )
                else:
                    raise ValueError(tr("Unknown property."))
                self.session.reply(identifier, value)
            elif method == "set_text":
                if widget is None:
                    raise ValueError(tr("The component does not exist."))
                if isinstance(widget, QDateEdit):
                    if not valid_date(request["value"]):
                        raise ValueError(tr("A date must be written as YYYY-MM-DD."))
                    set_date(widget, request["value"])
                elif isinstance(widget, QComboBox):
                    index = widget.findText(request["value"])
                    if index < 0:
                        raise ValueError(tr("This option is not in the list."))
                    widget.blockSignals(True)
                    widget.setCurrentIndex(index)
                    widget.blockSignals(False)
                elif isinstance(widget, QPlainTextEdit):
                    widget.setPlainText(request["value"])
                else:
                    widget.setText(request["value"])
                self.session.reply(identifier)
            elif method in {"set_rows", "add_row"}:
                if not isinstance(widget, RecordTable):
                    raise ValueError(tr("The component does not exist."))
                if method == "set_rows":
                    set_table_rows(widget, request["value"])
                else:
                    blocked = widget.blockSignals(True)
                    append_table_row(widget, request["value"])
                    widget.blockSignals(blocked)
                self.session.reply(identifier)
            elif method == "set_chart":
                if not isinstance(widget, ChartWidget):
                    raise ValueError(tr("The component does not exist."))
                widget.set_data(request["labels"], request["value"])
                self.session.reply(identifier)
            elif method == "show_records":
                listing = request["value"]
                if isinstance(widget, RecordTable):
                    configure_table(widget, listing["headers"])
                    set_table_rows(widget, listing["rows"], listing["ids"])
                elif isinstance(widget, QComboBox):
                    fill_choice(widget, listing["names"], widget.currentText(), listing["ids"])
                else:
                    raise ValueError(tr("The component does not exist."))
                self.session.reply(identifier)
            elif method == "set_options":
                if not isinstance(widget, QComboBox):
                    raise ValueError(tr("The component does not exist."))
                fill_choice(widget, request["value"], widget.currentText())
                self.session.reply(identifier)
            elif method in {"set_theme", "set_background"}:
                from makebench.core.style import THEMES, valid_color

                view = self.views.get(self.current_window)
                if method == "set_theme":
                    if request["theme"] not in THEMES or (
                        request["accent"] and not valid_color(request["accent"])
                    ):
                        raise ValueError(tr("Use light, dark or system and a #rrggbb accent."))
                    view.change_style(theme=request["theme"], accent=request["accent"])
                else:
                    if request["color"] and not valid_color(request["color"]):
                        raise ValueError(tr("Use a color such as #336699."))
                    view.change_style(background=request["color"])
                self.session.reply(identifier)
            elif method == "set_enabled":
                if widget is None:
                    raise ValueError(tr("The component does not exist."))
                view.set_enabled(component, request["value"])
                self.session.reply(identifier)
            elif method == "set_value":
                if isinstance(widget, (QDoubleSpinBox, QSlider)):
                    if not widget.minimum() <= request["value"] <= widget.maximum():
                        raise ValueError(tr("The value is outside the limits of the component."))
                    set_range_value(widget, request["value"])
                elif widget is None or not 0 <= request["value"] <= 100:
                    raise ValueError(tr("Progress must be between 0 and 100."))
                else:
                    widget.setValue(int(request["value"]))
                self.session.reply(identifier)
            elif method == "show_page":
                if view is None:
                    raise ValueError(tr("This page's window is not open."))
                view.show_page(component)
                self.session.reply(identifier)
            elif method == "go_state":
                self.apply_state(self.current_window, request["state"])
                self.session.reply(identifier)
            elif method == "open_window":
                reset = self.open_app_window(request["window"], request.get("close_current", False))
                self.session.reply(identifier, {"reset": reset})
            elif method == "close_window":
                self.close_app_window(self.current_window)
                self.session.reply(identifier)
            elif method in {"message", "confirm", "ask"}:
                self._dialog(request)
            else:
                raise ValueError(tr("Unknown context operation."))
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            self.session.reply(identifier, ok=False, error=str(exc))

    def _dialog(self, request):
        """Open declared input without blocking the editor's event loop."""
        method = request["method"]
        prompt = str(request.get("prompt", ""))
        kind = request.get("kind")
        parent = self.app_windows.get(self.current_window, self)
        if method in {"message", "confirm"}:
            dialog = QMessageBox(parent)
            dialog.setWindowTitle(tr("Confirmation") if method == "confirm" else self.project.name)
            dialog.setTextFormat(Qt.TextFormat.PlainText)
            dialog.setText(prompt)
            dialog.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                if method == "confirm"
                else QMessageBox.StandardButton.Ok
            )
            if method == "confirm":
                dialog.setDefaultButton(QMessageBox.StandardButton.No)
        elif kind in {"text", "choice"}:
            dialog = QInputDialog(parent)
            dialog.setWindowTitle(self.project.name)
            dialog.setLabelText(prompt)
            dialog.setOkButtonText(tr("Continue"))
            dialog.setCancelButtonText(tr("Cancel"))
            if kind == "choice":
                options = request.get("options", [])
                if (
                    not isinstance(options, list)
                    or not options
                    or any(not isinstance(v, str) for v in options)
                ):
                    raise ValueError(tr("Provide a non-empty list of text options."))
                dialog.setComboBoxItems(options)
                dialog.setComboBoxEditable(False)
        elif kind in {"file", "directory", "save_file"}:
            dialog = QFileDialog(parent, prompt, str(self.session.root))
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dialog.setFileMode(
                QFileDialog.FileMode.Directory
                if kind == "directory"
                else QFileDialog.FileMode.AnyFile
                if kind == "save_file"
                else QFileDialog.FileMode.ExistingFile
            )
            if kind == "save_file":
                dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        else:
            raise ValueError(tr("Unknown dialog type."))
        self.set_status(tr("Waiting for an answer…"))
        from makebench.ui.dialogs import translate_buttons

        translate_buttons(dialog)
        self.dialogs.add(dialog)

        def finished(result):
            """Return input or an explicit cancellation before releasing the dialog."""
            self.dialogs.discard(dialog)
            self._output("status", tr("Question answered or cancelled.") + "\n")
            value = None
            if method == "confirm":
                accepted = result == QMessageBox.StandardButton.Yes
                value = accepted
            elif method == "message":
                accepted = result == QMessageBox.StandardButton.Ok
            else:
                accepted = bool(result)
                if accepted:
                    value = (
                        dialog.selectedFiles()[0]
                        if isinstance(dialog, QFileDialog)
                        else dialog.textValue()
                    )
            self.session.reply(
                request["id"],
                value,
                ok=accepted,
                cancelled=not accepted,
                error=tr("Operation cancelled by the user.") if not accepted else "",
            )
            dialog.deleteLater()

        dialog.finished.connect(finished)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.show()

    def stop(self):
        """Stop the instance and ordinary tasks without touching an administrative task."""
        if not self.session.stop():
            self.set_status(tr("Wait for the administrative task to finish before stopping."))
            return False
        from makebench.terminal.components import stop_components

        for view in self.views.values():
            stop_components(view.widgets)
        self.set_status(tr("Stopping run…"))
        self.stop_button.setEnabled(False)
        for dialog in list(self.dialogs):
            dialog.reject()
        return True

    def _stopped(self):
        """Allow closing only after ordinary processes have ended."""
        for window_id, window in self.app_windows.items():
            if window is not self:
                window.close()
        for view in self.views.values():
            view.set_busy(True)
        self.set_status(tr("Run ended."))
        self.stop_button.setEnabled(False)
        self.shutdown_finished.emit()
        if self.close_pending:
            self.close()

    def closeEvent(self, event):
        """Never abandon processes or close during an active elevated task."""
        if not self.session.closed:
            event.ignore()
            if len(self.open_windows) > 1 and self.root_window_id in self.open_windows:
                self.close_with_event(
                    self.root_window_id, lambda: self.close_app_window(self.root_window_id)
                )
                return

            def finish():
                if self.stop():
                    self.close_pending = True

            self.close_with_event(self.root_window_id, finish)
            return
        if self.temporary:
            self.temporary.cleanup()
        event.accept()
