# SPDX-License-Identifier: MIT
"""Runnable Qt interface, using the same controls/layouts as the designer."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QTableWidget,
    QDoubleSpinBox,
    QFrame,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
)
from makebench.core.project import ComponentKind
from makebench.core.style import qt_stylesheet, window_style
from makebench.core.web import WEB_PAGE, is_web
from makebench.ui import web
from makebench.ui.renderer import (
    TextArea,
    apply_component_style,
    create_control,
    place_children,
    set_background_image,
)
from makebench.i18n import tr


class RuntimeView(QFrame):
    """Interface instance independent of the editable document and its handles."""

    clicked = Signal(str)
    changed = Signal(str)

    def __init__(self, project, read_asset, parent=None, window_root=None):
        """Render the snapshot and keep controls for context reads/changes."""
        super().__init__(parent)
        self.project = project
        self.read_asset = read_asset
        self.window_root = window_root or project.root
        self.style_changes = {}
        self.widgets = {}
        self.frames = {}
        self.tabs = {}
        self.enabled = {}
        self.busy = False
        self.event_buttons = {
            f["event"]["component"] for f in project.workflows if f["event"]["kind"] == "click"
        }
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self._fill(layout)
        self.apply_style(window_style(self.window_root.properties))
        if not is_web(self.window_root):
            set_background_image(self, self.window_root, self.read_asset)

    def apply_style(self, style):
        """Scope the look to this window; other windows and the editor are untouched."""
        self.setObjectName("mbWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(qt_stylesheet(style, "mbWindow"))

    def change_style(self, **changes):
        """Used by ctx.set_theme/set_background while the application runs."""
        self.style_changes.update(changes)
        self.apply_style(window_style({**self.window_root.properties, **self.style_changes}))

    def reset(self):
        """Re-create the controls of a closed window when it opens again."""
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.widgets = {}
        self.frames = {}
        self.tabs = {}
        self.enabled = {}
        self.busy = False
        self.style_changes = {}
        self._fill(layout)
        self.apply_style(window_style(self.window_root.properties))

    def _fill(self, layout):
        """A Web view window is its page, edge to edge; any other window has components."""
        if is_web(self.window_root):
            layout.setContentsMargins(0, 0, 0, 0)
            page = web.web_widget(self.window_root.properties[WEB_PAGE], self.read_asset)
            self.widgets[self.window_root.id] = page
            self.frames[self.window_root.id] = page
            layout.addWidget(page)
        else:
            layout.addWidget(self._render(self.window_root))

    def _render(self, node):
        """Build containers/pages and connect clicks only in the running instance."""
        frame = QFrame()
        self.frames[node.id] = frame
        self.widgets[node.id] = frame
        self.enabled[node.id] = node.properties.get("enabled", True)
        if node.kind == ComponentKind.PAGES:
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(4, 4, 4, 4)
            tabs = QTabWidget()
            self.tabs[node.id] = tabs
            for page in node.children:
                tabs.addTab(self._render(page), page.properties.get("title", tr("Page")))
            tabs.setCurrentIndex(
                next(
                    i
                    for i, page in enumerate(node.children)
                    if page.id == node.properties["initial_page"]
                )
            )
            layout.addWidget(tabs)
        elif node.can_have_children:
            place_children(frame, node, self._render)
            if node.kind != ComponentKind.WINDOW:
                apply_component_style(frame, node, container=True)
        else:
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(4, 4, 4, 4)
            widget = create_control(node, self.read_asset)
            self.widgets[node.id] = widget
            layout.addWidget(widget)
            if isinstance(widget, QPushButton):
                widget.clicked.connect(lambda _, identifier=node.id: self.clicked.emit(identifier))
            if isinstance(widget, QLineEdit):
                widget.textEdited.connect(
                    lambda _, identifier=node.id: self.changed.emit(identifier)
                )
            if isinstance(widget, QCheckBox):
                widget.clicked.connect(lambda _, identifier=node.id: self.changed.emit(identifier))
            if isinstance(widget, QTableWidget):
                widget.itemSelectionChanged.connect(
                    lambda identifier=node.id: self.changed.emit(identifier)
                )
            if isinstance(widget, QDateEdit):
                widget.dateChanged.connect(
                    lambda _, identifier=node.id: self.changed.emit(identifier)
                )
            if isinstance(widget, QComboBox):
                widget.activated.connect(
                    lambda _, identifier=node.id: self.changed.emit(identifier)
                )
            if isinstance(widget, TextArea):
                widget.edited.connect(lambda identifier=node.id: self.changed.emit(identifier))
            if isinstance(widget, (QDoubleSpinBox, QSlider)):
                widget.valueChanged.connect(
                    lambda _, identifier=node.id: self.changed.emit(identifier)
                )
            if isinstance(widget, QPlainTextEdit):
                widget.setMaximumBlockCount(2000)
        return frame

    def set_busy(self, busy):
        """Block concurrent clicks without undoing set_enabled done by the application."""
        self.busy = busy
        for identifier in self.event_buttons & self.widgets.keys():
            self.widgets[identifier].setEnabled(self.enabled[identifier] and not busy)

    def set_enabled(self, identifier, enabled):
        """Keep the application's intent separate from the temporary run lock."""
        self.enabled[identifier] = enabled
        self.widgets[identifier].setEnabled(
            enabled and not (self.busy and identifier in self.event_buttons)
        )

    def set_visible(self, identifier, visible):
        """A page belongs to its tab widget: showing its frame directly would
        draw it over the current page, so pages hide or show their tab instead."""
        parent = self.project.parent_of(identifier)
        if parent is not None and parent.kind == ComponentKind.PAGES and parent.id in self.tabs:
            index = [child.id for child in parent.children].index(identifier)
            self.tabs[parent.id].setTabVisible(index, visible)
            return
        self.frames[identifier].setVisible(visible)

    def show_page(self, identifier):
        """Reveal pages even inside nested sets of pages."""
        node = self.project.find(identifier)
        if node is None or node.kind != ComponentKind.PAGE:
            raise ValueError(tr("The page does not exist."))
        parent = self.project.parent_of(identifier)
        while parent:
            if parent.kind == ComponentKind.PAGES:
                self.tabs[parent.id].setCurrentIndex(parent.children.index(node))
            node, parent = parent, self.project.parent_of(parent.id)
