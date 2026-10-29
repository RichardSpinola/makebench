# SPDX-License-Identifier: GPL-3.0-or-later
"""Start page, local projects, recents, recovery and portable sharing."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import unicodedata

from PySide6.QtCore import Qt, QStandardPaths
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QComboBox,
)
from makebench.core.project import Project, ProjectError
from makebench.core.storage import load_project, save_project
from makebench.core.source import SourceBuffer
from makebench.core.bundle import read_bundle, write_bundle
from .assets import AssetStore
from .look import make_muted, make_title
from makebench.i18n import language, tr
from makebench.i18n import ntr


def slug(text):
    """Produce a simple folder name, never using text as an arbitrary path."""
    clean = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", clean).strip("-") or "my-application"


class ProjectMixin:
    """Keep file operations independent of running the application."""

    def project_dialog_parent(self):
        """Keep selectors and messages above the launcher while the workbench is hidden."""
        startup = getattr(self, "startup_dialog", None)
        return startup if startup and startup.isVisible() else self

    def install_projects(self):
        """Build the start page and commands without replacing a project opened by argument."""
        from PySide6.QtWidgets import QGridLayout, QToolButton, QScrollArea, QFrame, QSizePolicy
        from PySide6.QtCore import QSize
        from .theme import icon

        from .startup import (
            CONTENT_WIDTH,
            HomeBackground,
            HomeHero,
            HomeTile,
            LauncherDelegate,
            style_home,
            show_startup,
            tips,
        )

        home = HomeBackground()
        home.setObjectName("home")
        page = QVBoxLayout(home)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        page.addWidget(HomeHero(self.settings))
        outer = QVBoxLayout()
        outer.setContentsMargins(32, 20, 32, 18)
        page.addLayout(outer, 1)
        content = QWidget()
        content.setMaximumWidth(CONTENT_WIDTH)
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.home_tiles = []
        for symbol, label, detail, callback in [
            (
                "new",
                tr("New…"),
                tr("Start from a template"),
                lambda: self.new_project_dialog("blank"),
            ),
            ("open", tr("Open project…"), tr("Continue a saved project"), self.open_project),
            (
                "document",
                tr("Open example…"),
                tr("A ready app to learn from"),
                self.open_example_dialog,
            ),
            (
                "history",
                tr("Download from Git…"),
                tr("A shared project, with history"),
                self.clone_project_dialog,
            ),
        ]:
            tile = HomeTile(symbol, label, detail)
            tile.clicked.connect(callback)
            tiles.addWidget(tile)
            self.home_tiles.append(tile)
        body.addLayout(tiles)
        self.recovery_row = QFrame()
        self.recovery_row.setObjectName("home_recovery")
        rr = QHBoxLayout(self.recovery_row)
        rr.setContentsMargins(12, 6, 6, 6)
        self.home_recovery_label = QLabel(tr("Previous session available."))
        rr.addWidget(self.home_recovery_label, 1)
        recover = QPushButton(tr("Recover"))
        recover.clicked.connect(self.recover_latest)
        rr.addWidget(recover)
        discard = QToolButton()
        discard.setIcon(icon("close"))
        discard.setAutoRaise(True)
        discard.setToolTip(tr("Discard recovery"))
        discard.setAccessibleName(tr("Discard recovery"))
        discard.clicked.connect(self.discard_recovery)
        rr.addWidget(discard)
        body.addWidget(self.recovery_row)

        def card(heading_widgets):
            frame = QFrame()
            frame.setObjectName("home_card")
            box = QVBoxLayout(frame)
            box.setContentsMargins(0, 0, 0, 6)
            box.setSpacing(0)
            top = QHBoxLayout()
            top.setContentsMargins(14, 8, 8, 8)
            for widget in heading_widgets:
                top.addWidget(widget)
            box.addLayout(top)
            rule = QFrame()
            rule.setObjectName("home_card_rule")
            rule.setFixedHeight(1)
            box.addWidget(rule)
            return frame, box

        def heading(text):
            label = QLabel(text)
            font = label.font()
            font.setWeight(font.Weight.DemiBold)
            label.setFont(font)
            return label

        self.recent_search = QLineEdit()
        self.recent_search.setPlaceholderText(tr("Search projects…"))
        self.recent_search.setClearButtonEnabled(True)
        self.recent_search.setMinimumWidth(200)
        self.recent_search.setMaximumWidth(260)
        self.recent_search.textChanged.connect(self.filter_recents)
        recent_card, recent_box = card([heading(tr("Recent")), QWidget(), self.recent_search])
        recent_card.layout().itemAt(0).layout().setStretch(1, 1)
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("recent_list")
        self.recent_list.setFrameShape(QFrame.Shape.NoFrame)
        self.recent_list.setAccessibleName(tr("Recent projects"))
        self.recent_list.setItemDelegate(LauncherDelegate(self.recent_list))
        self.recent_list.setMouseTracking(True)
        self.recent_list.itemActivated.connect(self.open_recent)
        self.recent_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recent_list.customContextMenuRequested.connect(self.recent_context)
        recent_box.addWidget(self.recent_list, 1)
        self.no_recents = make_muted(
            QLabel(
                tr("No recent projects.")
                + " "
                + tr("Create a new one or open an example to get started.")
            )
        )
        self.no_recents.setWordWrap(True)
        self.no_recents.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_recents.setContentsMargins(16, 24, 16, 24)
        recent_box.addWidget(self.no_recents)
        recent_box.addStretch()
        self.recent_actions = QWidget()
        actions = QHBoxLayout(self.recent_actions)
        actions.setContentsMargins(8, 4, 8, 0)
        actions.setSpacing(2)
        actions.addStretch()
        for symbol, label, callback in [
            ("open", tr("Open"), lambda: self.open_recent(self.recent_list.currentItem())),
            ("search", tr("Locate…"), self.locate_recent),
            ("remove", tr("Remove from list"), self.remove_recent),
            ("trash", tr("Move to trash…"), self.trash_recent),
        ]:
            button = QToolButton()
            button.setIcon(icon(symbol))
            button.setText(label)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setAutoRaise(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.clicked.connect(callback)
            actions.addWidget(button)
        recent_box.addWidget(self.recent_actions)
        models_card, models_box = card([heading(tr("New from template"))])
        self.home_models = QListWidget()
        self.home_models.setFrameShape(QFrame.Shape.NoFrame)
        self.home_models.setAccessibleName(tr("Templates"))
        self.home_models.setItemDelegate(LauncherDelegate(self.home_models))
        self.home_models.setMouseTracking(True)
        self.fill_home_models()
        self.home_models.itemActivated.connect(
            lambda item: self.new_project_dialog(item.data(Qt.ItemDataRole.UserRole))
        )
        models_box.addWidget(self.home_models, 1)
        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(recent_card, 3)
        columns.addWidget(models_card, 2)
        body.addLayout(columns, 1)
        center = QHBoxLayout()
        center.addStretch()
        center.addWidget(content, 1)
        center.addStretch()
        outer.addLayout(center, 1)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 10, 0, 0)
        hints = tips()
        self.home_tip = QLabel(
            f"<b>{tr('Tip:')}</b> "
            + hints[self.settings.value("v1/projects/tip", 0, type=int) % len(hints)]
        )
        self.home_tip.setObjectName("home_tip")
        self.home_tip.setWordWrap(True)
        bottom.addWidget(self.home_tip, 1)
        self.show_startup_button = QToolButton()
        self.show_startup_button.setText(tr("Show the start window"))
        self.show_startup_button.setIcon(icon("start-window"))
        self.show_startup_button.setProperty("makebenchIcon", "start-window")
        self.show_startup_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.show_startup_button.setAutoRaise(True)
        self.show_startup_button.clicked.connect(lambda: show_startup(self))
        bottom.addWidget(self.show_startup_button)
        outer.addLayout(bottom)
        from .theme import manager as theme_manager

        import shiboken6

        # The theme manager outlives windows: skip a home page that is already deleted.
        theme_manager().changed.connect(lambda *_: shiboken6.isValid(home) and style_home(self))
        self.home_page = home
        self.pages.addWidget(home)
        style_home(self)
        self.new_action.triggered.disconnect()
        self.new_action.triggered.connect(lambda: self.new_project_dialog("blank"))
        menu = self.menuBar().actions()[0].menu()
        menu.addSeparator()
        share = menu.addAction(tr("Share project…"))
        share.triggered.connect(self.share_project)
        self.clone_action = menu.addAction(tr("Download from Git…"))
        self.clone_action.triggered.connect(self.clone_project_dialog)
        self.startup_action = menu.addAction(tr("Start window…"))
        self.startup_action.triggered.connect(lambda: show_startup(self))
        self.refresh_recents()
        self.refresh_recovery()
        from PySide6.QtCore import QFileSystemWatcher

        self.source_watcher = QFileSystemWatcher(self)
        self.source_watcher.fileChanged.connect(self.source_changed_externally)
        self.watch_source()
        self.pages.currentChanged.connect(lambda _: self._update_actions())
        from .shell import sync_status_items

        self.pages.currentChanged.connect(lambda _: sync_status_items(self))
        self.external_change_row = QWidget()
        row = QHBoxLayout(self.external_change_row)
        row.addWidget(QLabel(tr("Functions changed outside Makebench.")), 1)
        reload = QPushButton(tr("Reload file"))
        reload.clicked.connect(self.reload_source)
        row.addWidget(reload)
        keep = QPushButton(tr("Keep my version"))
        keep.clicked.connect(self.keep_source)
        row.addWidget(keep)
        self.editor_page.layout().insertWidget(1, self.external_change_row)
        self.external_change_row.hide()
        self.trust_row = QWidget()
        trust_layout = QHBoxLayout(self.trust_row)
        self.trust_label = QLabel()
        self.trust_label.setWordWrap(True)
        trust_layout.addWidget(self.trust_label, 1)
        review = QPushButton(tr("Review code"))
        review.clicked.connect(lambda: self.set_mode("code"))
        trust_layout.addWidget(review)
        trust = QPushButton(tr("Trust and continue"))
        trust.clicked.connect(lambda: (self.trust_project(), self.refresh_trust_banner()))
        trust_layout.addWidget(trust)
        self.editor_page.layout().insertWidget(1, self.trust_row)
        self.trust_row.hide()
        self.refresh_trust_banner()
        self.programming_row = QWidget()
        programming_layout = QHBoxLayout(self.programming_row)
        programming_label = QLabel(
            tr("How will you program this project? Blocks can be converted to Python later.")
        )
        programming_label.setWordWrap(True)
        programming_layout.addWidget(programming_label, 1)
        for kind, text in (("blocks", tr("Blocks")), ("python", tr("Python"))):
            button = QPushButton(text)
            button.setObjectName("choose_programming_" + kind)
            button.clicked.connect(lambda _=False, k=kind: self.choose_programming(k))
            programming_layout.addWidget(button)
        self.editor_page.layout().insertWidget(1, self.programming_row)
        self.programming_row.hide()

    def reload_source(self):
        """Reload by explicit choice, without importing the Python file."""
        if not self.path:
            return
        if self.source.path and not self.source.path.exists():
            self.statusBar().showMessage(
                tr("The file was removed. Your edits remain here; use Keep my version or Save As."),
                10000,
            )
            return
        try:
            self._trusted_session = False
            self.source = SourceBuffer.load(self.path)
            self.source_editor.blockSignals(True)
            self.source_editor.setPlainText(self.source.text)
            self.source_editor.blockSignals(False)
            self.external_change_row.hide()
            self._update_code()
            self._update_actions()
            self.watch_source()
        except (OSError, ProjectError) as exc:
            self._show_error(exc, tr("Could not reload the file"))

    def keep_source(self):
        """Allow keeping the current buffer; the next write stays explicit."""
        if self.source.path:
            try:
                self.source.original = (
                    self.source.path.read_bytes() if self.source.path.exists() else None
                )
            except OSError as exc:
                self._show_error(exc, tr("Could not keep your version"))
                return
        self.external_change_row.hide()
        self.watch_source()
        self.refresh_trust_banner()

    def show_home(self, compact=False):
        """Show the start page without discarding or running the document being edited."""
        if not self._finish_field_edit():
            return
        self.refresh_recents()
        self.refresh_recovery()
        self.pages.setCurrentWidget(self.home_page)
        self.workspace_toolbar.show()
        if compact:
            self._compact_home = True
            self.setMinimumSize(680, 420)
            self.resize(820, 500)

    def refresh_recents(self):
        """Show real paths and flag documents that were moved or removed."""
        self.recent_list.clear()
        paths = self.settings.value("projects/recent", [], type=list)
        from .theme import icon
        from PySide6.QtCore import QSize

        from .startup import DETAIL_ROLE, SWATCH_ROLE, SWATCHES, short_path, when
        import zlib

        for value in paths[:20]:
            path = Path(value)
            found = path.is_file()
            detail = short_path(path.parent) + " · "
            detail += when(path.stat().st_mtime) if found else tr("Not found")
            item = QListWidgetItem(path.parent.name)
            item.setData(DETAIL_ROLE, detail)
            item.setData(
                SWATCH_ROLE,
                SWATCHES[zlib.crc32(str(path).encode()) % len(SWATCHES)] if found else "#777777",
            )
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.recent_list.addItem(item)
        count = self.recent_list.count()
        self.recent_list.setVisible(count > 0)
        if hasattr(self, "no_recents"):
            self.no_recents.setVisible(count == 0)
            self.recent_actions.setVisible(count > 0)
        self.filter_recents()

    def filter_recents(self):
        """Filter locally without removing files or list references."""
        query = self.recent_search.text().casefold() if hasattr(self, "recent_search") else ""
        for index in range(self.recent_list.count()):
            item = self.recent_list.item(index)
            text = f"{item.text()} {item.data(Qt.ItemDataRole.UserRole + 1) or ''} {item.toolTip()}"
            item.setHidden(query not in text.casefold())

    def recent_context(self, point):
        """The project menu separates opening, locating, removing the reference and trash."""
        item = self.recent_list.itemAt(point)
        if not item:
            return
        self.recent_list.setCurrentItem(item)
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        menu = QMenu(self)
        menu.addAction(tr("Open"), lambda: self.open_recent(item))
        menu.addAction(
            tr("Open folder"),
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(Path(item.data(Qt.ItemDataRole.UserRole)).parent))
            ),
        )
        menu.addAction(tr("Locate…"), self.locate_recent)
        menu.addSeparator()
        menu.addAction(tr("Remove from recents"), self.remove_recent)
        menu.addAction(tr("Move to trash…"), self.trash_recent)
        menu.exec(self.recent_list.viewport().mapToGlobal(point))

    def trash_recent(self):
        """Offer a recoverable trash; never deletes folders silently."""
        item = self.recent_list.currentItem()
        if not item:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        if not path.is_file():
            self.remove_recent()
            return
        if self.runtime_window and not self.runtime_window.session.closed:
            self.statusBar().showMessage(
                tr("Stop the test before moving a project to the trash."), 6000
            )
            return
        if self.path == path and not self._confirm_discard():
            return
        from PySide6.QtWidgets import QCheckBox
        from makebench.core.source import source_path

        dialog = QDialog(self.project_dialog_parent())
        dialog.setWindowTitle(tr("Move project to trash"))
        layout = QVBoxLayout(dialog)
        caption = QLabel(tr("Move these files to the trash?"))
        layout.addWidget(caption)
        paths = [path]
        own = source_path(path)
        if own.exists():
            paths.append(own)
        listing = QLabel("\n".join(str(p) for p in paths))
        listing.setTextFormat(Qt.TextFormat.PlainText)
        listing.setWordWrap(True)
        layout.addWidget(listing)
        folder = QCheckBox(tr("Include the whole project folder and its contents"))
        layout.addWidget(folder)
        safe = path.parent.resolve() not in {
            Path.home().resolve(),
            Path("/"),
            Path(
                self.settings.value(
                    "v1/projects/folder", str(Path.home() / "Makebench" / "Projects")
                )
            ).resolve(),
        }
        folder.setEnabled(safe)
        folder.setToolTip(
            tr(
                "The whole folder is included only if you check this option. Images stay when only the files are moved."
            )
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Move to trash"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.move_project_to_trash(path, whole_folder=folder.isChecked())

    def move_project_to_trash(self, path, whole_folder=False):
        """Move only the chosen set; a failure never becomes a permanent deletion."""
        from PySide6.QtCore import QFile
        from makebench.core.source import source_path

        path = Path(path)
        if whole_folder and path.parent.resolve() in {
            Path.home().resolve(),
            Path("/"),
            Path(
                self.settings.value(
                    "v1/projects/folder", str(Path.home() / "Makebench" / "Projects")
                )
            ).resolve(),
        }:
            self._show_error(tr("This folder cannot be moved as a whole project."))
            return False
        targets = (
            [path.parent] if whole_folder else [p for p in (source_path(path), path) if p.exists()]
        )
        moved = []
        for target in targets:
            result = QFile.moveToTrash(str(target))
            ok = result[0] if isinstance(result, tuple) else result
            if not ok:
                self._show_error(
                    tr("Could not move to trash: {path}").format(path=target)
                    + "\n"
                    + tr("Already moved: {items}").format(items=", ".join(moved) or tr("none"))
                )
                return False
            moved.append(str(target))
        recent = self.settings.value("projects/recent", [], type=list)
        self.settings.setValue("projects/recent", [p for p in recent if p != str(path)])
        self.refresh_recents()
        if self.path == path:
            self._replace_project(Project.empty(), None)
            self.show_home()
        self.statusBar().showMessage(tr("Project moved to the trash."), 6000)
        return True

    def remember_project(self):
        """Add the path to the top of the recents after a successful open or save."""
        if self.path:
            paths = self.settings.value("projects/recent", [], type=list)
            paths = [str(self.path), *[p for p in paths if p != str(self.path)]]
            self.settings.setValue("projects/recent", paths[:20])
            self.refresh_recents()
            if getattr(self, "_trusted_session", False):
                self.trust_project()
        self.watch_source()
        self.refresh_trust_banner()

    def open_recent(self, item):
        """Open an existing recent without destroying the current project on error."""
        if not item:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        if not path.is_file():
            self.statusBar().showMessage(
                tr("Project not found. Use Locate or remove it from the list."), 6000
            )
            return
        if not self._confirm_discard():
            return
        try:
            self._replace_project(load_project(path), path)
            self.pages.setCurrentWidget(self.editor_page)
            self.workspace_toolbar.show()
        except (OSError, ProjectError) as exc:
            self._show_error(exc, tr("Could not open the project"))

    def locate_recent(self):
        """Replace only the selected entry; never moves the user's files."""
        item = self.recent_list.currentItem()
        if not item:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, tr("Locate project"), "", tr("Makebench projects (*.makebench.json)")
        )
        if not filename:
            return
        try:
            load_project(filename)
        except ProjectError as exc:
            self._show_error(exc, tr("Could not locate the project"))
            return
        paths = self.settings.value("projects/recent", [], type=list)
        old = item.data(Qt.ItemDataRole.UserRole)
        self.settings.setValue("projects/recent", [filename if p == old else p for p in paths])
        self.refresh_recents()

    def remove_recent(self):
        """Remove the shortcut without deleting the project on disk."""
        item = self.recent_list.currentItem()
        if item:
            self.settings.setValue(
                "projects/recent",
                [
                    p
                    for p in self.settings.value("projects/recent", [], type=list)
                    if p != item.data(Qt.ItemDataRole.UserRole)
                ],
            )
            self.refresh_recents()

    def fill_home_models(self):
        """List the templates on the home page, plugin templates included."""
        from .plugins_ui import template_models
        from .startup import SYMBOL_ROLE, model_icon

        if not hasattr(self, "home_models"):
            return
        self.home_models.clear()
        for key, label, description in template_models(self):
            item = QListWidgetItem(label)
            item.setData(SYMBOL_ROLE, model_icon(key))
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setData(Qt.ItemDataRole.UserRole + 1, description)
            self.home_models.addItem(item)

    def new_project_dialog(self, template="blank"):
        """Create a folder only after validating the name, destination and pending changes."""
        from .plugins_ui import template_models
        from makebench.core.environment import gtk_support
        from .theme import manager
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QIcon

        dialog = QDialog(self.project_dialog_parent())
        dialog.setWindowTitle(tr("New project"))
        dialog.setFixedWidth(560)
        form = QFormLayout(dialog)
        model = QComboBox()
        models = template_models(self)
        for key, label, description in models:
            model.addItem(label, key)
        model.setCurrentIndex(max(0, model.findData(template)))
        form.addRow(tr("Template"), model)
        about = QLabel()
        about.setWordWrap(True)
        about.setEnabled(False)
        descriptions = {key: description for key, _, description in models}
        model.currentIndexChanged.connect(
            lambda _: about.setText(descriptions.get(model.currentData(), ""))
        )
        about.setText(descriptions.get(model.currentData(), ""))
        form.addRow(about)
        from PySide6.QtWidgets import QButtonGroup, QRadioButton, QVBoxLayout

        programming = QButtonGroup(dialog)
        programming_box = QWidget()
        choices = QVBoxLayout(programming_box)
        choices.setContentsMargins(0, 0, 0, 0)
        preferred_programming = self.settings.value("v1/projects/programming", "blocks")
        for kind, title, sentence in (
            ("blocks", tr("Blocks"), tr("Snap pieces together, no typing code.")),
            ("python", tr("Python"), tr("Write the code, with help from the editor.")),
        ):
            option = QRadioButton(title)
            option.setObjectName("new_project_programming_" + kind)
            option.setChecked(kind == preferred_programming)
            programming.addButton(option)
            option.setProperty("programming", kind)
            choices.addWidget(option)
            hint = QLabel(sentence)
            hint.setWordWrap(True)
            hint.setIndent(24)
            make_muted(hint)
            choices.addWidget(hint)
        if programming.checkedButton() is None:
            programming.buttons()[0].setChecked(True)
        form.addRow(tr("Program with"), programming_box)
        backend = QComboBox()
        backend.addItem(tr("GTK — Adwaita look"), "gtk")
        backend.addItem(tr("Qt — desktop controls"), "qt")
        supported = gtk_support()["gtk4"]
        preferred = self.settings.value("v1/projects/backend", "gtk" if supported else "qt")
        backend.setCurrentIndex(backend.findData(preferred if supported else "qt"))
        form.addRow(tr("Application look"), backend)
        if not supported:
            note = QLabel(tr("GTK4 not available; Qt selected."))
            form.addRow(note)
        name = QLineEdit(tr("My application"))
        form.addRow(tr("Name"), name)
        folder = QLineEdit(
            str(
                Path(
                    self.settings.value(
                        "v1/projects/folder", str(Path.home() / "Makebench" / "Projects")
                    )
                )
                / "my-application"
            )
        )
        folder_row = QWidget()
        row = QHBoxLayout(folder_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(folder)
        choose = QPushButton(tr("Choose…"))
        row.addWidget(choose)

        def choose_folder():
            """Receive a folder choice without creating or changing files."""
            value = QFileDialog.getExistingDirectory(
                dialog, tr("Folder for the new project"), folder.text()
            )
            if value:
                folder.setText(value)

        choose.clicked.connect(choose_folder)
        form.addRow(tr("Folder"), folder_row)
        name.textEdited.connect(
            lambda text: folder.setText(str(Path(folder.text()).parent / slug(text)))
        )
        info = QLabel(tr("A folder will be created with the project, its functions and images."))
        info.setWordWrap(True)
        form.addRow(info)
        identifier = QLineEdit("com.example.myapplication")
        identifier.setPlaceholderText("com.example.myapp")
        identifier.setObjectName("new_application_id")
        form.addRow(tr("Identifier"), identifier)
        version = QLineEdit("0.1.0")
        version.setObjectName("new_application_version")
        form.addRow(tr("Version"), version)

        def suggest_identifier(text):
            """Suggest an editable identifier, never replacing a choice the user made."""
            if not identifier.isModified():
                identifier.setText("com.example.app_" + slug(text).replace("-", "_"))

        name.textEdited.connect(suggest_identifier)
        icon_path = QLineEdit()
        icon_path.setReadOnly(True)
        icon_path.setPlaceholderText(tr("Choose later"))
        icon_path.setObjectName("new_application_icon")
        icon_row = QWidget()
        icons = QHBoxLayout(icon_row)
        icons.setContentsMargins(0, 0, 0, 0)
        icons.addWidget(icon_path)
        choose_icon = QPushButton(tr("Choose…"))
        icons.addWidget(choose_icon)

        def select_icon():
            """The icon is copied as an asset only when creation is confirmed."""
            filename, _ = QFileDialog.getOpenFileName(
                dialog, tr("Application icon"), "", tr("Icons (*.png *.svg)")
            )
            if filename:
                icon_path.setText(filename)

        choose_icon.clicked.connect(select_icon)
        form.addRow(tr("Icon"), icon_row)
        advanced_rows = [identifier, version, icon_row]
        more = QCheckBox(tr("Show advanced options (identifier, version, icon)"))
        more.setObjectName("new_project_advanced")

        def show_advanced(on):
            """Keep the first steps short: name, template and look come first."""
            for widget in advanced_rows:
                form.setRowVisible(widget, on)
            dialog.setMinimumHeight(0)
            dialog.setMaximumHeight(16777215)
            dialog.setFixedHeight(dialog.sizeHint().height())

        more.toggled.connect(show_advanced)
        form.insertRow(form.getWidgetPosition(identifier)[0], more)
        show_advanced(False)
        name.setObjectName("new_application_name")
        folder.setObjectName("new_project_folder")
        backend.setObjectName("new_application_backend")
        model.setObjectName("new_project_model")
        error = QLabel()
        error.setWordWrap(True)
        error.setMinimumHeight(error.fontMetrics().height() * 2)
        form.addRow(error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Create project"))
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        def create():
            """Create the requested item with the dialog's validated values."""
            destination = Path(folder.text()).expanduser()
            if not name.text().strip():
                error.setText(tr("Enter a name for the project."))
                return
            if not re.fullmatch(
                r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_-]*){2,}", identifier.text().strip()
            ):
                more.setChecked(True)
                error.setText(tr("Use an identifier such as com.example.myapp."))
                return
            if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version.text().strip()):
                more.setChecked(True)
                error.setText(tr("Enter the version, for example 0.1.0."))
                return
            if destination.exists() and any(destination.iterdir()):
                error.setText(tr("Choose a new or empty folder."))
                return
            if not self._confirm_discard():
                return
            try:
                project, source, assets = self.project_template(
                    model.currentData(), name.text().strip()
                )
                project.application.update(
                    backend=backend.currentData(),
                    name=name.text().strip(),
                    version=version.text().strip(),
                    language=language(),
                )
                used = self.settings.value("projects/templates/recent", [], type=list)
                self.settings.setValue(
                    "projects/templates/recent",
                    [model.currentData(), *[key for key in used if key != model.currentData()]][:5],
                )
                chosen = programming.checkedButton().property("programming")
                if chosen == "python" and project.workflows:
                    from makebench.core.codegen import convert_to_python

                    source = convert_to_python(project, source)
                project.metadata["programming"] = chosen
                self.settings.setValue("v1/projects/programming", chosen)
                if identifier.text().strip():
                    project.application["id"] = identifier.text().strip()
                if icon_path.text():
                    project.application["icon"] = assets.import_image(Path(icon_path.text()))
                destination.mkdir(parents=True, exist_ok=True)
                self._replace_project(project, None)
                self.source.text = source
                self.source_editor.setPlainText(source)
                self.assets = assets
                if not self.save_to(destination / "project.makebench.json"):
                    return
                self._created_here = True
                self.trust_project()
                self.set_mode("map")
                dialog.accept()
                from .guide import show_guide

                show_guide(self, automatic=True)
            except (OSError, ProjectError) as exc:
                error.setText(str(exc))

        buttons.accepted.connect(create)
        dialog.setFixedHeight(dialog.sizeHint().height())
        dialog.exec()

    def project_template(self, key, name):
        """Copy the shipped templates, keeping the original examples intact."""
        if key.startswith("plugin:"):
            return self.plugin_manager.make_template(key, name), SourceBuffer().text, AssetStore()
        if key != "tasks":
            from makebench.core.templates import make_template

            project = make_template(key, name)
            if key == "blank":
                project.metadata["empty_map"] = True
            return project, SourceBuffer().text, AssetStore()
        # The task-center template exists in each interface language.
        portuguese = language() == "pt_BR"
        root = (
            Path(__file__).resolve().parents[3]
            / "examples"
            / ("script-center" if portuguese else "en/script-center")
        )
        if not (root / "app.makebench.json").is_file():
            root = (
                Path(__file__).resolve().parent.parent
                / "templates"
                / ("script-center.pt_BR" if portuguese else "script-center")
            )
        project = load_project(root / "app.makebench.json")
        from makebench.core.project import new_id

        project.id = new_id("project")
        project.name = name
        project.root.properties["title"] = name
        return project, SourceBuffer.load(root / "app.makebench.json").text, AssetStore(root)

    def available_examples(self):
        """Examples shipped with the source tree or the editor AppImage, in the interface language.

        Returns [(title, folder, project file name)]; empty when the editor was installed
        without the examples (for example from a wheel).
        """
        package = Path(__file__).resolve().parents[1]
        for base in (package.parents[1] / "examples", package.parent / "examples"):
            if base.is_dir():
                break
        else:
            return []
        if language() != "pt_BR" and (base / "en").is_dir():
            base = base / "en"
        catalog = [
            (
                tr("Welcome wizard — states and two windows"),
                "welcome-states",
                "project.makebench.json",
            ),
            (
                tr("Task center — tasks, questions and live output"),
                "script-center",
                "app.makebench.json",
            ),
            (
                tr("Terminal and debugging — breakpoints, step by step"),
                "terminal-debug",
                "qt.makebench.json",
            ),
            (tr("Python modules — several files"), "python-modules/qt", "project.makebench.json"),
            (
                tr("Complete workshop — every component, logic in blocks"),
                "full-blocks",
                "project.makebench.json",
            ),
        ]
        twins = [
            (tr("{title} · Python").format(title=title), folder + "-python", name)
            for title, folder, name in catalog[:3]
        ]
        catalog[3:3] = twins
        return [
            (title, base / folder, name)
            for title, folder, name in catalog
            if (base / folder / name).is_file()
        ]

    def clone_project_dialog(self):
        """Download a project from Git and open it, like Open project."""
        from .clone import CloneDialog

        if not self._confirm_discard():
            return
        dialog = CloneDialog(self.project_dialog_parent(), self.settings)
        if not dialog.exec() or not dialog.project_path:
            return
        try:
            self._replace_project(load_project(dialog.project_path), dialog.project_path)
            self.pages.setCurrentWidget(self.editor_page)
            self.workspace_toolbar.show()
        except (OSError, ProjectError) as exc:
            self._show_error(exc, tr("Could not open the project"))

    def open_example_dialog(self):
        """Open a copy of an example in a new folder; the original stays untouched and nothing runs."""
        examples = self.available_examples()
        if not examples:
            self._show_error(
                tr(
                    "The examples are not included in this installation. They are in the examples folder of the source code."
                ),
                tr("No examples available"),
            )
            return
        from .guide import ExampleChooser

        chooser = ExampleChooser([title for title, _, _ in examples], self.project_dialog_parent())
        if not chooser.exec() or not self._confirm_discard():
            return
        title, folder, name = examples[chooser.choice()]
        projects = Path(
            self.settings.value("v1/projects/folder", str(Path.home() / "Makebench" / "Projects"))
        ).expanduser()
        destination = projects / slug(
            folder.name if folder.name not in {"qt", "gtk"} else folder.parent.name
        )
        number = 2
        while destination.exists():
            destination = destination.with_name(
                destination.name.rsplit("-copy", 1)[0] + f"-copy{number}"
            )
            number += 1
        try:
            projects.mkdir(parents=True, exist_ok=True)
            shutil.copytree(folder, destination, ignore=shutil.ignore_patterns("__pycache__"))
            path = destination / name
            self._replace_project(load_project(path), path)
        except (OSError, ProjectError) as exc:
            self._show_error(exc, tr("Could not open the example"))
            return
        # A copy made here is the user's own; trusting it avoids a warning about code they just chose.
        self._created_here = True
        self.trust_project()
        self.pages.setCurrentWidget(self.editor_page)
        self.workspace_toolbar.show()
        self.statusBar().showMessage(
            tr("Example copied to {path}. Press F5 to test it.").format(path=destination), 10000
        )
        from .guide import show_guide

        show_guide(self, automatic=True)

    def share_project(self):
        """Export the editable document and assets; this is not the application exporter."""
        if not self._finish_field_edit():
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            tr("Share project"),
            slug(self.project.name) + ".zip",
            tr("Shared project (*.zip)"),
        )
        if not filename:
            return
        try:
            write_bundle(self.project, self.source.text, self.assets.read, filename)
            self.statusBar().showMessage(tr("Project shared at {path}").format(path=filename), 7000)
        except (OSError, ProjectError) as exc:
            self._show_error(exc, tr("Could not share the project"))

    def recovery_root(self):
        """Resolve the XDG state folder; never uses the project's original folder for snapshots."""
        base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
        return Path(base) / "makebench" / "recovery"

    def snapshot_recovery(self):
        """Write a complete copy, including assets not saved yet; never runs code."""
        if not (
            self.history.dirty or self.source.dirty or self.logic.pending or self.script_dirty()
        ):
            return
        if not self.prepare_script_change() or not self.logic.flush():
            return
        root = self.recovery_root()
        root.mkdir(parents=True, exist_ok=True)
        target = root / self.project.id
        temporary = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=root))
        try:
            write_bundle(
                self.project, self.source.text, self.assets.read, temporary / "project.zip"
            )
            (temporary / "session.json").write_text(
                json.dumps(
                    {
                        "path": str(self.path) if self.path else None,
                        "time": time.time(),
                        "name": self.project.name,
                    }
                ),
                encoding="utf-8",
            )
            previous = target.with_name(target.name + ".previous")
            if previous.exists():
                shutil.rmtree(previous)
            if target.exists():
                target.rename(previous)
            temporary.rename(target)
            if previous.exists():
                shutil.rmtree(previous)
        except (OSError, ProjectError) as exc:
            self.statusBar().showMessage(
                tr("Could not create recovery: {error}").format(error=exc), 6000
            )
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def clear_recovery(self, project_id=None):
        """Delete only the snapshot of the project confirmed as saved or discarded."""
        for suffix in ("", ".previous"):
            path = self.recovery_root() / ((project_id or self.project.id) + suffix)
            if path.exists():
                shutil.rmtree(path)

    def refresh_recovery(self):
        """Detect valid snapshots from previous sessions without loading code."""
        root = self.recovery_root()
        self.recoveries = (
            sorted(
                [
                    p
                    for p in root.glob("*")
                    if (p / "session.json").is_file() and (p / "project.zip").is_file()
                ],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if root.exists()
            else []
        )
        self.recovery_row.setVisible(bool(self.recoveries))
        if self.recoveries and hasattr(self, "home_recovery_label"):
            from .startup import recovery_text

            self.home_recovery_label.setText(recovery_text(self.recoveries))

    def recover_latest(self):
        """Recover into an isolated session folder, leaving the original untouched."""
        if not self.recoveries or not self._confirm_discard():
            return
        snapshot = self.recoveries[0]
        try:
            self._recovery_temp = tempfile.TemporaryDirectory(prefix="makebench-recovered-")
            path = read_bundle(snapshot / "project.zip", Path(self._recovery_temp.name))
            project = load_project(path)
            source = SourceBuffer.load(path)
            self._replace_project(project, None)
            self.source.text = source.text
            self.source_editor.setPlainText(source.text)
            self.assets = AssetStore(path.parent)
            # Recovery requires Save As; fingerprints are not bound to the original.
            self.history.push(project)
            self.source.saved_text = source.text + chr(0)
            self._recovered = True
            self._refresh()
            self.pages.setCurrentWidget(self.editor_page)
            self.workspace_toolbar.show()
            self.statusBar().showMessage(
                tr("Changes recovered. Save to a folder to continue."), 10000
            )
        except (OSError, ProjectError, ValueError) as exc:
            self._show_error(exc, tr("Could not recover the session"))

    def discard_recovery(self):
        """Discard only the selected recovery, keeping the original project."""
        if self.recoveries:
            shutil.rmtree(self.recoveries[0])
            self.refresh_recovery()

    def fingerprint(self):
        """Bind trust to the content that will run, not just to the path."""
        data = (
            json.dumps(self.project.to_dict(), sort_keys=True, ensure_ascii=True) + self.source.text
        )
        return hashlib.sha256(data.encode()).hexdigest()

    def trust_project(self):
        """Record consent for the project's current snapshot."""
        self._trusted_session = True
        self._trusted = self.fingerprint()
        if self.path:
            self.settings.setValue(
                "trust/" + hashlib.sha256(str(self.path).encode()).hexdigest(), self._trusted
            )

    def confirm_trust(self):
        """Ask for consent once per imported content before running."""
        from .settings import preference

        if (
            not preference("projects/trust")
            or not self.path
            or getattr(self, "_created_here", False)
            or getattr(self, "_trusted_session", False)
        ):
            return True
        key = "trust/" + hashlib.sha256(str(self.path).encode()).hexdigest()
        if (
            getattr(self, "_trusted", None) == self.fingerprint()
            or self.settings.value(key) == self.fingerprint()
        ):
            return True
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr("Test this project?"))
        dialog.setText(
            tr(
                "Testing will run Python functions and scripts with your permissions. The separate process is not a sandbox. Open Code to review the project before continuing."
            )
        )
        run = dialog.addButton(tr("Trust and test"), QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(tr("Review code"), QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() is run:
            self.trust_project()
            return True
        self.set_mode("code")
        return False

    def watch_source(self):
        """Watch your own file without replacing an edit automatically."""
        if not hasattr(self, "source_watcher"):
            return
        old = self.source_watcher.files()
        if old:
            self.source_watcher.removePaths(old)
        if self.source.path and self.source.path.exists():
            self.source_watcher.addPath(str(self.source.path))

    def source_changed_externally(self, _path):
        """Flag a conflict; the SourceBuffer fingerprint keeps protecting the write."""
        try:
            data = (
                self.source.path.read_bytes()
                if self.source.path and self.source.path.exists()
                else None
            )
        except OSError as exc:
            self.statusBar().showMessage(str(exc), 7000)
            return
        if self.source.path and data != self.source.original:
            self.external_change_row.show()
            self.statusBar().showMessage(
                tr("Functions changed outside Makebench. Choose Reload or Keep my version."),
                15000,
            )
        self.watch_source()

    def save_as_dialog(self):
        """Ask for a name and folder, copying functions and assets through the existing mechanisms."""
        if not self._finish_field_edit():
            return False
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Save project as"))
        dialog.resize(620, 210)
        form = QFormLayout(dialog)
        name = QLineEdit(
            self.path.name[: -len(".makebench.json")] if self.path else slug(self.project.name)
        )
        folder = QLineEdit(
            str(self.path.parent)
            if self.path
            else str(Path.home() / "Makebench" / "Projects" / slug(self.project.name))
        )
        form.addRow(tr("File name"), name)
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(folder)
        choose = QPushButton(tr("Choose…"))
        rl.addWidget(choose)

        def choose_folder():
            """Receive a folder choice without creating or changing files."""
            path = QFileDialog.getExistingDirectory(dialog, tr("Project folder"), folder.text())
            if path:
                folder.setText(path)

        choose.clicked.connect(choose_folder)
        form.addRow(tr("Folder"), row)
        note = QLabel(
            tr(
                "Includes the functions file and the project's assets. Different sources at the destination are preserved."
            )
        )
        note.setWordWrap(True)
        form.addRow(note)
        error = QLabel()
        error.setWordWrap(True)
        form.addRow(error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        saved = []

        def save():
            """Validate the fields and confirm only after saving successfully."""
            filename = name.text().strip()
            if not filename or Path(filename).name != filename or filename in {".", ".."}:
                error.setText(tr("Enter a file name, without folders."))
                return
            if not filename.endswith(".makebench.json"):
                filename += ".makebench.json"
            destination = Path(folder.text()).expanduser() / filename
            if destination.exists() and destination != self.path:
                if (
                    QMessageBox.warning(
                        dialog,
                        tr("Replace project?"),
                        tr(
                            "The destination already contains a project. Your functions and assets will still be checked before saving."
                        ),
                        QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Cancel,
                    )
                    != QMessageBox.StandardButton.Save
                ):
                    return
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                error.setText(str(exc))
                return
            if self.save_to(destination):
                saved.append(True)
                dialog.accept()

        buttons.accepted.connect(save)
        dialog.exec()
        return bool(saved)

    def choose_programming(self, kind):
        """Record blocks or Python; afterwards only the explicit conversion changes it."""
        self.project.metadata["programming"] = kind
        self.history.push(self.project, tr("Choose how to program"))
        self._refresh()

    def refresh_programming_banner(self):
        """Ask without blocking when an older, empty project has no choice yet."""
        if hasattr(self, "programming_row"):
            self.programming_row.setVisible(bool(self.path) and self.project.programming is None)

    def refresh_trust_banner(self):
        """Explain future execution without blocking reading and editing the project."""
        if not hasattr(self, "trust_row"):
            return
        from .settings import preference

        trusted = (
            not preference("projects/trust")
            or not self.path
            or getattr(self, "_created_here", False)
            or getattr(self, "_trusted_session", False)
        )
        if self.path and not trusted:
            key = "trust/" + hashlib.sha256(str(self.path).encode()).hexdigest()
            if self.settings.value(key) == self.fingerprint():
                self._trusted_session = True
                trusted = True
        self.trust_row.setVisible(not trusted)
        if not trusted:
            from makebench.core.logic import function_names

            count = len(function_names(self.source.text)[0])

            def scripts(value):
                """Count declared scripts, without running their texts."""
                if isinstance(value, dict):
                    return int(value.get("op") == "script") + sum(
                        scripts(v) for v in value.values()
                    )
                if isinstance(value, list):
                    return sum(scripts(v) for v in value)
                return 0

            script_count = sum(scripts(f.get("body")) for f in self.project.workflows)
            self.trust_label.setText(
                tr(
                    "Project not reviewed yet: {functions} and {scripts}. Nothing was run. Testing runs this code with your permissions."
                ).format(
                    functions=ntr(
                        "{count} Python function", "{count} Python functions", count
                    ).format(count=count),
                    scripts=ntr("{count} script", "{count} scripts", script_count).format(
                        count=script_count
                    ),
                )
            )
