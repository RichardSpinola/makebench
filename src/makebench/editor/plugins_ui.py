# SPDX-License-Identifier: GPL-3.0-or-later
"""The Plugins menu and the window that turns plugins on and off."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from makebench.core.project import ProjectError
from makebench.i18n import tr

from makebench.core import plugin_scan
from .errors import show_error
from .look import button_row, empty_hint, header, make_muted
from .plugins import CommandContext, PluginManager


def warning() -> str:
    return tr(
        "This plugin runs code on your computer with your permissions. "
        "Turn it on only if you trust where it came from."
    )


def run_command(window, plugin_id: str, index: int) -> None:
    """Run a plugin command as one undoable change; failures only turn that plugin off."""
    manager = window.plugin_manager
    label = manager.plugins[plugin_id].commands[index][0]
    context = CommandContext(
        window=getattr(window, "active_window", window.project.root.id),
        parent=window,
        read_asset=window.assets.read,
        import_image=window.assets.import_image,
    )
    try:
        result = manager.run_command(plugin_id, index, window.project, context)
        # A command that changed nothing (a cancelled dialog) leaves no step in the history.
        if result.to_dict() != window.project.to_dict():
            window._edit(lambda: window.project.__dict__.update(result.__dict__), label=label)
    except ProjectError as exc:
        show_error(window, exc, tr("Plugin command"))
    rebuild_menu(window)


def template_models(window) -> list[tuple[str, str, str]]:
    """The built-in templates followed by those of the plugins that are on."""
    from makebench.core.templates import MODELS

    manager = getattr(window, "plugin_manager", None)
    return MODELS + (manager.templates() if manager else [])


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
    menu.addAction(tr("Themes…"), lambda: open_themes(window))
    from .pieces import rebuild_menu as rebuild_pieces

    if hasattr(window, "pieces_menu"):
        rebuild_pieces(window)
    if hasattr(window, "fill_home_models"):
        window.fill_home_models()


def open_themes(window) -> None:
    from .themes_ui import ThemesDialog

    ThemesDialog(window).exec()


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
        self.resize(600, 460)
        layout = QVBoxLayout(self)
        layout.addWidget(
            header(tr("Plugins"), tr("Plugins are off until you turn them on.") + " " + warning())
        )
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._show_details)
        empty_hint(
            self.list,
            tr("No plugins installed. Use Install from a folder… to add one."),
        )
        layout.addWidget(self.list, 2)
        self.details = make_muted(QLabel())
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.details.setMinimumHeight(48)
        layout.addWidget(self.details)
        self.toggle = QPushButton()
        self.toggle.clicked.connect(self._toggle)
        install = QPushButton(tr("Install from a folder…"))
        install.clicked.connect(self._install)
        folder = QPushButton(tr("Open plugins folder"))
        folder.clicked.connect(self._open_folder)
        layout.addLayout(button_row(self.toggle, trailing=[install, folder]))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._fill()

    def _fill(self):
        self.manager.scan()
        self.list.clear()
        for plugin in self.manager.plugins.values():
            state = tr("on") if plugin.enabled else tr("off")
            label = f"{plugin.name} {plugin.version} · {state}"
            if plugin.official:
                label += " · " + tr("Official")
            item = QListWidgetItem(label)
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
            self.details.setText(tr("Select a plugin to see what it does."))
            return
        self.toggle.setText(tr("Turn off") if plugin.enabled else tr("Turn on"))
        lines = [plugin.description, plugin.author]
        if plugin.official:
            lines.append(tr("Ships with Makebench. Its code is also an example of a plugin."))
        if plugin.license:
            lines.append(tr("License:") + " " + plugin.license)
        if plugin.source:
            lines.append(tr("Source:") + " " + plugin.source)
        if plugin.detected:
            lines.append(
                tr("Its code can: {list}.").format(
                    list="; ".join(plugin_scan.describe(plugin.detected)).lower()
                )
            )
        hidden = sorted(set(plugin.detected) - set(plugin.declared))
        if hidden and not plugin.official:
            lines.append(
                tr(
                    "Not declared in plugin.json: {list}. Turn it on only if you trust the author."
                ).format(list=", ".join(hidden))
            )
        if plugin.fingerprint:
            lines.append(tr("Fingerprint (SHA-256):") + " " + plugin.fingerprint[:16])
        if plugin.error:
            lines.append(tr("Problem:") + " " + plugin.error)
        self.details.setText("\n".join(line for line in lines if line))

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
