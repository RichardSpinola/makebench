# SPDX-License-Identifier: GPL-3.0-or-later
"""Contextual inspector by scope, with collapsible sections and accessible fields."""

from PySide6.QtCore import QRect, Qt, Signal, QEvent, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QDoubleSpinBox,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from makebench.core.project import (
    KIND_LABELS,
    LAYOUT_LABELS,
    RANGE_DEFAULTS,
    RANGE_KINDS,
    ComponentKind,
    LayoutKind,
)
from makebench.i18n import ntr, tr

from .theme import blend, icon, manager

ROW_HEIGHT = 24
LABEL_WIDTH = 104


class SectionHeader(QToolButton):
    """Full-width group bar: ▾/▸ and a bold title on the group color."""

    def __init__(self, title):
        super().__init__()
        self.setText(title)
        self.setCheckable(True)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.DemiBold)
        self.setFont(bold)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event):
        t = manager().tokens
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(blend(t["panel"], t["text"], 0.07)))
        painter.fillRect(QRect(0, self.height() - 1, self.width(), 1), QColor(t["border"]))
        if self.hasFocus():
            painter.fillRect(QRect(0, 0, 2, self.height()), QColor(t["accent"]))
        painter.setPen(QColor(t["muted"]))
        arrow = QRect(6, 0, 12, self.height())
        painter.drawText(arrow, Qt.AlignmentFlag.AlignCenter, "▾" if self.isChecked() else "▸")
        painter.setPen(QColor(t["text"]))
        painter.drawText(
            self.rect().adjusted(22, 0, -6, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )


class PropertyTable(QWidget):
    """Two-column property grid: label cells on the left, flat editors on the right."""

    def __init__(self):
        super().__init__()
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setHorizontalSpacing(0)
        self.form.setVerticalSpacing(0)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def event(self, event):
        if event.type() == QEvent.Type.LayoutRequest:
            self.flatten()
        return super().event(event)

    def flatten(self):
        """Give every row the table look: fixed label width, frameless editors, even height."""
        for row in range(self.form.rowCount()):
            label = self.form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            field = self.form.itemAt(row, QFormLayout.ItemRole.FieldRole)
            span = self.form.itemAt(row, QFormLayout.ItemRole.SpanningRole)
            if label and label.widget() and not label.widget().property("tableCell"):
                widget = label.widget()
                widget.setProperty("tableCell", True)
                widget.setMinimumWidth(max(LABEL_WIDTH, widget.sizeHint().width()))
                widget.setContentsMargins(8, 0, 6, 0)
                widget.setMinimumHeight(ROW_HEIGHT)
            for item in (field, span):
                widget = item.widget() if item else None
                if widget is None or widget.property("tableCell"):
                    continue
                widget.setProperty("tableCell", True)
                if isinstance(widget, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox)):
                    widget.setFrame(False)
                    widget.setAutoFillBackground(False)
                if item is span and isinstance(widget, QCheckBox):
                    widget.setContentsMargins(8, 0, 0, 0)
                if isinstance(
                    widget, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QPushButton)
                ):
                    widget.setMinimumHeight(ROW_HEIGHT)

    def paintEvent(self, _event):
        t = manager().tokens
        painter = QPainter(self)
        line = QColor(t["border"])
        cell = QColor(blend(t["panel"], t["text"], 0.03))
        rows = [QColor(t["raised"]), QColor(blend(t["raised"], t["text"], 0.025))]
        for row in range(self.form.rowCount()):
            items = [
                self.form.itemAt(row, role)
                for role in (
                    QFormLayout.ItemRole.LabelRole,
                    QFormLayout.ItemRole.FieldRole,
                    QFormLayout.ItemRole.SpanningRole,
                )
            ]
            geometry = [i.geometry() for i in items if i and i.widget() and i.widget().isVisible()]
            if not geometry:
                continue
            top = min(g.top() for g in geometry)
            bottom = max(g.bottom() for g in geometry)
            band = QRect(0, top, self.width(), bottom - top + 1)
            painter.fillRect(band, rows[row % 2])
            if items[0] and items[0].widget():
                edge = items[0].geometry().right() + 1
                painter.fillRect(QRect(0, top, edge, band.height()), cell)
                painter.fillRect(QRect(edge, top, 1, band.height()), line)
            painter.fillRect(QRect(0, bottom, self.width(), 1), line)


class Inspector(QWidget):
    """Show the content, arrangement, size and events relevant to the selection."""

    property_changed = Signal(str, str, object)
    batch_changed = Signal(str, object)
    image_requested = Signal(str)
    image_cleared = Signal(str)
    logic_requested = Signal(str)
    icon_requested = Signal(str)
    navigation_requested = Signal(dict)
    selection_command = Signal(str)
    layout_preview_requested = Signal(str, str)
    restore_requested = Signal(str, str)

    def __init__(self, parent=None):
        """Keep only presentation state; the document stays in the project."""
        super().__init__(parent)
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 6, 0, 8)
        self.form.setHorizontalSpacing(6)
        self.form.setVerticalSpacing(4)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields = self.form
        self._expanded = {}
        self._overrides = {}
        self._kind = ""
        self.setMinimumWidth(220)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(400)
        self.preview_timer.timeout.connect(self.emit_preview)
        self._preview = None

    def clear(self):
        """Remove the previous views, including connections and fields from another scope."""
        self._binding_signature = None
        self.preview_timer.stop()
        self._preview = None
        while self.form.rowCount():
            row = self.form.takeRow(0)
            for item in (row.labelItem, row.fieldItem):
                if item and item.widget():
                    widget = item.widget()
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
        self.fields = self.form

    def section(self, title, expanded=True):
        """Create a section whose open state is remembered per component type."""
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = SectionHeader(title)
        body = PropertyTable()
        key = (self._kind, title)
        opened = self._expanded.get(key, expanded)
        header.setChecked(opened)
        body.setVisible(opened)

        def toggle(value):
            """Remember the section's open state without changing the document."""
            self._expanded[key] = value
            body.setVisible(value)

        header.toggled.connect(toggle)
        layout.addWidget(header)
        layout.addWidget(body)
        self.form.addRow(wrapper)
        self.fields = body.form

    def set_component(self, project, node, overrides=None, state_mode=False):
        """Render effective properties; ● marks differences in the active state."""
        import html
        import json

        parent = project.parent_of(node.id)
        from makebench.core.navigation import navigation_edges

        flows = {f["id"] for f in project.editable_flows if f["event"]["component"] == node.id}
        interactions = json.dumps(
            (
                [f["id"] for f in project.editable_flows if f["id"] in flows],
                [e for e in navigation_edges(project) if e["flow"] in flows],
            ),
            sort_keys=True,
        )
        signature = (
            id(project),
            project.name,
            json.dumps(node.to_dict(), sort_keys=True),
            parent.id if parent else None,
            parent.display_name if parent else None,
            json.dumps(overrides or {}, sort_keys=True),
            state_mode,
            interactions,
        )
        if signature == getattr(self, "_binding_signature", None):
            return
        self.clear()
        self._binding_signature = signature
        self._kind = node.kind.value
        self._overrides = overrides or {}
        self.state_mode = state_mode
        name = node.properties.get("code_name") or node.display_name
        heading = QLabel(
            "<b>{}</b> <span style='color:{}'>: {}</span>".format(
                html.escape(name), manager().tokens["muted"], KIND_LABELS[node.kind]
            )
        )
        heading.setContentsMargins(8, 0, 8, 0)
        heading.setTextFormat(Qt.TextFormat.RichText)
        heading.setAccessibleName(f"{name}: {KIND_LABELS[node.kind]}")
        self.form.addRow(heading)
        parent = project.parent_of(node.id)
        if parent:
            caption = QLabel(
                tr("Inside: {name}").format(
                    name=parent.properties.get("code_name") or parent.display_name
                )
            )
            caption.setWordWrap(True)
            caption.setProperty("muted", True)
            caption.setContentsMargins(8, 0, 8, 0)
            self.form.addRow(caption)
        self.section(tr("Content"))
        for key, label in [
            ("title", tr("Title")),
            ("text", tr("Text")),
            ("placeholder", tr("Field hint")),
        ]:
            if key in node.properties:
                self._text_field(label, node.id, key, node.properties[key])
        if node.kind == ComponentKind.BUTTON:
            self._text_field(tr("Tooltip"), node.id, "tooltip", node.properties.get("tooltip", ""))
            choose_icon = QPushButton(
                tr("Choose icon…") if not node.properties.get("icon") else tr("Change icon…")
            )
            choose_icon.setEnabled(not self.state_mode)
            choose_icon.clicked.connect(lambda: self.icon_requested.emit(node.id))
            self.fields.addRow(tr("Icon"), choose_icon)
            if node.properties.get("icon"):
                clear_icon = QPushButton(tr("Remove icon"))
                clear_icon.setEnabled(not self.state_mode)
                clear_icon.clicked.connect(lambda: self.property_changed.emit(node.id, "icon", ""))
                self.fields.addRow(clear_icon)
        if node.kind == ComponentKind.IMAGE:
            filename = QLabel(node.properties.get("image_name") or tr("No image"))
            filename.setWordWrap(True)
            self.fields.addRow(tr("File"), filename)
            button = QPushButton(tr("Choose or replace image…"))
            button.clicked.connect(lambda: self.image_requested.emit(node.id))
            self.fields.addRow(button)
            clear = QPushButton(tr("Remove image"))
            clear.setEnabled(bool(node.properties.get("source")))
            clear.clicked.connect(lambda: self.image_cleared.emit(node.id))
            self.fields.addRow(clear)
            self._text_field(
                tr("Accessible description"),
                node.id,
                "alt_text",
                node.properties.get("alt_text", ""),
            )
        if node.kind == ComponentKind.TERMINAL:
            self._text_field(
                tr("Program (empty = shell)"),
                node.id,
                "terminal_program",
                node.properties.get("terminal_program", ""),
            )
            self._boolean_field(
                tr("Start when the application runs"),
                node.id,
                "terminal_autostart",
                node.properties.get("terminal_autostart", False),
            )
            import shlex

            arguments = QLineEdit(shlex.join(node.properties.get("terminal_arguments", [])))

            def change_arguments():
                """Interpret only argv; never runs the properties' text."""
                try:
                    values = shlex.split(arguments.text())
                except ValueError:
                    arguments.setToolTip(tr("Unbalanced quotes in the arguments."))
                    return
                self.property_changed.emit(node.id, "terminal_arguments", values)

            arguments.editingFinished.connect(change_arguments)
            arguments.setEnabled(not self.state_mode)
            self.fields.addRow(tr("Arguments"), arguments)
        if node.kind == ComponentKind.PROGRESS:
            self._number_field(
                tr("Progress (%)"), node.id, "value", node.properties.get("value", 0), 0, 100
            )
        if node.kind in RANGE_KINDS:
            r = {**RANGE_DEFAULTS, **node.properties}
            digits = 0 if node.kind == ComponentKind.SLIDER else r["decimals"]
            for label, key in [
                (tr("Value"), "value"),
                (tr("Minimum"), "minimum"),
                (tr("Maximum"), "maximum"),
                (tr("Step"), "step"),
            ]:
                self._decimal_field(label, node.id, key, r[key], digits)
            if node.kind == ComponentKind.NUMBER:
                self._number_field(tr("Decimals"), node.id, "decimals", r["decimals"], 0, 6)
        if node.kind == ComponentKind.PAGES:
            pages = QComboBox()
            for child in node.children:
                pages.addItem(child.properties.get("title", tr("Page")), child.id)
            pages.setCurrentIndex(pages.findData(node.properties["initial_page"]))
            pages.currentIndexChanged.connect(
                lambda _: self.property_changed.emit(node.id, "initial_page", pages.currentData())
            )
            self.fields.addRow(tr("Initial page"), pages)
        self.section(tr("Layout"))
        if node.can_have_children and node.kind != ComponentKind.PAGES:
            segments = QWidget()
            row = QGridLayout(segments)
            row.setContentsMargins(4, 4, 4, 4)
            row.setSpacing(4)
            for index, (mode, label) in enumerate(LAYOUT_LABELS.items()):
                button = QPushButton(label)
                button.setCheckable(True)
                button.setChecked(node.layout == mode)
                button.setEnabled(not self.state_mode)
                button.setAccessibleName(tr("Arrange as {layout}").format(layout=label))
                button.setProperty("layoutNode", node.id)
                button.setProperty("layoutMode", mode.value)
                button.installEventFilter(self)
                button.clicked.connect(
                    lambda _, mode=mode: self.property_changed.emit(node.id, "layout", mode.value)
                )
                row.addWidget(button, index // 2, index % 2)
            self.fields.addRow(segments)
            if node.layout != LayoutKind.FREE:
                self._number_field(
                    tr("Spacing"), node.id, "spacing", node.properties.get("spacing", 6), 0, 2000
                )
                self._number_field(
                    tr("Inner margins"),
                    node.id,
                    "padding",
                    node.properties.get("padding", 8),
                    0,
                    2000,
                )
                pad = QWidget()
                grid = QGridLayout(pad)
                grid.setContentsMargins(4, 3, 4, 3)
                grid.setSpacing(2)
                symbols = ["↖", "↑", "↗", "←", "·", "→", "↙", "↓", "↘"]
                for row, y in enumerate(["top", "center", "bottom"]):
                    for column, x in enumerate(["left", "center", "right"]):
                        value = y + "-" + x
                        button = QToolButton()
                        button.setText(symbols[row * 3 + column])
                        button.setFixedSize(28, 28)
                        button.setCheckable(True)
                        button.setChecked(node.properties.get("alignment_preset") == value)
                        button.setEnabled(not self.state_mode)
                        button.setAccessibleName(
                            tr("Alignment {vertical} {horizontal}").format(
                                vertical={
                                    "top": tr("top"),
                                    "center": tr("middle"),
                                    "bottom": tr("bottom"),
                                }[y],
                                horizontal={
                                    "left": tr("left"),
                                    "center": tr("center"),
                                    "right": tr("right"),
                                }[x],
                            )
                        )
                        button.setToolTip(button.accessibleName())
                        button.clicked.connect(
                            lambda _, value=value: self.property_changed.emit(
                                node.id, "alignment_preset", value
                            )
                        )
                        grid.addWidget(button, row, column)
                self.fields.addRow(tr("Alignment"), pad)
                self._choice_field(
                    tr("Align"),
                    node.id,
                    "align",
                    node.properties.get("align", "start"),
                    [
                        (tr("Start"), "start"),
                        (tr("Center"), "center"),
                        (tr("End"), "end"),
                        (tr("Fill"), "stretch"),
                    ],
                )
                self._choice_field(
                    tr("Distribute"),
                    node.id,
                    "distribute",
                    node.properties.get("distribute", "start"),
                    [
                        (tr("Start"), "start"),
                        (tr("Center"), "center"),
                        (tr("End"), "end"),
                        (tr("Between elements"), "space-between"),
                    ],
                )
            if node.layout == LayoutKind.GRID:
                self._number_field(
                    tr("Columns"), node.id, "columns", node.properties.get("columns", 2), 1, 12
                )
        if node.kind == ComponentKind.WINDOW:
            self._number_field(
                tr("Initial width"), node.id, "width", node.properties.get("width", 640), 200, 4000
            )
            self._number_field(
                tr("Initial height"),
                node.id,
                "height",
                node.properties.get("height", 480),
                160,
                4000,
            )
            self._boolean_field(
                tr("Resizable"), node.id, "resizable", node.properties.get("resizable", True)
            )
            self._number_field(
                tr("Timer every (seconds, 0 = off)"),
                node.id,
                "timer_seconds",
                node.properties.get("timer_seconds", 0),
                0,
                3600,
            )
            self.section(tr("Window look"))
            self._choice_field(
                tr("Theme"),
                node.id,
                "theme",
                node.properties.get("theme", "system"),
                [(tr("System"), "system"), (tr("Light"), "light"), (tr("Dark"), "dark")],
            )
            self._color_field(tr("Accent color"), node.id, "accent", node.properties)
            self._color_field(tr("Background color"), node.id, "background", node.properties)
        elif parent:
            for axis, label in (
                []
                if parent.layout == LayoutKind.FREE
                else [("width", tr("Width")), ("height", tr("Height"))]
            ):
                field = QComboBox()
                for text, value in [
                    (tr("Fit to content"), "content"),
                    (tr("Fill"), "fill"),
                    (tr("Fixed"), "fixed"),
                ]:
                    field.addItem(text, value)
                field.setCurrentIndex(
                    field.findData(node.properties.get("size_mode", {}).get(axis, "content"))
                )

                def change_mode(_, axis=axis, field=field):
                    """Update the sizing of the chosen axis."""
                    modes = dict(node.properties.get("size_mode", {}))
                    modes[axis] = field.currentData()
                    self.property_changed.emit(node.id, "size_mode", modes)

                field.setEnabled(not self.state_mode)
                field.currentIndexChanged.connect(change_mode)
                field.setAccessibleName(label)
                self.fields.addRow(label, field)
                if node.properties.get("size_mode", {}).get(axis) == "fixed":
                    self._number_field(
                        label + " (px)", node.id, "geometry." + axis, node.geometry[axis], 1, 20000
                    )
            if parent.layout == LayoutKind.FREE and parent.kind != ComponentKind.PAGES:
                for key, label in [
                    ("x", "X"),
                    ("y", "Y"),
                    ("width", tr("Width (px)")),
                    ("height", tr("Height (px)")),
                ]:
                    self._number_field(
                        label,
                        node.id,
                        "geometry." + key,
                        node.geometry[key],
                        1 if key in {"width", "height"} else 0,
                        20000,
                    )
            else:
                hint = QLabel(
                    tr("Position set by the container ({layout}).").format(
                        layout=LAYOUT_LABELS[parent.layout]
                    )
                )
                hint.setWordWrap(True)
                hint.setProperty("muted", True)
                self.fields.addRow(hint)
        self.section(tr("State"))
        for key, label in [("visible", tr("Visible")), ("enabled", tr("Enabled"))]:
            self._boolean_field(label, node.id, key, node.properties.get(key, True))
        if node.kind == ComponentKind.CHECKBOX:
            self._boolean_field(
                tr("Initially selected"),
                node.id,
                "checked",
                node.properties.get("checked", False),
            )
        if node.kind in {
            ComponentKind.WINDOW,
            ComponentKind.BUTTON,
            ComponentKind.TEXT_INPUT,
            ComponentKind.CHECKBOX,
            *RANGE_KINDS,
        }:
            self.section(tr("Interactions"))
            count = sum(
                1
                for flow in project.editable_flows
                if flow.get("event", {}).get("component") == node.id
            )
            label = (
                tr("Edit logic")
                if count
                else tr("+ On start")
                if node.kind == ComponentKind.WINDOW
                else tr("+ On click")
                if node.kind == ComponentKind.BUTTON
                else tr("+ On change")
            )
            logic = QPushButton(
                label
                + (
                    " · " + ntr("{count} flow", "{count} flows", count).format(count=count)
                    if count
                    else ""
                )
            )
            logic.clicked.connect(lambda: self.logic_requested.emit(node.id))
            self.fields.addRow(logic)
            from makebench.core.navigation import navigation_edges

            for edge in [
                e
                for e in navigation_edges(project)
                if any(
                    f["id"] == e["flow"] and f["event"]["component"] == node.id
                    for f in project.editable_flows
                )
            ]:
                destination = project.find(edge["target"]) if edge["target"] else None
                text = (
                    tr("Navigation:")
                    + " "
                    + (
                        destination.display_name
                        if destination
                        else next(
                            (
                                s["name"]
                                for s in project.states.get(project.window_of(node.id).id, [])
                                if s["id"] == edge["target"]
                            ),
                            tr("Default"),
                        )
                    )
                )
                link = QToolButton()
                link.setText(text)
                link.setToolTip(tr("Inspect this transition in the Map"))
                link.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                link.setAutoRaise(True)
                link.clicked.connect(lambda _, edge=edge: self.navigation_requested.emit(edge))
                self.fields.addRow(link)
        self.section(tr("Advanced"), False)
        if node.kind == ComponentKind.WINDOW and node.id == project.root.id:
            self._text_field(tr("Project name"), "@project", "name", project.name)
        identifier = QLineEdit(node.id)
        identifier.setReadOnly(True)
        self.fields.addRow(tr("Internal identifier"), identifier)
        self._text_field(
            tr("Name in code"), node.id, "code_name", node.properties.get("code_name", "")
        )
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.form.addRow(self.error_label)

    def _restore_menu(self, field, node_id, key):
        """Offer per-property restore only when there is an override."""
        if key not in self._overrides:
            return
        field.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        def menu(point):
            """Offer an explicit restore of the selected property."""
            popup = QMenu(field)
            action = popup.addAction(tr("Restore from Default"))
            action.triggered.connect(lambda: self.restore_requested.emit(node_id, key))
            popup.exec(field.mapToGlobal(point))

        field.customContextMenuRequested.connect(menu)

    def _label(self, label, key):
        """Tie the change marker to the label, never relying on color alone."""
        return ("● " if key in self._overrides else "") + label

    def _text_field(self, label, node_id, key, value):
        """Confirm typing when leaving the field, as a single change."""
        field = QLineEdit(value)
        if self.state_mode and key in {"code_name", "tooltip"}:
            field.setReadOnly(True)
        field.setObjectName("property_" + key)
        field.setAccessibleName(label)
        field.editingFinished.connect(
            lambda: self.property_changed.emit(node_id, key, field.text())
        )
        self._restore_menu(field, node_id, key)
        self.fields.addRow(self._label(label, key), field)

    def _number_field(self, label, node_id, key, value, minimum, maximum):
        """Constrain values before sending an edit to the document."""
        field = QSpinBox()
        field.setObjectName("property_" + key)
        field.setRange(minimum, maximum)
        field.setValue(value)
        field.setKeyboardTracking(False)
        field.setAccessibleName(label)
        if self.state_mode and key not in {"value"}:
            field.setEnabled(False)
        field.valueChanged.connect(lambda value: self.property_changed.emit(node_id, key, value))
        self._restore_menu(field, node_id, key)
        self.fields.addRow(self._label(label, key), field)

    def _decimal_field(self, label, node_id, key, value, digits):
        """Edit a number that may have decimals; whole numbers stay whole in the document."""
        field = QDoubleSpinBox()
        field.setObjectName("property_" + key)
        field.setDecimals(digits)
        field.setRange(-1e12, 1e12)
        field.setValue(value)
        field.setKeyboardTracking(False)
        field.setAccessibleName(label)
        if self.state_mode and key != "value":
            field.setEnabled(False)
        field.valueChanged.connect(
            lambda number: self.property_changed.emit(
                node_id, key, number if digits else int(round(number))
            )
        )
        self._restore_menu(field, node_id, key)
        self.fields.addRow(self._label(label, key), field)

    def _boolean_field(self, label, node_id, key, value):
        """Show the initial condition or override without firing a run event."""
        field = QCheckBox(self._label(label, key))
        field.setChecked(value)
        field.setAccessibleName(label)
        if self.state_mode and key == "resizable":
            field.setEnabled(False)
        field.toggled.connect(lambda value: self.property_changed.emit(node_id, key, value))
        self._restore_menu(field, node_id, key)
        self.fields.addRow(field)

    def _color_field(self, label, node_id, key, properties):
        """Pick a #rrggbb color; Clear goes back to the theme's own value."""
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog

        value = properties.get(key, "")
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 2, 0)
        layout.setSpacing(2)
        pick = QPushButton(value or tr("Default"))
        pick.setFlat(True)
        pick.setObjectName("property_" + key)
        pick.setAccessibleName(label)
        if value:
            swatch = QPixmap(14, 14)
            swatch.fill(QColor(value))
            pick.setIcon(QIcon(swatch))
        clear = QToolButton()
        clear.setAutoRaise(True)
        clear.setIcon(icon("close"))
        clear.setProperty("makebenchIcon", "close")
        clear.setToolTip(tr("Clear"))
        clear.setAccessibleName(tr("Clear"))
        clear.setEnabled(bool(value) and not self.state_mode)
        pick.setEnabled(not self.state_mode)

        def choose():
            color = QColorDialog.getColor(QColor(value or "#3584e4"), self, label)
            if color.isValid():
                self.property_changed.emit(node_id, key, color.name())

        pick.clicked.connect(choose)
        clear.clicked.connect(lambda: self.property_changed.emit(node_id, key, ""))
        layout.addWidget(pick, 1)
        layout.addWidget(clear)
        self.fields.addRow(label, row)

    def _choice_field(self, label, node_id, key, value, options):
        """Use stable internal values, independent of translated labels."""
        field = QComboBox()
        for text, data in options:
            field.addItem(text, data)
        field.setCurrentIndex(field.findData(value))
        field.setAccessibleName(label)
        field.setEnabled(not self.state_mode)
        field.currentIndexChanged.connect(
            lambda _: self.property_changed.emit(node_id, key, field.currentData())
        )
        self.fields.addRow(label, field)

    def set_multiple(self, nodes, project=None, state_mode=False):
        """Show common/mixed values and block operations incompatible with the layout."""
        from makebench.core.navigation import OVERRIDES

        ids = tuple(sorted(node.id for node in nodes))
        parents = [project.parent_of(node.id) for node in nodes] if project else []
        free = bool(parents) and all(
            p and p.id == parents[0].id and p.layout == LayoutKind.FREE for p in parents
        )
        import json

        signature = (
            "multi",
            ids,
            json.dumps([n.to_dict() for n in nodes], sort_keys=True),
            free,
            state_mode,
        )
        if signature == getattr(self, "_binding_signature", None):
            return
        self.clear()
        self._binding_signature = signature
        self.state_mode = state_mode
        self._kind = "multiple"
        self.form.addRow(
            QLabel(
                ntr("{count} component", "{count} components", len(nodes)).format(count=len(nodes))
            )
        )
        self.section(tr("Common properties"))
        labels = {
            "text": tr("Text"),
            "tooltip": tr("Tooltip"),
            "visible": tr("Visible"),
            "enabled": tr("Enabled"),
            "checked": tr("Checked"),
            "placeholder": tr("Field hint"),
        }
        common = set.intersection(*(set(n.properties) for n in nodes)) | {
            "visible",
            "enabled",
            "tooltip",
        }
        for key, label in labels.items():
            if key not in common or state_mode and key not in OVERRIDES:
                continue
            values = [
                n.properties.get(key, True if key in {"visible", "enabled"} else "") for n in nodes
            ]
            mixed = any(v != values[0] for v in values[1:])
            if all(type(v) is bool for v in values):
                field = QCheckBox()
                field.setTristate(mixed)
                field.setCheckState(
                    Qt.CheckState.PartiallyChecked
                    if mixed
                    else Qt.CheckState.Checked
                    if values[0]
                    else Qt.CheckState.Unchecked
                )
                field.checkStateChanged.connect(
                    lambda state, key=key: (
                        self.batch_changed.emit(key, state == Qt.CheckState.Checked)
                        if state != Qt.CheckState.PartiallyChecked
                        else None
                    )
                )
            elif all(isinstance(v, str) for v in values):
                field = QLineEdit("" if mixed else values[0])
                field.setPlaceholderText(tr("Multiple values") if mixed else "")

                def finish(field=field, key=key):
                    """Never confirm a mixed field that only received focus."""
                    if field.isModified():
                        field.setModified(False)
                        self.batch_changed.emit(key, field.text())

                field.editingFinished.connect(finish)
            else:
                continue
            field.setObjectName("batch_" + key)
            field.setAccessibleName(label)
            self.fields.addRow(label, field)
        if free and not state_mode:
            for key, label in [
                ("x", "X"),
                ("y", "Y"),
                ("width", tr("Width")),
                ("height", tr("Height")),
            ]:
                values = [n.geometry[key] for n in nodes]
                mixed = len(set(values)) > 1
                field = QSpinBox()
                field.setRange(-1, 20000)
                field.setSpecialValueText(tr("Multiple values"))
                field.setKeyboardTracking(False)
                field.setValue(-1 if mixed else values[0])
                field.setObjectName("batch_geometry." + key)
                field.setAccessibleName(label)
                field.valueChanged.connect(
                    lambda value, key=key: (
                        self.batch_changed.emit("geometry." + key, value) if value >= 0 else None
                    )
                )
                self.fields.addRow(label, field)
        self.section(tr("Align and distribute"))
        wrapper = QWidget()
        grid = QGridLayout(wrapper)
        grid.setContentsMargins(0, 0, 0, 0)
        commands = [
            (tr("Left"), "left", "align-left"),
            (tr("Horizontal center"), "center_x", "align-center"),
            (tr("Right"), "right", "align-right"),
            (tr("Top"), "top", "align-top"),
            (tr("Vertical center"), "center_y", "align-center"),
            (tr("Bottom"), "bottom", "align-bottom"),
            (tr("Same width"), "same_width", "width"),
            (tr("Same height"), "same_height", "height"),
            (tr("Distribute horizontally"), "distribute_x", "distribute"),
            (tr("Distribute vertically"), "distribute_y", "distribute"),
        ]
        from .theme import icon

        for index, (label, mode, symbol) in enumerate(commands):
            button = QToolButton()
            button.setIcon(icon(symbol))
            button.setAccessibleName(label)
            button.setObjectName("selection_" + mode)
            enabled = (
                free and not state_mode and (not mode.startswith("distribute") or len(nodes) >= 3)
            )
            reason = (
                tr("Select siblings in a Free container in the Default state.")
                if not free or state_mode
                else tr("Select at least three components.")
            )
            button.setEnabled(enabled)
            button.setToolTip(label if enabled else label + " · " + reason)
            button.clicked.connect(lambda _, mode=mode: self.selection_command.emit(mode))
            grid.addWidget(button, index // 5, index % 5)
        self.fields.addRow(wrapper)

    def emit_preview(self):
        """Deliver the simulation after 400 ms of deliberate hover."""
        if self._preview:
            self.layout_preview_requested.emit(*self._preview)

    def eventFilter(self, obj, event):
        """Cancel the simulation when leaving the control, without touching the project."""
        if not getattr(self, "state_mode", False) and obj.property("layoutNode"):
            if event.type() == QEvent.Type.Enter:
                self._preview = (obj.property("layoutNode"), obj.property("layoutMode"))
                self.preview_timer.start()
            elif event.type() == QEvent.Type.Leave:
                self.preview_timer.stop()
                self._preview = None
                self.layout_preview_requested.emit(obj.property("layoutNode"), "")
        return super().eventFilter(obj, event)

    def patch_value(self, key, value):
        """Update an existing input if the change came from another command, without losing focus."""
        field = self.findChild(QWidget, "property_" + key)
        if field is None:
            return
        blocked = field.blockSignals(True)
        try:
            if isinstance(field, QLineEdit) and field.text() != str(value):
                field.setText(str(value))
            elif isinstance(field, (QSpinBox, QDoubleSpinBox)) and field.value() != value:
                field.setValue(value)
        finally:
            field.blockSignals(blocked)
