# SPDX-License-Identifier: GPL-3.0-or-later
"""Local image library with usage, replacement and preservation for undo."""

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFileDialog, QInputDialog, QListWidgetItem, QMessageBox
from makebench.core.project import ProjectError
from makebench.i18n import ntr, tr


class ResourceMixin:
    """Operate only on the document's local assets; never imports project code."""

    def resource_usage(self, path):
        """Count references from the composition, states and the application icon."""
        count = sum(1 for node in self.project.walk() if node.properties.get("source") == path)
        count += sum(
            1
            for states in self.project.states.values()
            for state in states
            for values in state.get("overrides", {}).values()
            if values.get("source") == path
        )
        count += int(self.project.application.get("icon") == path)
        return count

    def list_resources(self):
        """List referenced and orphaned assets, with thumbnails and usage counts."""
        paths = self.project.asset_paths() | set(self.assets._cache)
        if self.assets.root:
            folder = self.assets.root / "assets"
            if folder.is_dir():
                for number, path in enumerate(folder.rglob("*")):
                    if number > 2000:
                        break
                    if path.is_file():
                        paths.add(path.relative_to(self.assets.root).as_posix())
        paths -= getattr(self.assets, "removed", set()) - self.project.asset_paths()
        for path in sorted(paths):
            uses = self.resource_usage(path)
            name = (
                next(
                    (
                        node.properties.get("image_name")
                        for node in self.project.walk()
                        if node.properties.get("source") == path
                        and node.properties.get("image_name")
                    ),
                    None,
                )
                or Path(path).name
            )
            item = QListWidgetItem(
                tr("Image · {name}").format(name=name)
                + "\n"
                + ntr("Used in {count} place", "Used in {count} places", uses).format(count=uses)
            )
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, {"kind": "resource", "path": path})
            try:
                image = QPixmap()
                image.loadFromData(self.assets.read(path))
                if not image.isNull():
                    item.setIcon(QIcon(image))
            except (OSError, ProjectError):
                item.setText(tr("Missing asset · {name}").format(name=name))
            self.data_list.addItem(item)

    def edit_resource(self, path):
        """Offer replacing, or removing only when there is no current use."""
        replace_label, remove_label = tr("Replace everywhere"), tr("Remove unused asset")
        actions = [replace_label]
        if self.resource_usage(path) == 0:
            actions.append(remove_label)
        choice, ok = QInputDialog.getItem(
            self, tr("Project asset"), Path(path).name, actions, 0, False
        )
        if not ok:
            return
        if choice == remove_label:
            self.remove_resource(path)
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, tr("Replace image"), "", tr("Images (*.png *.jpg *.jpeg *.webp *.svg)")
        )
        if not filename:
            return
        try:
            new_path = self.assets.import_image(Path(filename))
        except (OSError, ProjectError) as exc:
            self._show_error(exc, tr("Could not replace the image"))
            return

        def replace():
            """Update references to the asset without deleting the original file."""
            for node in self.project.walk():
                if node.properties.get("source") == path:
                    node.properties.update(source=new_path, image_name=Path(filename).name)
            for states in self.project.states.values():
                for state in states:
                    for values in state.get("overrides", {}).values():
                        if values.get("source") == path:
                            values.update(source=new_path, image_name=Path(filename).name)
            app = self.project.application
            if app.get("icon") == path:
                app["icon"] = new_path

        self._edit(replace)

    def remove_resource(self, path):
        """Remove an orphan; the cache keeps bytes needed by the session history."""
        if self.resource_usage(path):
            self.statusBar().showMessage(tr("This asset is still used by the application."), 6000)
            return
        try:
            self.assets.read(path)
            if self.assets.root:
                file = self.assets._inside(self.assets.root, path)
                if file.exists():
                    file.unlink()
            if not hasattr(self.assets, "removed"):
                self.assets.removed = set()
            self.assets.removed.add(path)
            self._data_signature = None
            self.sync_studio()
        except (OSError, ProjectError) as exc:
            self._show_error(exc, tr("Could not remove the asset"))
