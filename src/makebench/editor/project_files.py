# SPDX-License-Identifier: GPL-3.0-or-later
"""New, open, save and discard of the project file."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
)

from makebench.core.history import History
from makebench.core.project import (
    Project,
    ProjectError,
)
from makebench.core.source import SourceBuffer
from makebench.core.storage import load_project, save_workspace
from makebench.editor.assets import AssetStore
from makebench.i18n import tr


class ProjectFilesMixin:
    """New, open, save and discard of the project file. Mixed into MainWindow."""

    def new_project(self) -> None:
        """Create a document after resolving unsaved changes."""
        if not self._confirm_discard():
            return
        self._replace_project(Project.empty(), None)

    def open_project(self) -> None:
        """Open a validated document; failures never replace the current project."""
        if not self._confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self.project_dialog_parent(),
            tr("Open Makebench project"),
            str(self.path.parent) if self.path else "",
            tr("Makebench projects (*.makebench.json *.zip);;JSON (*.json)"),
        )
        if not filename:
            return
        if filename.lower().endswith(".zip"):
            destination = QFileDialog.getExistingDirectory(
                self.project_dialog_parent(), tr("Extract into an empty folder"), ""
            )
            if not destination:
                return
            from makebench.core.bundle import read_bundle

            try:
                filename = str(read_bundle(filename, Path(destination)))
            except (ProjectError, OSError) as exc:
                self._show_error(exc, tr("Could not open the project"))
                return
        try:
            project = load_project(filename)
        except ProjectError as exc:
            self._show_error(exc, tr("Could not open the project"))
            return
        try:
            self._replace_project(project, Path(filename))
        except (ProjectError, OSError) as exc:
            self._show_error(exc, tr("Could not open the project"))

    def _replace_project(self, project: Project, path: Path | None) -> None:
        """Swap the document and start an independent history."""
        path = path.resolve() if path else None
        source = SourceBuffer.load(path)
        if path and project.programming is None:
            from makebench.core.project import infer_programming

            choice = infer_programming(project, source.text)
            if choice:
                project.metadata["programming"] = choice
        self._trusted_session = False
        self._created_here = False
        self.project = project
        self.path = path
        self.source = source
        self.source_editor.blockSignals(True)
        self.source_editor.setPlainText(source.text)
        self.source_editor.blockSignals(False)
        self._script_target = None
        self._script_original = ""
        self.script_editor.clear()
        self.script_apply.setEnabled(False)
        self.logic.flow_id = None
        self.logic._target_component = None
        self.assets = AssetStore(path.parent if path else None)
        self.history = History(project)
        self._saved_document = project.to_dict() if path else None
        self.selected_id = project.root.id
        self._refresh()
        self.remember_project()
        self.pages.setCurrentWidget(self.editor_page)

    def save(self) -> bool:
        """Save the project or ask for a destination when it has no path yet."""
        if not self._finish_field_edit():
            return False
        if self.path is None:
            return self.save_as()
        return self.save_to(self.path)

    def save_as(self) -> bool:
        """Ask for a destination, keeping the current path on failure."""
        return self.save_as_dialog()

    def save_to(self, path: Path) -> bool:
        """Persist the document and mark it as saved only after success."""
        if not self._finish_field_edit():
            return False
        path = path.resolve()
        if hasattr(self, "tidy_code_files"):
            self.tidy_code_files()
        try:
            saved = self._saved_document if path == self.path else None
            self._saved_document, backup = save_workspace(
                self.project, self.source, self.assets, path, saved
            )
        except (ProjectError, OSError) as exc:
            self._show_error(exc, tr("Could not save the project"))
            return False
        self.path = path
        self.history.mark_saved()
        self._update_code()
        self._update_actions()
        self.remember_project()
        self.canvas.close_native_preview()
        self.clear_recovery()
        from .history_panel import record_version

        record_version(self)
        if backup:
            self.statusBar().showMessage(
                tr(
                    "Project upgraded to format {version}. The copy {backup} keeps the previous version; older editors cannot open the new features."
                ).format(version=self.project.to_dict()["format_version"], backup=backup.name),
                12000,
            )
        return True

    def _confirm_discard(self) -> bool:
        """Offer to save changes before closing, opening or creating a project."""
        if not self._finish_field_edit():
            choice = QMessageBox.warning(
                self,
                tr("Unconfirmed blocks"),
                tr(
                    "There are logic changes not confirmed yet. Discarding may lose blocks or the script being edited. Discard and continue?"
                ),
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Discard:
                self.clear_recovery()
                return True
            return False
        if not self.history.dirty and not self.source.dirty:
            return True
        choice = QMessageBox.warning(
            self,
            tr("Save changes?"),
            tr("The project has changes that have not been saved yet."),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        if choice == QMessageBox.StandardButton.Discard:
            self.clear_recovery()
            return True
        return False
