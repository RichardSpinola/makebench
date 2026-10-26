# SPDX-License-Identifier: GPL-3.0-or-later
"""The Plugins menu and the window that turns plugins on and off."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from makebench.core.project import Project, ProjectError
from makebench.i18n import tr

from .errors import show_error
from .plugins import PluginManager


def warning() -> str:
    return tr(
        "This plugin runs code on your computer with your permissions. "
        "Turn it on only if you trust where it came from."
    )


def run_command(window, plugin_id: str, index: int) -> None:
    """Run a plugin command as one undoable change; failures only turn that plugin off."""
    manager = window.plugin_manager
    label = manager.plugins[plugin_id].commands[index][0]

    def change():
        result = manager.run_command(plugin_id, index, window.project)
        window.project.__dict__.update(result.__dict__)

    try:
        window._edit(change, label=label)
    except ProjectError as exc:
        show_error(window, exc, tr("Plugin command"))
    rebuild_menu(window)


def rebuild_menu(window) -> None:
    menu = window.plugins_menu
    menu.clear()
    manager = window.plugin_manager
    for plugin in manager.plugins.values():
        for index, (name, _) in enumerate(plugin.commands):
            menu.addAction(name, lambda pid=plugin.id, i=index: run_command(window, pid, i))
    if menu.actions():
        menu.addSeparator()
    menu.addAction(tr("Manage plugins…"), lambda: PluginsDialog(window).exec())
    from .pieces import rebuild_menu as rebuild_pieces

    if hasattr(window, "pieces_menu"):
        rebuild_pieces(window)


def ask_enable(parent) -> bool:
    return (
        QMessageBox.warning(
            parent,
            tr("Turn on plugin"),
            warning(),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        == QMessageBox.StandardButton.Ok
    )


class PluginsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window_ref = window
        self.manager = window.plugin_manager
        self.setWindowTitle(tr("Plugins"))
        self.resize(520, 460)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Plugins are off until you turn them on.") + " " + warning()))
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._show_details)
        layout.addWidget(self.list)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(110)
        layout.addWidget(self.details)
        self.toggle = QPushButton()
        self.toggle.clicked.connect(self._toggle)
        layout.addWidget(self.toggle)
        for text, slot in (
            (tr("Install from a folder…"), self._install),
            (tr("Open plugins folder"), self._open_folder),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            layout.addWidget(button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._fill()

    def _fill(self):
        self.manager.scan()
        self.list.clear()
        for plugin in self.manager.plugins.values():
            state = tr("on") if plugin.enabled else tr("off")
            item = QListWidgetItem(f"{plugin.name} {plugin.version} · {state}")
            item.setData(256, plugin.id)
            self.list.addItem(item)
        self._show_details()

    def _current(self):
        item = self.list.currentItem()
        return self.manager.plugins.get(item.data(256)) if item else None

    def _show_details(self, *_):
        plugin = self._current()
        self.toggle.setEnabled(bool(plugin) and not plugin.incompatible)
        if plugin is None:
            self.toggle.setText(tr("Turn on"))
            self.details.setPlainText("")
            return
        self.toggle.setText(tr("Turn off") if plugin.enabled else tr("Turn on"))
        lines = [plugin.description, plugin.author]
        if plugin.error:
            lines.append(tr("Problem:") + " " + plugin.error)
        self.details.setPlainText("\n".join(line for line in lines if line))

    def _toggle(self):
        plugin = self._current()
        if plugin is None:
            return
        if plugin.enabled:
            self.manager.disable(plugin.id)
        elif ask_enable(self):
            self.manager.enable(plugin.id)
        rebuild_menu(self.window_ref)
        self._fill()

    def _install(self):
        folder = QFileDialog.getExistingDirectory(self, tr("Choose the plugin folder"))
        if not folder:
            return
        try:
            self.manager.install_from(Path(folder))
        except (ProjectError, OSError) as exc:
            show_error(self, exc, tr("Install plugin"))
        self._fill()

    def _open_folder(self):
        self.manager.folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.manager.folder)))


def install_plugins(window, menubar_before=None) -> None:
    """Create the Plugins menu and load the plugins the person already turned on."""
    window.plugin_manager = PluginManager()
    window.plugin_manager.load_enabled()
    window.plugins_menu = QMenu(tr("&Plugins"), window)
    if menubar_before is not None:
        window.menuBar().insertMenu(menubar_before, window.plugins_menu)
    else:
        window.menuBar().addMenu(window.plugins_menu)
    rebuild_menu(window)
