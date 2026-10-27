# SPDX-License-Identifier: GPL-3.0-or-later
"""Download from Git: address, folder and progress, then the project opens."""

import threading
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from makebench.core import vcs
from makebench.i18n import tr

from .look import make_muted
from .settings import preference


def find_project(folder: Path) -> Path | None:
    """The project file at the top of the folder, or one level down."""
    for pattern in ("*.makebench.json", "*/*.makebench.json"):
        found = sorted(folder.glob(pattern))
        if found:
            return found[0]
    return None


class CloneDialog(QDialog):
    """Ask for the address and the folder; git runs in the background."""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Download from Git"))
        self.setMinimumWidth(520)
        self.project_path = None
        self._thread = None
        self._result = None
        self._named = False
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://github.com/you/app.git")
        self.url.setAccessibleName(tr("Repository address"))
        self.url.textChanged.connect(self._suggest_name)
        form.addRow(tr("Address"), self.url)
        folder_row = QHBoxLayout()
        self.folder = QLineEdit(preference("projects/folder", settings))
        self.folder.setAccessibleName(tr("Download into"))
        browse = QPushButton(tr("Choose…"))
        browse.clicked.connect(self._choose_folder)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        form.addRow(tr("Into"), folder_row)
        self.name = QLineEdit()
        self.name.setAccessibleName(tr("Folder name"))
        self.name.textEdited.connect(lambda _text: setattr(self, "_named", True))
        form.addRow(tr("Folder name"), self.name)
        layout.addLayout(form)
        layout.addWidget(
            make_muted(QLabel(tr("Nothing in the project runs until you open it and press F5.")))
        )
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.download_button = self.buttons.addButton(
            tr("Download"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.download_button.setDefault(True)
        self.buttons.accepted.connect(self.start)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.poll = QTimer(self)
        self.poll.setInterval(100)
        self.poll.timeout.connect(self._check)

    def _suggest_name(self, text):
        if not self._named:
            self.name.setText(vcs.repo_name(text))

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Download into"), self.folder.text())
        if folder:
            self.folder.setText(folder)

    def busy(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        """Clone in a thread so the window keeps drawing while git works."""
        if self.busy():
            return
        if not vcs.available():
            self.status.setText(tr("Git is not installed on this computer."))
            return
        url, parent, name = self.url.text(), self.folder.text().strip(), self.name.text()
        if not parent:
            self.status.setText(tr("Choose the folder to download into."))
            return
        self._result = None

        def work():
            try:
                self._result = ("ok", vcs.clone(url, Path(parent).expanduser(), name or None))
            except (vcs.VcsError, OSError) as exc:
                self._result = ("error", str(exc))

        self._set_busy(True)
        self.status.setText(tr("Downloading…"))
        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        self.poll.start()

    def _set_busy(self, busy):
        for widget in (self.url, self.folder, self.name, self.download_button):
            widget.setEnabled(not busy)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(not busy)
        self.progress.setVisible(busy)

    def _check(self):
        if self.busy():
            return
        self.poll.stop()
        self._set_busy(False)
        kind, value = self._result or ("error", tr("The download stopped."))
        if kind == "error":
            self.status.setText(value)
            return
        project = find_project(value)
        if project is None:
            self.status.setText(
                tr("Downloaded to {folder}, but there is no Makebench project in it.").format(
                    folder=value
                )
            )
            return
        self.project_path = project
        self.accept()

    def reject(self):
        """Closing waits for git: a half-finished folder is never left behind."""
        if self.busy():
            return
        super().reject()
