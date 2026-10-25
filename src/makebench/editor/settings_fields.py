# SPDX-License-Identifier: GPL-3.0-or-later
"""Native controls for dependencies and icons, never installing or importing packages."""

import importlib.metadata
import re
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QInputDialog,
    QLabel,
)
from makebench.i18n import tr


class Dependencies(QWidget):
    """List declared requirements and the versions available in the editor's Python."""

    changed = Signal(list)

    def __init__(self, packages, parent=None):
        """The diagnostic reads metadata; importing a package's module is forbidden here."""
        super().__init__(parent)
        self.packages = list(packages)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.items = QListWidget()
        self.items.setAccessibleName(tr("Application Python requirements"))
        self.items.setMaximumHeight(210)
        self.items.itemActivated.connect(lambda _: self.edit())
        layout.addWidget(self.items)
        row = QHBoxLayout()
        for label, callback in [
            (tr("Add…"), lambda: self.edit(new=True)),
            (tr("Edit…"), self.edit),
            (tr("Remove"), self.remove),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        hint = QLabel(
            tr("Availability in this Python. The Flatpak build uses its own SDK and cache.")
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.refresh()

    def refresh(self):
        """Update only the requirement list, keeping the original declaration."""
        self.items.clear()
        for package in self.packages:
            name = re.split(r"[\[<>=!~]", package, 1)[0]
            try:
                status = tr("installed: {version}").format(version=importlib.metadata.version(name))
            except importlib.metadata.PackageNotFoundError:
                status = tr("missing in this Python")
            self.items.addItem(package + " · " + status)

    def edit(self, _checked=False, new=False):
        """Validate a requirement without sending it to the shell or the package manager."""
        index = self.items.currentRow()
        if index < 0 and not new:
            return
        text, ok = QInputDialog.getText(
            self,
            tr("Python dependency"),
            tr("Requirement, for example requests>=2.32"),
            text="" if new else self.packages[index],
        )
        if not ok or not text.strip():
            return
        text = text.strip()
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:[<>=!~]=?[A-Za-z0-9.*+!_-]+(?:,[<>=!~]=?[A-Za-z0-9.*+!_-]+)*)?",
            text,
        ):
            self.notice.setText(
                tr("Invalid requirement. Use a name and version, for example requests>=2.32.")
            )
            return
        self.notice.clear()
        if new:
            self.packages.append(text)
        else:
            self.packages[index] = text
        self.changed.emit(list(self.packages))
        self.refresh()

    def remove(self):
        """Remove the selected declaration, never uninstalling anything from the computer."""
        index = self.items.currentRow()
        if index >= 0:
            self.packages.pop(index)
            self.changed.emit(list(self.packages))
            self.refresh()
