"""Runnable Qt interface, using the same controls/layouts as the designer."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout
from makebench.core.project import ComponentKind
from makebench.ui.renderer import create_control, place_children
from makebench.i18n import tr


class RuntimeView(QFrame):
    """Interface instance independent of the editable document and its handles."""

    clicked = Signal(str)

    def __init__(self, project, read_asset, parent=None, window_root=None):
        """Render the snapshot and keep controls for context reads/changes."""
        super().__init__(parent)
        self.project = project
        self.read_asset = read_asset
        self.window_root = window_root or project.root
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
        layout.addWidget(self._render(window_root or project.root))

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
        else:
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(4, 4, 4, 4)
            widget = create_control(node, self.read_asset)
            self.widgets[node.id] = widget
            layout.addWidget(widget)
            if isinstance(widget, QPushButton):
                widget.clicked.connect(lambda _, identifier=node.id: self.clicked.emit(identifier))
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
