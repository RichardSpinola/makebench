# SPDX-License-Identifier: GPL-3.0-or-later
"""Design editing: properties, components, geometry and images."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
)

from makebench.core.project import (
    RANGE_KINDS,
    Component,
    ComponentKind,
    LayoutKind,
    Project,
    ProjectError,
    clamp_range,
)
from makebench.i18n import ntr, tr


def undo_labels():
    """Names shown by Undo/Redo, keyed by the editor command that made the change."""
    return {
        "edit_resource": tr("Replace image"),
        "mouseReleaseEvent": tr("Move in the map"),
        "contextMenuEvent": tr("Create interface"),
        "new_window_dialog": tr("Create interface"),
        "new_state_dialog": tr("Create state"),
        "make_entry_window": tr("Set start window"),
        "make_initial_state": tr("Set initial state"),
        "rename_state_dialog": tr("Rename state"),
        "restore_default_properties": tr("Restore from Default"),
        "remove_state": tr("Remove state"),
        "remove_window": tr("Remove window"),
        "duplicate_interface": tr("Duplicate interface"),
        "set_initial": tr("Set as initial"),
        "connect_nodes": tr("Connect interfaces"),
        "edit_edge": tr("Edit transition"),
        "remove_edge": tr("Remove transition"),
        "organize": tr("Arrange map"),
        "selection_command": tr("Align selection"),
        "restore_state_property": tr("Restore property"),
        "import_image_drop": tr("Insert image"),
        "add_component": tr("Add component"),
        "_on_drop": tr("Drop component"),
        "_commit_geometry": tr("Move or resize"),
        "duplicate_component": tr("Duplicate"),
        "reorder_component": tr("Reorder"),
        "add_page": tr("Add page"),
        "choose_image": tr("Choose image"),
        "clear_image": tr("Remove image"),
        "remove_component": tr("Remove component"),
        "remove_flow": tr("Remove flow"),
        "change_flow_filter": tr("Change state filter"),
        "variable_dialog": tr("Edit variable"),
        "remove_variable": tr("Remove variable"),
        "duplicate_flow_dialog": tr("Duplicate flow"),
        "insert_behavior": tr("Insert behavior"),
        "_toggle_breakpoint": tr("Toggle breakpoint"),
        "choose_window_icon": tr("Choose window icon"),
    }


class DesignEditMixin:
    """Design editing: properties, components, geometry and images. Mixed into MainWindow."""

    def _change_property(self, component_id: str, key: str, value: object) -> None:
        """Apply a valid property and record a single history change."""
        if self._refreshing:
            return
        before = self.project.to_dict()
        if component_id != "@project" and getattr(self, "active_state", "@default") != "@default":
            from makebench.core.navigation import OVERRIDES

            if key not in OVERRIDES:
                self.statusBar().showMessage(
                    tr("Edit structure and layout in the Default state."), 6000
                )
                self._refresh()
                return
            state = next(
                item
                for item in self.project.states[self.active_window]
                if item["id"] == self.active_state
            )
            state.setdefault("overrides", {}).setdefault(component_id, {})[key] = value
            try:
                Project.from_dict(self.project.to_dict())
            except ProjectError as exc:
                self.project = Project.from_dict(before)
                self._refresh()
                self.statusBar().showMessage(str(exc), 7000)
                return
            self.history.push(self.project, tr("Change property"))
            self._refresh_property(component_id, key)
            return
        if component_id == "@project":
            cleaned = str(value).strip()
            if not cleaned:
                field = self.inspector.findChild(
                    __import__("PySide6.QtWidgets", fromlist=["QLineEdit"]).QLineEdit,
                    "property_name",
                )
                if field:
                    field.setText(self.project.name)
                    field.setModified(False)
                self.statusBar().showMessage(tr("The project name cannot be empty."), 5000)
                return
            if self.project.name == cleaned:
                return
            self.project.name = cleaned
        else:
            node = self.project.find(component_id)
            if node is None:
                return
            if key == "layout":
                if node.layout == LayoutKind(value):
                    return
                try:
                    self.convert_layout(node, value)
                except ProjectError as exc:
                    self._show_error(exc, tr("Could not change the property"))
                    self._refresh()
                    return
            elif key == "alignment_preset":
                if node.properties.get(key) == value:
                    return
                vertical, horizontal = str(value).split("-")
                horizontal = {"left": "start", "center": "center", "right": "end"}[horizontal]
                vertical = {"top": "start", "center": "center", "bottom": "end"}[vertical]
                node.properties.update(
                    alignment_preset=value,
                    align=horizontal if node.layout == LayoutKind.VERTICAL else vertical,
                    distribute=vertical if node.layout == LayoutKind.VERTICAL else horizontal,
                )
            elif key.startswith("geometry."):
                name = key.partition(".")[2]
                if node.geometry[name] == value:
                    return
                node.geometry[name] = int(value)
            else:
                if node.properties.get(key) == value:
                    return
                node.properties[key] = value
                if node.kind in RANGE_KINDS:
                    clamp_range(node)
                if node.kind == ComponentKind.CHOICE and node.properties.get("text") not in {
                    "",
                    *node.properties.get("options", []),
                }:
                    node.properties["text"] = ""
        try:
            Project.from_dict(self.project.to_dict())
        except ProjectError as exc:
            self.project = Project.from_dict(before)
            self._refresh()
            self.statusBar().showMessage(str(exc), 7000)
            return
        self.history.push(self.project, tr("Change property"))
        self._refresh_property(component_id, key)

    def _refresh_property(self, identifier, key, finish=True):
        """Update values without destroying the field being edited or the widget tree."""
        structural = {
            "layout",
            "size_mode",
            "align",
            "distribute",
            "alignment_preset",
            "initial_page",
        }
        if (
            key in structural
            or (
                key in {"value", "minimum", "maximum", "step", "decimals"}
                and self.project.find(identifier).kind in RANGE_KINDS
            )
            or (
                key in {"options", "text"}
                and self.project.find(identifier).kind == ComponentKind.CHOICE
            )
            or key == "menus"
            or (key == "headers" and self.project.find(identifier).kind == ComponentKind.TABLE)
            or key in {"width", "height", "resizable", "frame", "theme", "accent", "background"}
            or key == "icon"
            and self.project.find(identifier).kind == ComponentKind.WINDOW
        ):
            self.setUpdatesEnabled(False)
            try:
                self._refresh()
            finally:
                self.setUpdatesEnabled(True)
            return
        if identifier == "@project":
            self.canvas._project.name = self.project.name
            self._presentation_signature = self.presentation_signature()
            self._update_actions()
            return
        node = self.project.find(identifier)
        if node is None:
            return
        effective = next(
            (
                n
                for n in self.project.effective_root(self.active_window, self.active_state).walk()
                if n.id == identifier
            ),
            None,
        )
        shown = self.canvas._project.find(identifier)
        if effective is None or shown is None:
            return
        shown.properties = deepcopy(effective.properties)
        shown.geometry = dict(effective.geometry)
        self.canvas.refresh_native_preview()
        frame = self.canvas._frames.get(identifier)
        widget = (
            frame.layout().itemAt(0).widget()
            if frame and frame.layout() and frame.layout().count()
            else None
        )
        if widget and not node.can_have_children:
            if key == "text":
                widget.setPlainText(str(effective.properties.get("text", ""))) if hasattr(
                    widget, "setPlainText"
                ) else widget.setText(str(effective.properties.get("text", "")))
            elif key == "placeholder" and hasattr(widget, "setPlaceholderText"):
                widget.setPlaceholderText(str(effective.properties.get("placeholder", "")))
            elif key == "tooltip":
                widget.setToolTip(effective.properties.get("tooltip", ""))
            elif key == "icon" and hasattr(widget, "setIcon"):
                from PySide6.QtGui import QIcon, QPixmap

                image = QPixmap()
                if effective.properties.get("icon"):
                    image.loadFromData(self.assets.read(effective.properties["icon"]))
                widget.setIcon(QIcon(image))
            elif key == "checked" and hasattr(widget, "setChecked"):
                widget.setChecked(effective.properties["checked"])
            elif key == "value" and hasattr(widget, "setValue"):
                widget.setValue(effective.properties["value"])
            elif key in {"source", "alt_text", "image_name"} and hasattr(widget, "image"):
                from PySide6.QtGui import QPixmap

                image = QPixmap()
                if effective.properties.get("source"):
                    image.loadFromData(self.assets.read(effective.properties["source"]))
                widget.image = image
                widget.setAccessibleName(effective.properties.get("alt_text", tr("Image")))
                widget.update()
        if frame:
            if key == "visible":
                frame.setVisible(effective.properties.get("visible", True))
            if key == "enabled":
                target = frame if node.can_have_children else widget
                if target:
                    target.setEnabled(effective.properties.get("enabled", True))
            if key == "spacing" and frame.layout():
                frame.layout().setSpacing(effective.properties.get("spacing", 6))
            if key == "padding" and frame.layout():
                value = effective.properties.get("padding", 8)
                frame.layout().setContentsMargins(value, value, value, value)
            if key.startswith("geometry."):
                parent = self.project.parent_of(identifier)
                if parent and parent.layout == LayoutKind.FREE:
                    frame.setGeometry(
                        *(effective.geometry[k] for k in ("x", "y", "width", "height"))
                    )
                else:
                    axis = key.partition(".")[2]
                    if axis in {"width", "height"}:
                        getattr(frame, "setFixed" + axis.title())(effective.geometry[axis])
        if key == "title" and node.kind == ComponentKind.WINDOW:
            for label in self.canvas.findChildren(QLabel):
                if (
                    label.property("componentId") == identifier
                    and label.parentWidget().objectName() == "app_window_titlebar"
                ):
                    label.setText(str(effective.properties.get("title", tr("Interface"))))
        item = self._tree_items.get(identifier)
        if item:
            count = sum(
                f.get("event", {}).get("component") == identifier
                for f in self.project.editable_flows
            )
            item.setText(
                0,
                ("◌ " if not node.properties.get("visible", True) else "")
                + (node.properties.get("code_name") or node.display_name)
                + (
                    " · " + ntr("{count} event", "{count} events", count).format(count=count)
                    if count
                    else ""
                ),
            )
        if self.active_state != "@default":
            state = next(
                s for s in self.project.states[self.active_window] if s["id"] == self.active_state
            )
            self.inspector._overrides = state.get("overrides", {}).get(identifier, {})
        if identifier == self.selected_id:
            if key == "icon":
                self.inspector._binding_signature = None
                self._select(identifier)
            elif not key.startswith("geometry."):
                self.inspector.patch_value(key, effective.properties.get(key, ""))
        self._presentation_signature = self.presentation_signature()
        if not finish:
            return
        self.logic.sync()
        self._update_code()
        self._update_actions()
        if hasattr(self, "zoom_view"):
            self.zoom_view.update_bounds()

    def choose_component_icon(self, identifier):
        """Import a portable icon into the document, never linking external paths."""
        filename, _ = QFileDialog.getOpenFileName(
            self, tr("Button icon"), "", tr("Icons (*.png *.svg)")
        )
        if filename:
            try:
                self._change_property(identifier, "icon", self.assets.import_image(Path(filename)))
            except (OSError, ProjectError) as exc:
                self._show_error(exc, tr("Could not use this icon"))

    def reveal_navigation(self, edge):
        """The Designer's inspector opens the exact connection in the Map."""
        self.set_mode("map")
        line = next(
            (
                line
                for line in self.map_panel.edges
                if line.edge["flow"] == edge["flow"] and line.edge["block"] == edge["block"]
            ),
            None,
        )
        if line:
            self.map_panel.view.scene().clearSelection()
            line.setSelected(True)
            self.map_panel.view.ensureVisible(line)

    def _finish_field_edit(self) -> bool:
        """Commit text still being edited before saving or replacing the project."""
        # Also commits edits made through accessibility/tests without an active window.
        from PySide6.QtWidgets import QLineEdit

        for field in self.inspector.findChildren(QLineEdit):
            if field.isModified():
                field.setModified(False)
                field.editingFinished.emit()
        focus = QApplication.focusWidget()
        if focus is not None:
            focus.clearFocus()
        if not self.prepare_script_change():
            return False
        return self.logic.flush()

    def add_component(self) -> None:
        """Insert into the container or page that fits the current selection."""
        if self.active_state != "@default":
            self.statusBar().showMessage(tr("Add components in the Default state."), 6000)
            return
        kind = ComponentKind(self.palette.currentData())

        def insert():
            """Insert the chosen type into the destination resolved from the selection."""
            parent = self._insertion_parent(kind)
            self.selected_id = self.project.add(parent.id, kind).id

        self._edit(insert)

    def _insertion_parent(self, kind: ComponentKind) -> Component:
        """Resolve insertions from the button, including inside selected pages."""
        node = self.project.find(self.selected_id)
        if node.kind == ComponentKind.PAGES and kind != ComponentKind.PAGE:
            return self.canvas.visible_page(node)
        while node:
            if node.accepts(kind):
                return node
            node = self.project.parent_of(node.id)
        raise ProjectError(tr("Select a set of pages to add a page."))

    def _page_group(self, node: Component) -> Component | None:
        """Find the set of pages closest to the selection."""
        while node:
            if node.kind == ComponentKind.PAGES:
                return node
            node = self.project.parent_of(node.id)
        return None

    def _edit(self, change: Callable[[], None], refresh=True, label: str | None = None) -> None:
        """Group a command into one change and restore the document if it fails.

        `label` names the change for Undo/Redo; when omitted it comes from
        UNDO_LABELS, keyed by the name of the command that called this method.
        """
        if label is None:
            import sys

            label = undo_labels().get(sys._getframe(1).f_code.co_name, tr("Edit"))
        if not self._finish_field_edit():
            return
        before = self.project.to_dict()
        selection = self.selected_id
        try:
            change()
            Project.from_dict(self.project.to_dict())
        except ProjectError as exc:
            self.project = Project.from_dict(before)
            self.selected_id = selection
            self._refresh()
            self._show_error(exc, tr("Could not apply the change"))
            return
        self.history.push(self.project, label)
        if refresh:
            self._refresh()
        else:
            self._update_actions()

    def change_application(self, key, value):
        """App metadata does not need to destroy the widgets of the interface being edited."""
        if self.project.application.get(key) == value or not self._finish_field_edit():
            return
        before = deepcopy(self.project.application)
        self.project.application[key] = value
        try:
            Project.from_dict(self.project.to_dict())
        except ProjectError as exc:
            self.project.application = before
            self._show_error(exc, tr("Could not change the application settings"))
            return
        self.history.push(self.project, tr("Change application settings"))
        if key == "backend":
            self._refresh()
        else:
            self.canvas._project.application = deepcopy(self.project.application)
            self._update_actions()

    def _can_drop(self, payload: dict, parent_id: str) -> bool:
        """Validate a drag without changing the document while the mouse passes over."""
        if self.active_state != "@default":
            return False
        parent = self.project.find(parent_id)
        if parent is None:
            return False
        if payload.get("mode") == "new":
            try:
                return parent.accepts(ComponentKind(payload["kind"]))
            except (KeyError, ValueError):
                return False
        node = self.project.find(payload.get("id"))
        if payload.get("project") != self.project.id or node is None:
            return False
        previous = self.project.parent_of(node.id)
        return bool(
            previous
            and parent.accepts(node.kind)
            and parent.id not in {child.id for child in node.walk()}
            and not (
                previous is not parent
                and previous.kind == ComponentKind.PAGES
                and len(previous.children) == 1
            )
        )

    def _on_drop(self, payload: dict, parent_id: str, index: int, geometry: dict | None) -> None:
        """Turn a tree or screen drop into a model edit."""
        if not self._can_drop(payload, parent_id):
            return

        def apply():
            """Apply the creation/move and the drop geometry at once."""
            if payload["mode"] == "new":
                node = self.project.add(parent_id, ComponentKind(payload["kind"]))
            else:
                node = self.project.find(payload["id"])
            self.project.move(node.id, parent_id, index)
            parent = self.project.find(parent_id)
            if geometry and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE:
                snapped = {
                    key: max(0, min(20000, round(value / self.canvas.snap) * self.canvas.snap))
                    for key, value in geometry.items()
                }
                self.project.set_geometry(node.id, snapped)
            self.selected_id = node.id

        self._edit(apply)

    def _resize_window(self, width: int, height: int) -> None:
        """Store the size the window opens with, as one step in the history."""
        identifier = self.project.root.id
        self._edit(
            lambda: self.project.find(identifier).properties.update(width=width, height=height)
        )

    def _commit_geometry(self, node_id: str, geometry: dict) -> None:
        """Record a complete move/resize without fragmenting the history."""
        if self.active_state != "@default":
            self._refresh()
            return
        node = self.project.find(node_id)
        ids = getattr(self, "selected_ids", {node_id})
        if (
            len(ids) > 1
            and node_id in ids
            and geometry.get("width", node.geometry["width"]) == node.geometry["width"]
            and geometry.get("height", node.geometry["height"]) == node.geometry["height"]
        ):
            dx = geometry.get("x", node.geometry["x"]) - node.geometry["x"]
            dy = geometry.get("y", node.geometry["y"]) - node.geometry["y"]
            siblings = [
                self.project.find(identifier)
                for identifier in ids
                if self.project.parent_of(identifier) is self.project.parent_of(node_id)
            ]
            dx = max(
                -min(item.geometry["x"] for item in siblings),
                min(dx, 20000 - max(item.geometry["x"] for item in siblings)),
            )
            dy = max(
                -min(item.geometry["y"] for item in siblings),
                min(dy, 20000 - max(item.geometry["y"] for item in siblings)),
            )

            def move_group():
                """Move the group keeping relative positions and valid bounds."""
                for identifier in ids:
                    item = self.project.find(identifier)
                    if self.project.parent_of(identifier) is self.project.parent_of(node_id):
                        self.project.set_geometry(
                            identifier,
                            {
                                "x": max(0, min(20000, item.geometry["x"] + dx)),
                                "y": max(0, min(20000, item.geometry["y"] + dy)),
                            },
                        )

            self._edit(move_group, refresh=False)
            self.patch_geometries(ids)
        else:
            self._edit(lambda: self.project.set_geometry(node_id, geometry), refresh=False)
            self.patch_geometries([node_id])

    def duplicate_component(self) -> None:
        """Duplicate the selection with its own identifiers and keep the copy selected."""
        if self.active_state != "@default":
            self.statusBar().showMessage(tr("Edit the structure in the Default state."), 6000)
            return

        def duplicate():
            """Duplicate the selection's top nodes and keep the copied group selected."""
            identifiers = self.top_level_selection()
            copies = [self.project.duplicate(identifier).id for identifier in identifiers]
            self.selected_ids = set(copies)
            self.selected_id = copies[-1]

        self._edit(duplicate)

    def reorder_component(self, direction: int) -> None:
        """Offer keyboard reordering, with the same semantics as dragging."""

        def reorder():
            """Turn the command's direction into an insertion position."""
            node = self.project.find(self.selected_id)
            parent = self.project.parent_of(node.id)
            if parent:
                old_index = parent.children.index(node)
                self.project.move(node.id, parent.id, old_index + (2 if direction > 0 else -1))

        self._edit(reorder)

    def add_page(self) -> None:
        """Add a page to the selected set or an ancestor."""
        if self.active_state != "@default":
            self.statusBar().showMessage(tr("Edit the structure in the Default state."), 6000)
            return

        def add():
            """Insert a page into the selection's ancestor set."""
            group = self._page_group(self.project.find(self.selected_id))
            if group is not None:
                self.selected_id = self.project.add(group.id, ComponentKind.PAGE).id

        self._edit(add)

    def nudge_component(self, dx: int, dy: int) -> None:
        """Nudge a free component in fine steps without affecting other layouts."""
        node = self.project.find(self.selected_id)
        parent = self.project.parent_of(node.id)
        if parent and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE:
            self._commit_geometry(
                node.id,
                {
                    "x": max(0, min(20000, node.geometry["x"] + dx)),
                    "y": max(0, min(20000, node.geometry["y"] + dy)),
                },
            )

    def align_component(self, mode: str) -> None:
        """Align the selection to the visible bounds of its free container."""
        node = self.project.find(self.selected_id)
        parent = self.project.parent_of(node.id)
        if not parent or parent.layout != LayoutKind.FREE or parent.kind == ComponentKind.PAGES:
            return
        area = self.canvas._frames[parent.id].contentsRect()
        x, y = node.geometry["x"], node.geometry["y"]
        if mode in {"left", "center_x", "right"}:
            remaining = area.width() - node.geometry["width"]
            x = 8 if mode == "left" else remaining // 2 if mode == "center_x" else remaining - 8
        else:
            remaining = area.height() - node.geometry["height"]
            y = 8 if mode == "top" else remaining // 2 if mode == "center_y" else remaining - 8
        self._commit_geometry(node.id, {"x": max(0, min(20000, x)), "y": max(0, min(20000, y))})

    def choose_image(self, node_id: str) -> None:
        """Import an explicitly chosen image, copying it when saving."""
        filename, _ = QFileDialog.getOpenFileName(
            self, tr("Choose image"), "", tr("Images (*.png *.jpg *.jpeg *.webp)")
        )
        if not filename:
            return

        def choose():
            """Reserve the imported asset and update the visual reference."""
            source = self.assets.import_image(Path(filename))
            node = self.project.find(node_id)
            node.properties.update(source=source, image_name=Path(filename).name)

        self._edit(choose)

    def clear_image(self, node_id: str) -> None:
        """Remove the visual reference, keeping the asset available for undo."""

        def clear():
            """Clear the image without removing the asset from the session history."""
            node = self.project.find(node_id)
            node.properties.update(source="", image_name="")

        self._edit(clear)

    def remove_component(self) -> None:
        """Remove the selection, keeping the deletion available for undo."""
        if self.active_state != "@default":
            self.statusBar().showMessage(tr("Edit the structure in the Default state."), 6000)
            return
        if not self._finish_field_edit():
            return
        node = self.project.find(self.selected_id)
        if node and node.kind == ComponentKind.WINDOW:
            if len(self.project.roots) > 1:
                self.remove_window()
            return
        if len(getattr(self, "selected_ids", set())) > 1:

            def remove_group():
                """Group sibling/container removals into a single reversible change."""
                identifiers = self.top_level_selection()
                parent = self.project.parent_of(identifiers[0])
                for identifier in identifiers:
                    self.project.remove(identifier)
                self.selected_id = (
                    parent.id if parent and self.project.find(parent.id) else self.active_window
                )
                self.selected_ids = {self.selected_id}

            self._edit(remove_group)
            return
        try:
            self.selected_id = self.project.remove(self.selected_id)
        except ProjectError as exc:
            self._show_error(exc, tr("Could not remove the component"))
            return
        self.history.push(self.project, tr("Remove component"))
        self._refresh()
