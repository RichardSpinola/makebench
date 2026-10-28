# SPDX-License-Identifier: GPL-3.0-or-later
"""Detachable Design panels: layers, components, data and properties around the creation area."""

from PySide6.QtCore import QRect, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QToolButton,
    QWidget,
)

from makebench.i18n import tr

from .theme import icon, manager

LAYOUT_KEY = "workspace/design_docks"
LAYOUT_VERSION = 1
LEFT = ("layers", "components", "data")


def panel_titles():
    """Title of each panel, in the order they are built."""
    return {
        "layers": tr("Layers"),
        "components": tr("Components"),
        "data": tr("Data"),
        "properties": tr("Properties"),
    }


class DockTitle(QWidget):
    """Panel header: grip, bold title, then float and close buttons."""

    def __init__(self, dock):
        super().__init__(dock)
        self.dock = dock
        self.setFixedHeight(24)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 4, 0)
        row.setSpacing(4)
        self.grip = QLabel("⋮⋮")
        self.grip.setToolTip(tr("Drag to move"))
        self.title = QLabel(dock.windowTitle())
        bold = QFont(self.title.font())
        bold.setWeight(QFont.Weight.DemiBold)
        self.title.setFont(bold)
        row.addWidget(self.grip)
        row.addWidget(self.title, 1)
        self.float_button = self._button("float", tr("Detach (becomes a floating window)"))
        self.float_button.clicked.connect(lambda: dock.setFloating(not dock.isFloating()))
        self.close_button = self._button("close", tr("Close (reopen in View › Panels)"))
        self.close_button.clicked.connect(dock.close)
        row.addWidget(self.float_button)
        row.addWidget(self.close_button)
        dock.windowTitleChanged.connect(self.title.setText)
        dock.topLevelChanged.connect(self._floating_changed)
        manager().changed.connect(self.restyle)
        self.restyle()

    def _button(self, name, tooltip):
        button = QToolButton(self)
        button.setAutoRaise(True)
        button.setIcon(icon(name))
        button.setProperty("makebenchIcon", name)
        button.setIconSize(QSize(12, 12))
        button.setFixedSize(18, 18)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        return button

    def _floating_changed(self, floating):
        tooltip = tr("Dock it back") if floating else tr("Detach (becomes a floating window)")
        self.float_button.setToolTip(tooltip)
        self.float_button.setAccessibleName(tooltip)

    def restyle(self, *_):
        palette = self.grip.palette()
        palette.setColor(self.grip.foregroundRole(), QColor(manager().tokens["muted"]))
        self.grip.setPalette(palette)
        self.update()

    def paintEvent(self, _event):
        t = manager().tokens
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t["header"]))
        painter.fillRect(QRect(0, self.height() - 1, self.width(), 1), QColor(t["border"]))


class DesignHost(QMainWindow):
    """Inner window of the Design area: the creation area in the middle, panels around it."""

    def __init__(self, central: QWidget, panels: dict):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setObjectName("design_panels")
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
        )
        self.setCentralWidget(central)
        self.docks = {}
        self._parked = []
        for name, title in panel_titles().items():
            dock = QDockWidget(title, self)
            dock.setObjectName(f"{name}_panel")
            dock.setTitleBarWidget(DockTitle(dock))
            dock.setWidget(panels[name])
            dock.setFeatures(
                QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                | QDockWidget.DockWidgetFeature.DockWidgetClosable
            )
            self.docks[name] = dock
        self._arrange()
        self.default_state = self.saveState(LAYOUT_VERSION)
        self.settings = QSettings("Makebench", "Makebench")
        saved = self.settings.value(LAYOUT_KEY)
        if saved:
            self.restoreState(saved, LAYOUT_VERSION)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(self.save_layout)
        for dock in self.docks.values():
            dock.dockLocationChanged.connect(self.save_timer.start)
            dock.topLevelChanged.connect(self.save_timer.start)
            dock.visibilityChanged.connect(self.save_timer.start)

    def _arrange(self):
        """Layers above components on the left, properties on the right."""
        left = Qt.DockWidgetArea.LeftDockWidgetArea
        self.addDockWidget(left, self.docks["layers"])
        self.splitDockWidget(
            self.docks["layers"], self.docks["components"], Qt.Orientation.Vertical
        )
        self.tabifyDockWidget(self.docks["components"], self.docks["data"])
        self.docks["components"].raise_()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.docks["properties"])
        self.resizeDocks(
            [self.docks["layers"], self.docks["properties"]], [230, 280], Qt.Orientation.Horizontal
        )
        self.resizeDocks(
            [self.docks["layers"], self.docks["components"]], [200, 420], Qt.Orientation.Vertical
        )

    def save_layout(self):
        self.settings.setValue(LAYOUT_KEY, self.saveState(LAYOUT_VERSION))

    def restore_layout(self):
        """Dock every panel back in its first place."""
        for dock in self.docks.values():
            dock.setFloating(False)
            dock.show()
        self.restoreState(self.default_state, LAYOUT_VERSION)
        self._arrange()
        self.save_layout()

    def toggle_side(self, side):
        """Show or hide the panels of one side together."""
        names = LEFT if side == "left" else ("properties",)
        docks = [self.docks[n] for n in names]
        visible = any(d.isVisible() for d in docks)
        for dock in docks:
            dock.setVisible(not visible)
        if not visible:
            docks[0 if side == "right" else 1].raise_()

    def showEvent(self, event):
        super().showEvent(event)
        for dock in self._parked:
            dock.show()
        self._parked = []

    def hideEvent(self, event):
        self.save_layout()
        if not event.spontaneous():
            # Floating panels belong to the Design area; they wait for it in other areas.
            self._parked = [d for d in self.docks.values() if d.isFloating() and d.isVisible()]
            for dock in self._parked:
                dock.hide()
            self.save_timer.stop()
        super().hideEvent(event)


def add_panel_menu(window, menu):
    """Add one entry per panel and "Restore layout" to the View menu."""
    panels = menu.addMenu(tr("Panels"))
    for dock in window.design_host.docks.values():
        panels.addAction(dock.toggleViewAction())
    panels.addSeparator()
    restore = panels.addAction(tr("Restore layout"))
    restore.triggered.connect(window.design_host.restore_layout)
    window.restore_layout_action = restore
