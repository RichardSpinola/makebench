# SPDX-License-Identifier: GPL-3.0-or-later
"""Window shell: the area bar on the left, the "where you are" strip and the status bar."""

from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from makebench.i18n import ntr, tr

from .look import make_muted
from .theme import icon, manager


def area_names():
    """Short names shown in the strip badge, one per area."""
    return {
        "map": tr("MAP"),
        "design": tr("DESIGN"),
        "logic": tr("LOGIC"),
        "code": tr("CODE"),
    }


def area_hints():
    """One line on what each area is for."""
    return {
        "map": tr("How the windows connect"),
        "design": tr("Drag components into the window"),
        "logic": tr("Blocks and nodes for what happens"),
        "code": tr("The project's Python"),
    }


class AreaButton(QToolButton):
    """Icon-only area button; the current area gets the raised surface and an accent edge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIconSize(QSize(18, 18))
        self.setFixedSize(40, 38)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def paintEvent(self, _event):
        t = manager().tokens
        painter = QPainter(self)
        if self.isChecked():
            painter.fillRect(self.rect(), QColor(t["raised"]))
            painter.fillRect(QRect(0, 0, 2, self.height()), QColor(t["accent"]))
        elif self.underMouse() and self.isEnabled():
            painter.fillRect(self.rect(), QColor(t["hover"]))
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        size = self.iconSize()
        pixmap = self.icon().pixmap(size, mode)
        painter.drawPixmap(
            (self.width() - size.width()) // 2, (self.height() - size.height()) // 2, pixmap
        )
        if self.hasFocus():
            painter.setPen(QColor(t["accent"]))
            painter.drawRect(self.rect().adjusted(2, 2, -3, -3))


class AreaBar(QWidget):
    """Vertical column of areas; tools that open their own window sit below a gap."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(40)
        self.setAccessibleName(tr("Areas"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 1, 0)
        layout.setSpacing(0)
        layout.addStretch(1)

    def add_area(self, button):
        """Add an area button above the gap."""
        layout = self.layout()
        layout.insertWidget(layout.count() - 1, button)

    def add_bottom(self, button):
        """Add a button below the gap, at the bottom of the bar."""
        self.layout().addWidget(button)

    def paintEvent(self, _event):
        t = manager().tokens
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t["sidebar"]))
        painter.fillRect(QRect(self.width() - 1, 0, 1, self.height()), QColor(t["border"]))


class AreaStrip(QWidget):
    """A thin strip saying which area is open, where in the project, and what it is for."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 1)
        layout.setSpacing(8)
        self.badge = QLabel()
        self.badge.setTextFormat(Qt.TextFormat.PlainText)
        self.badge.setFixedHeight(18)
        self.path = make_muted(QLabel())
        self.path.setWordWrap(False)
        self.path.setTextFormat(Qt.TextFormat.PlainText)
        self.path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.hint = make_muted(QLabel())
        self.hint.setWordWrap(False)
        self.hint.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.badge)
        layout.addWidget(self.path, 1)
        layout.addWidget(self.hint)
        manager().changed.connect(self.restyle)
        self.restyle()

    def restyle(self, *_):
        """The badge is the one place the accent fills a surface."""
        t = manager().tokens
        self.badge.setStyleSheet(
            f"background: {t['fill']}; color: {t['on_accent']}; font-weight: bold;"
            " font-size: 11px; padding: 0 7px; border-radius: 2px;"
        )
        self.update()

    def show_area(self, name, path, hint):
        self.badge.setText(name)
        self.path.setText(path)
        self.path.setToolTip(path)
        self.hint.setText(hint)

    def paintEvent(self, _event):
        t = manager().tokens
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t["sidebar"]))
        painter.fillRect(QRect(0, self.height() - 1, self.width(), 1), QColor(t["border"]))


def dot(color):
    """A small round status mark."""
    pixmap = QPixmap(10, 10)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(1, 1, 8, 8)
    painter.end()
    return QIcon(pixmap)


def status_button(tooltip):
    """A flat status bar item that still says what clicking it does."""
    button = QPushButton()
    button.setFlat(True)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setIconSize(QSize(10, 10))
    button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    return button


class ProjectCorner(QWidget):
    """Project name and folder at the right end of the menu bar, beside the logo."""

    def __init__(self, logo, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.name = QLabel()
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setAlignment(Qt.AlignmentFlag.AlignRight)
        font = self.name.font()
        font.setBold(True)
        self.name.setFont(font)
        self.folder = make_muted(QLabel())
        self.folder.setWordWrap(False)
        self.folder.setTextFormat(Qt.TextFormat.PlainText)
        self.folder.setAlignment(Qt.AlignmentFlag.AlignRight)
        small = self.folder.font()
        small.setPointSizeF(small.pointSizeF() * 0.85)
        self.folder.setFont(small)
        text.addWidget(self.name)
        text.addWidget(self.folder)
        layout.addLayout(text)
        self.logo = QLabel()
        self.logo.setAccessibleName(tr("Makebench"))
        if logo is not None:
            self.logo.setPixmap(logo.pixmap(24, 24))
        layout.addWidget(self.logo)

    def show_project(self, name, path):
        self.name.setText(name)
        if path:
            folder = str(Path(path).parent)
            home = str(Path.home())
            if folder == home or folder.startswith(home + "/"):
                folder = "~" + folder[len(home) :]
        else:
            folder = tr("Not saved yet")
        self.folder.setText(folder)
        self.setToolTip(str(path) if path else folder)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(QRect(0, 4, 1, self.height() - 8), QColor(manager().tokens["border"]))


def install_shell(window, logo=None):
    """Put the area bar beside the pages, the strip above the editor and fixed status items."""
    bar = window.mode_switcher
    if hasattr(window, "pieces_menu"):
        pieces = AreaButton()
        pieces.setIcon(icon("pieces"))
        pieces.setProperty("makebenchIcon", "pieces")
        pieces.setToolTip(tr("Pieces"))
        pieces.setAccessibleName(tr("Pieces"))
        pieces.setMenu(window.pieces_menu)
        pieces.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bar.add_area(pieces)
    if hasattr(window, "history_action"):
        history = AreaButton()
        history.setIcon(icon("history"))
        history.setProperty("makebenchIcon", "history")
        history.setToolTip(tr("Version history"))
        history.setAccessibleName(tr("Version history"))
        history.clicked.connect(window.history_action.trigger)
        bar.add_area(history)
    if hasattr(window, "plugins_menu"):
        plugins = AreaButton()
        plugins.setIcon(icon("plugins"))
        plugins.setProperty("makebenchIcon", "plugins")
        plugins.setToolTip(tr("Plugins and themes"))
        plugins.setAccessibleName(tr("Plugins and themes"))
        plugins.setMenu(window.plugins_menu)
        plugins.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bar.add_area(plugins)
    settings = AreaButton()
    settings.setIcon(icon("settings"))
    settings.setProperty("makebenchIcon", "settings")
    settings.setToolTip(tr("Preferences"))
    settings.setAccessibleName(tr("Preferences"))
    settings.clicked.connect(window.preferences)
    bar.add_bottom(settings)
    central = QWidget()
    row = QHBoxLayout(central)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    window.takeCentralWidget()
    row.addWidget(bar)
    row.addWidget(window.pages, 1)
    window.setCentralWidget(central)
    bar.show()

    window.area_strip = AreaStrip()
    window.editor_page.layout().insertWidget(0, window.area_strip)

    window.project_corner = ProjectCorner(logo)
    window.menuBar().setCornerWidget(window.project_corner, Qt.Corner.TopRightCorner)
    window.project_corner.show()

    status = window.statusBar()
    status.setSizeGripEnabled(False)
    window.save_status = status_button(tr("Open the version history"))
    if hasattr(window, "history_action"):
        window.save_status.clicked.connect(window.history_action.trigger)
    window.problems_status = status_button(tr("Show the project's problems"))
    window.problems_status.clicked.connect(lambda: show_problems(window))
    window.selection_status = QLabel()
    window.selection_status.setTextFormat(Qt.TextFormat.PlainText)
    window.theme_status = status_button(tr("Switch between light and dark"))
    window.theme_status.clicked.connect(toggle_scheme)
    status.removeWidget(window.drawer_toggle)
    for widget in (
        window.save_status,
        window.problems_status,
        window.selection_status,
        window.theme_status,
        window.drawer_toggle,
    ):
        status.addPermanentWidget(widget)
        widget.show()


def show_problems(window):
    """Open the drawer on the Problems tab."""
    window.drawer.show()
    window.drawer.setCurrentIndex(1)


def toggle_scheme():
    """Flip light and dark; the choice is saved like the one in Preferences."""
    manager().set_mode("light" if manager().tokens["dark"] else "dark")


def area_path(window):
    """Where the person is inside the project, as a short › trail."""
    project = window.project
    mode = window._mode
    if mode == "map":
        count = len(project.roots)
        return (
            project.name
            + " › "
            + ntr("{count} window", "{count} windows", count).format(count=count)
        )
    if mode == "code":
        current = window.current_code_file() if hasattr(window, "code_files") else None
        if current and not str(current).startswith("@"):
            return Path(current).name
        return window.source.path.name if window.source.path else "project.actions.py"
    trail = []
    node = project.find(window.selected_id)
    while node is not None:
        title = node.properties.get("title") if node.kind.value == "window" else None
        trail.insert(0, title or node.display_name)
        node = project.parent_of(node.id)
    if mode == "logic" and len(trail) > 2:
        trail = [trail[0], trail[-1]]
    return " › ".join(trail)


def sync_shell(window):
    """Refresh the strip, the corner and the status items from the current document."""
    if not hasattr(window, "area_strip"):
        return
    t = manager().tokens
    mode = window._mode
    hint = area_hints().get(mode, "")
    if mode in {"design", "logic"} and getattr(window, "active_state", "@default") != "@default":
        hint = tr("Editing a state: properties only")
    window.area_strip.show_area(area_names().get(mode, ""), area_path(window), hint)
    window.project_corner.show_project(window.project.name, window.path)
    dirty = (
        window.history.dirty or window.source.dirty or window.logic.pending or window.script_dirty()
    )
    count = len(list(window.project.root.walk())) - 1
    window.save_status.setIcon(dot(t["warning"] if dirty else t["success"]))
    window.save_status.setText(
        (tr("Unsaved changes") if dirty else tr("Ready"))
        + " · "
        + ntr("{count} component", "{count} components", count).format(count=count)
    )
    problems = len(getattr(window, "_problem_targets", []))
    window.problems_status.setText(
        "▲ " + ntr("{count} problem", "{count} problems", problems).format(count=problems)
        if problems
        else tr("No problems")
    )
    node = window.project.find(window.selected_id)
    window.selection_status.setText(
        "" if node is None or mode in {"map", "code"} else node.display_name
    )
    window.theme_status.setText("◐ " + (tr("Dark") if t["dark"] else tr("Light")))
    window.area_strip.update()
    window.mode_switcher.update()
