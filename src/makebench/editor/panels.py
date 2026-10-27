# SPDX-License-Identifier: GPL-3.0-or-later
"""Detachable Design panels: layers, components, data and properties around the creation area."""

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QDockWidget, QMainWindow, QWidget

from makebench.i18n import tr

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
        for name, title in panel_titles().items():
            dock = QDockWidget(title, self)
            dock.setObjectName(f"{name}_panel")
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

    def hideEvent(self, event):
        self.save_layout()
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
