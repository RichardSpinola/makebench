# SPDX-License-Identifier: GPL-3.0-or-later
"""Distribution with explicit tool preparation and verifiable artifacts."""

from pathlib import Path
import threading
from PySide6.QtCore import QThread, QUrl, Signal, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLayout,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QFrame,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from makebench.core.packages import FORMATS, preflight, build_package
from makebench.core.environment import build_tools
from makebench.core.build_environment import prepare_flatpak
from makebench.core.portable import (
    ready,
    prepare as prepare_portable,
    editor_project,
    build_editor_appimage,
)
from makebench.i18n import tr
from .errors import describe


class BuildJob(QThread):
    """Build the snapshot in staging outside the UI, without running the project."""

    progress = Signal(int, str)
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        project,
        source,
        read_asset,
        destination,
        parent,
        format="source",
        recipe_only=False,
        environment="auto",
        editor=False,
    ):
        """Receive immutable build data and cooperative cancellation."""
        super().__init__(parent)
        self.project = project
        self.source = source
        self.read_asset = read_asset
        self.destination = destination
        self.format = format
        self.recipe_only = recipe_only
        self.environment = environment
        self.editor = editor
        self.cancel = threading.Event()

    def run(self):
        """Publish only a complete result; failures keep the destination intact."""
        try:
            self.completed.emit(
                build_editor_appimage(self.destination, self.progress.emit, self.cancel.is_set)
                if self.editor
                else build_package(
                    self.project,
                    self.source,
                    self.read_asset,
                    self.destination,
                    self.format,
                    self.progress.emit,
                    self.cancel.is_set,
                    self.recipe_only,
                    self.environment,
                )
            )
        except Exception as exc:
            # The first line is shown in the window; the rest goes to the details log.
            summary, details = describe(exc)
            self.failed.emit(summary + ("\n" + details if details else ""))


class PrepareJob(QThread):
    """Download trusted tools without installing RPMs on the user's system."""

    progress = Signal(int, str)
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self, project, format, parent, editor=False):
        """Flatpak prepares the SDK per user; the other formats use rootless Podman."""
        super().__init__(parent)
        self.project = project
        self.format = format
        self.editor = editor
        self.cancel = threading.Event()

    def run(self):
        """Preparation is an explicit action with visible output and cancellation."""
        try:
            self.completed.emit(
                prepare_flatpak(self.project, self.progress.emit, self.cancel.is_set)
                if self.format == "flatpak"
                else prepare_portable(
                    self.project, self.progress.emit, self.cancel.is_set, editor=self.editor
                )
            )
        except Exception as exc:
            # The first line is shown in the window; the rest goes to the details log.
            summary, details = describe(exc)
            self.failed.emit(summary + ("\n" + details if details else ""))


def stage_text(active=None):
    """Export steps, with the active one in brackets (Format → Check → Build → Result)."""
    names = [tr("Format"), tr("Verify"), tr("Build"), tr("Result")]
    return "  →  ".join(
        f"[{number} {name}]" if number == active else f"{number} {name}"
        for number, name in enumerate(names, 1)
    )


class PublishPanel(QWidget):
    """Separate app settings, tools and the real distribution result."""

    def __init__(self, window):
        """Compact native controls and expandable details for logs and diagnostics."""
        super().__init__()
        self.window = window
        self.job = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        self.stages = QLabel(stage_text())
        layout.addWidget(self.stages)
        header = QHBoxLayout()
        self.summary = QLabel()
        header.addWidget(self.summary, 1)
        edit = QPushButton(tr("Application…"))
        self.edit_application_button = edit
        edit.clicked.connect(window.application_settings)
        header.addWidget(edit)
        layout.addLayout(header)
        form = QFormLayout()
        self.destination_form = form
        self.product = QComboBox()
        self.product.addItem(tr("Project application"), False)
        self.product.addItem(tr("Makebench editor (AppImage)"), True)
        form.addRow(tr("Export"), self.product)
        self._product_editor_last = False
        self._product_syncing = False
        self.format = QComboBox()
        for key, (name, _, _) in FORMATS.items():
            self.format.addItem(name, key)
        self.format.setMaximumWidth(360)
        form.addRow(tr("Format"), self.format)
        self.environment = QComboBox()
        for label, key in [
            (tr("Automatic"), "auto"),
            (tr("Tools prepared by Makebench"), "managed"),
            (tr("System tools"), "system"),
        ]:
            self.environment.addItem(label, key)
        self.environment.setMaximumWidth(360)
        form.addRow(tr("Build with"), self.environment)
        layout.addLayout(form)
        tools = QHBoxLayout()
        self.tool_status = QLabel()
        tools.addWidget(self.tool_status, 1)
        self.prepare = QPushButton(tr("Prepare tools…"))
        self.prepare.clicked.connect(self.prepare_environment)
        tools.addWidget(self.prepare)
        layout.addLayout(tools)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setMaximumWidth(880)
        layout.addWidget(self.description)
        self.recipe_only = QCheckBox(tr("Export only the recipe"))
        self.recipe_only.setToolTip(
            tr("Generates a ZIP with the build files. Does not produce an installable package.")
        )
        layout.addWidget(self.recipe_only)
        self.check_hint = QLabel(tr("Check the project before building."))
        layout.addWidget(self.check_hint)
        self.checks = QListWidget()
        self.checks.setFrameShape(QFrame.Shape.NoFrame)
        self.checks.setMinimumHeight(60)
        self.checks.setMaximumHeight(160)
        self.checks.hide()
        self.checks.itemActivated.connect(self.fix_issue)
        layout.addWidget(self.checks)
        row = QHBoxLayout()
        self.check_button = QPushButton(tr("Check"))
        self.check_button.clicked.connect(self.check)
        row.addWidget(self.check_button)
        self.build = QPushButton(tr("Build…"))
        self.build.clicked.connect(self.build_source)
        row.addWidget(self.build)
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_build)
        self.cancel_button.hide()
        row.addWidget(self.cancel_button)
        row.addStretch()
        layout.addLayout(row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.progress_bar.hide()
        self.log_toggle = QCheckBox(tr("Show details"))
        layout.addWidget(self.log_toggle)
        self.build_log = QPlainTextEdit()
        self.build_log.setReadOnly(True)
        self.build_log.setMaximumBlockCount(2000)
        self.build_log.setMinimumHeight(110)
        layout.addWidget(self.build_log, 1)
        self.build_log.hide()
        self.log_toggle.toggled.connect(self.build_log.setVisible)
        self.result = QLabel()
        self.result.setWordWrap(True)
        self.result.setTextFormat(Qt.TextFormat.PlainText)
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result)
        result_row = QHBoxLayout()
        self.open_folder = QPushButton(tr("Open folder"))
        self.open_folder.hide()
        self.open_folder.clicked.connect(self.show_result_folder)
        result_row.addWidget(self.open_folder)
        self.copy_path = QPushButton(tr("Copy path"))
        self.copy_path.hide()
        self.copy_path.clicked.connect(
            lambda: QApplication.clipboard().setText(str(self.output_path))
        )
        result_row.addWidget(self.copy_path)
        result_row.addStretch()
        layout.addLayout(result_row)
        layout.addStretch()
        self.product.currentIndexChanged.connect(self.sync)
        self.format.currentIndexChanged.connect(self.sync)
        self.environment.currentIndexChanged.connect(self.sync)
        self.recipe_only.toggled.connect(self.sync)
        self.sync()

    def change(self, key, value):
        """Metadata stays a reversible command of the application settings."""
        self.window.change_application(key, value)

    def sync(self):
        """Missing tools never silently swap a package for a recipe."""
        if self._product_syncing:
            return
        is_editor = bool(self.product.currentData())
        if is_editor != self._product_editor_last:
            self._product_syncing = True
            if is_editor:
                self._project_format = self.format.currentData()
                self.format.setCurrentIndex(self.format.findData("appimage"))
            else:
                self.format.setCurrentIndex(
                    self.format.findData(getattr(self, "_project_format", "source"))
                )
            for index in range(self.format.count()):
                self.format.model().item(index).setEnabled(
                    not is_editor or self.format.itemData(index) == "appimage"
                )
            self._product_editor_last = is_editor
            self._product_syncing = False
        selected = editor_project() if is_editor else self.window.project
        self.edit_application_button.setVisible(not is_editor)
        app = selected.application
        self.summary.setText(
            (app.get("name") or self.window.project.name)
            + " · "
            + (app.get("version") or tr("No version"))
            + " · "
            + app.get("backend", "qt").upper()
        )
        from makebench.core.source import source_signature

        key = self.format.currentData()
        signature = (
            self.window.project.id,
            self.window.history._index,
            source_signature(self.window.source.text),
            key,
            self.recipe_only.isChecked(),
            self.environment.currentData(),
            is_editor,
        )
        if signature != getattr(self, "_check_signature", None):
            self._check_signature = signature
            self.checks.clear()
            self.checks.hide()
            self.check_hint.show()
            self.stages.setText(stage_text())
            self.result.clear()
            self.open_folder.hide()
            self.copy_path.hide()
        name, tool, _ = FORMATS[key]
        available = build_tools().get(tool) if tool else True
        managed = ready(selected, is_editor)
        busy = bool(self.job and self.job.isRunning())
        self.destination_form.setRowVisible(self.environment, False)
        self.prepare.setVisible(key != "source")
        self.recipe_only.setVisible(key != "source" and not is_editor)
        self.environment.setEnabled(key not in {"source", "flatpak"} and not busy)
        self.recipe_only.setEnabled(key != "source" and not busy)
        self.prepare.setEnabled(key != "source" and not busy)
        if key == "source":
            status = tr("Needs no build tools.")
            text = tr(
                "Python code, assets and runtime. The dependencies are listed in requirements.txt."
            )
        elif key == "flatpak":
            status = tr("{desktop} SDK · per-user preparation").format(
                desktop="GNOME" if app.get("backend") == "gtk" else "KDE"
            )
            text = tr(
                "Prepare installs the SDK from Flathub. The build uses the local SDK and produces a .flatpak bundle. The terminal and tasks stay in the sandbox, with no host access or administrative elevation."
            )
        else:
            status = (
                tr("Makebench tools ready.")
                if managed
                else tr("System tool available.")
                if available
                else tr("Prepare the tools to build.")
            )
            text = tr(
                "Prepare resolves Python 3.12, the backend and dependencies in a separate Podman container. Building uses only the verified cache, with no network."
            )
        if key == "appimage":
            text += " " + tr(
                "Includes Python and libraries. Targets: Ubuntu 24.04 and Fedora 44 x86_64; requires glibc 2.39+, X11/Wayland and the system drivers."
            )
        if key == "deb":
            text += " " + tr("DEB for Ubuntu 24.04 x86_64 with the runtime included.")
        if key == "rpm":
            text += " " + tr("RPM for Fedora 44 x86_64 with the runtime included.")
        if is_editor:
            text += " " + tr(
                "Includes the editor, QtWebEngine and the resources to create and test Qt and GTK applications."
            )
        self.tool_status.setText(status)
        self.description.setText(text)
        self.build.setText(
            tr("Export source…")
            if key == "source"
            else tr("Export recipe…")
            if self.recipe_only.isChecked() and not is_editor
            else tr("Build {name}…").format(name=name)
        )

    def check(self):
        """Check the project without running code and allow opening each problem's origin."""
        if not self.product.currentData() and not self.window._finish_field_edit():
            return False
        self.stages.setText(stage_text(2))
        self.checks.clear()
        self.checks.show()
        self.check_hint.hide()
        issues = (
            [
                {
                    "level": "success" if ready(editor_project(), True) else "warning",
                    "message": tr("Editor runtime ready.")
                    if ready(editor_project(), True)
                    else tr("Prepare the editor's complete runtime before building."),
                    "field": "destinations",
                }
            ]
            if self.product.currentData()
            else preflight(
                self.window.project,
                self.window.source.text,
                self.window.assets.read,
                self.format.currentData(),
            )
        )
        for issue in issues:
            prefix = {"error": "✕", "warning": "!", "success": "✓"}[issue["level"]]
            item = QListWidgetItem(prefix + "  " + issue["message"])
            item.setData(Qt.ItemDataRole.UserRole, issue["field"])
            self.checks.addItem(item)
        row_height = self.checks.sizeHintForRow(0) if self.checks.count() else 24
        self.checks.setFixedHeight(min(160, max(32, row_height * self.checks.count() + 8)))
        return not any(issue["level"] == "error" for issue in issues)

    def fix_issue(self, item):
        """Lead to the setting or interface that needs fixing."""
        field = item.data(Qt.ItemDataRole.UserRole)
        if field == "windows" and self.window.project.metadata.get("empty_map"):
            self.window.set_mode("map")
        elif field == "python":
            self.window.set_mode("code")
            self.window.code_files.setCurrentIndex(1)
        elif field == "logic":
            self.window.set_mode("logic")
            self.window.drawer.show()
            self.window.drawer.setCurrentIndex(1)
        elif field:
            self.window.application_settings(field)

    def start_job(self, job, prepare=False):
        """One operation at a time, with consistent controls and cancellation."""
        self.stages.setText(tr("Preparing the tools") if prepare else stage_text(3))
        self.job = job
        self.build.setEnabled(False)
        self.prepare.setEnabled(False)
        self.check_button.setEnabled(False)
        self.format.setEnabled(False)
        self.product.setEnabled(False)
        self.environment.setEnabled(False)
        self.recipe_only.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.result.clear()
        self.open_folder.hide()
        self.copy_path.hide()
        self.build_log.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.result.setText(tr("Preparing tools…") if prepare else tr("Building…"))
        job.progress.connect(
            lambda number, text: (
                self.progress_bar.setValue(number),
                self.build_log.appendPlainText(text),
            )
        )
        job.completed.connect(self.prepared if prepare else self.completed)
        job.failed.connect(self.failed)
        job.finished.connect(self.build_finished)
        job.start()

    def prepare_environment(self):
        """Explicit preparation may download tools and an SDK, never touching the project."""
        if self.job and self.job.isRunning():
            return
        from makebench.core.project import Project

        selected = (
            editor_project()
            if self.product.currentData()
            else Project.from_dict(self.window.project.to_dict())
        )
        self.start_job(
            PrepareJob(
                selected, self.format.currentData(), self, editor=bool(self.product.currentData())
            ),
            True,
        )

    def build_source(self):
        """Build exactly the chosen format from a snapshot of the document."""
        if self.job and self.job.isRunning():
            return
        if not self.check():
            return
        key = self.format.currentData()
        _, tool, suffix = FORMATS[key]
        recipe = key != "source" and not self.product.currentData() and self.recipe_only.isChecked()
        environment = self.environment.currentData()
        if key not in {"source", "flatpak"} and not recipe:
            if not ready(
                editor_project() if self.product.currentData() else self.window.project,
                bool(self.product.currentData()),
            ):
                self.failed(tr("Click Prepare tools before building."))
                return
        suffix = "-recipe.zip" if recipe else suffix
        filename, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export {format}").format(format=FORMATS[key][0]),
            ("Makebench-editor" if self.product.currentData() else self.window.project.name)
            + suffix,
            tr("Files (*{suffix})").format(suffix=suffix),
        )
        if not filename:
            return
        from makebench.core.project import Project

        project = (
            editor_project()
            if self.product.currentData()
            else Project.from_dict(self.window.project.to_dict())
        )
        assets = (
            {}
            if self.product.currentData()
            else {name: self.window.assets.read(name) for name in project.asset_paths()}
        )
        self.start_job(
            BuildJob(
                project,
                self.window.source.text,
                assets.__getitem__,
                filename,
                self,
                key,
                recipe,
                environment,
                editor=bool(self.product.currentData()),
            )
        )

    def cancel_build(self):
        """Wait for interruption and cleanup, without publishing a partial result."""
        if self.job:
            self.job.cancel.set()
            self.cancel_button.setEnabled(False)
            self.result.setText(tr("Cancelling…"))

    def prepared(self, result):
        """Confirm only the environment; no package was built in this step."""
        self.result.setText(result["status"])
        self.progress_bar.setValue(100)

    def completed(self, result):
        """The result shows format, size and folder; the hash stays in the details."""
        self.stages.setText(stage_text(4))
        self.output_path = Path(result["path"])
        self.result.setText(
            f"{result.get('status', tr('Exported'))}\n{self.output_path.name} · {result['size'] / 1048576:.1f} MB"
            if result["size"] >= 1048576
            else f"{result.get('status', tr('Exported'))}\n{self.output_path.name} · {result['size'] / 1024:.0f} KB"
        )
        self.result.setToolTip(str(self.output_path))
        self.build_log.appendPlainText(str(self.output_path) + "\nSHA-256: " + result["sha256"])
        self.progress_bar.setValue(100)
        self.open_folder.show()
        self.copy_path.show()

    def failed(self, message):
        """Keep the cause available next to the tool's output."""
        self.stages.setText(tr("Operation interrupted · see the diagnostics"))
        self.result.setText(
            message.splitlines()[0] if message else tr("The operation did not finish.")
        )
        self.build_log.appendPlainText(message)
        self.log_toggle.setChecked(True)

    def build_finished(self):
        """Release the controls only after the thread's output and cleanup."""
        self.build.setEnabled(True)
        self.check_button.setEnabled(True)
        self.format.setEnabled(True)
        self.product.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.sync()

    def show_result_folder(self):
        """Open the folder, without running the exported package."""
        if hasattr(self, "output_path"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_path.parent)))


class ExportDialog(QDialog):
    """Export in a compact window; closing keeps a build in progress."""

    def __init__(self, window):
        """The window grows with checks and details, without taking over the main workbench."""
        super().__init__(window)
        self.setWindowTitle(tr("Export application"))
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.panel = PublishPanel(window)
        self.panel.setFixedWidth(
            min(680, max(460, window.screen().availableGeometry().width() - 60))
        )
        layout.addWidget(self.panel)
        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.hide)
        row.addWidget(close)
        layout.addLayout(row)
