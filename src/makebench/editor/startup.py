"""Independent, fixed-size launcher; the workbench appears when a project opens."""

from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from makebench import __version__
from makebench.core.templates import MODELS
from .settings import preference
from .theme import icon
from makebench.i18n import tr


class StartupBanner(QWidget):
    """Our own vector illustration with desktop colors and a drag area."""

    def __init__(self, parent):
        """Reserve the top strip without a window title or resize handles."""
        super().__init__(parent)
        self.setFixedHeight(180)
        self.setAccessibleName("Makebench")
        self.close_button = QToolButton(self)
        self.close_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton)
        )
        self.close_button.setToolTip(tr("Close"))
        self.close_button.setAccessibleName(tr("Close the start window"))
        self.close_button.setAutoRaise(True)
        self.close_button.setFixedSize(30, 30)
        self.close_button.clicked.connect(parent.reject)

    def resizeEvent(self, event):
        """Keep the X inside the illustration, in the same corner at any DPI scale."""
        self.close_button.move(self.width() - 38, 8)
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        """The compositor can move the window by dragging the header, without resizing."""
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        """Draw connected windows; does not copy Kdenlive's image or brand."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        base = palette.color(QPalette.ColorRole.Window)
        accent = palette.color(QPalette.ColorRole.Highlight)
        foreground = palette.color(QPalette.ColorRole.WindowText)
        painter.fillRect(self.rect(), base)
        wash = QColor(accent)
        wash.setAlpha(28)
        painter.fillRect(self.rect(), wash)
        line = palette.color(QPalette.ColorRole.WindowText)
        line.setAlpha(45)
        painter.setPen(QPen(line, 1.5))
        for x, y, w, h in ((322, 30, 108, 76), (454, 88, 82, 62), (300, 126, 78, 38)):
            painter.drawRoundedRect(QRectF(x, y, w, h), 5, 5)
            painter.drawLine(x + 1, y + 16, x + w - 1, y + 16)
        painter.setPen(QPen(accent, 2))
        painter.drawLine(430, 68, 470, 68)
        painter.drawLine(470, 68, 470, 88)
        painter.drawLine(338, 106, 338, 126)
        painter.setPen(foreground)
        font = QFont(self.font())
        font.setPointSize(25)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(24, 100, "Makebench")
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(26, 124, tr("Linux applications, built by you."))
        painter.end()


class StartupDialog(QDialog):
    """Window without system decoration, fixed size and a single inner X."""

    def __init__(self, window):
        """Share recents and templates with the still-hidden workbench."""
        super().__init__(None, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.window = window
        self.settings = window.settings
        self._choosing = False
        self.setWindowTitle("Makebench")
        self.setWindowIcon(window.windowIcon())
        self.setFixedSize(576, 610)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        self.banner = StartupBanner(self)
        outer.addWidget(self.banner)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(18)
        commands = QHBoxLayout()
        commands.setSpacing(18)
        self.open_button = QPushButton(icon("open"), tr("Open project…"))
        self.open_button.setFixedSize(155, 32)
        self.open_button.clicked.connect(self.open_project)
        open_column = QHBoxLayout()
        open_column.addWidget(self.open_button)
        open_column.addStretch()
        commands.addLayout(open_column, 1)
        self.new_button = QPushButton(icon("new"), tr("New project…"))
        self.new_button.setFixedSize(155, 32)
        self.new_button.clicked.connect(lambda: self.new_project("blank"))
        new_column = QHBoxLayout()
        new_column.addWidget(self.new_button)
        new_column.addStretch()
        commands.addLayout(new_column, 1)
        self.example_button = QPushButton(icon("document"), tr("Open example…"))
        self.example_button.setFixedSize(155, 32)
        self.example_button.setToolTip(
            tr("Open a copy of an example project; nothing runs until you press F5.")
        )
        self.example_button.clicked.connect(self.open_example)
        example_column = QHBoxLayout()
        example_column.addWidget(self.example_button)
        example_column.addStretch()
        commands.addLayout(example_column, 1)
        layout.addLayout(commands)
        if getattr(window, "recoveries", []):
            recovery = QHBoxLayout()
            recovery.addWidget(QLabel(tr("Previous session available.")))
            recover = QPushButton(tr("Recover"))
            recover.setFixedHeight(30)
            recover.clicked.connect(lambda: self.choose_project(window.recover_latest))
            recovery.addStretch()
            recovery.addWidget(recover)
            layout.addLayout(recovery)
        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(QLabel(tr("Recent")))
        self.recents = QListWidget()
        self.recents.setFrameShape(QFrame.Shape.NoFrame)
        self.recents.viewport().setBackgroundRole(QPalette.ColorRole.Window)
        self.recents.setAccessibleName(tr("Recent projects"))
        self.recents.itemActivated.connect(self.open_recent)
        left.addWidget(self.recents, 1)
        columns.addLayout(left, 1)
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(QLabel(tr("New from template")))
        self.models = QListWidget()
        self.models.setFrameShape(QFrame.Shape.NoFrame)
        self.models.viewport().setBackgroundRole(QPalette.ColorRole.Window)
        self.models.setAccessibleName(tr("Recent templates"))
        self.models.itemActivated.connect(
            lambda item: self.new_project(item.data(Qt.ItemDataRole.UserRole))
        )
        right.addWidget(self.models, 1)
        columns.addLayout(right, 1)
        layout.addLayout(columns, 1)
        self.recents.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recents.customContextMenuRequested.connect(self.recent_menu)
        footer = QHBoxLayout()
        self.show_at_startup = QCheckBox(tr("Show at startup"))
        self.show_at_startup.setChecked(preference("projects/startup", self.settings))
        self.show_at_startup.toggled.connect(
            lambda enabled: self.settings.setValue("v1/projects/startup", enabled)
        )
        footer.addWidget(self.show_at_startup)
        footer.addStretch()
        footer.addWidget(QLabel(__version__))
        layout.addLayout(footer)
        outer.addWidget(content, 1)
        self.refresh()

    def paintEvent(self, event):
        """The native outline replaces the external frame; creates no global theme."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.Mid))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()

    def refresh(self):
        """Short names in the content; full paths in tooltips and the context menu."""
        self.recents.clear()
        for value in self.settings.value("projects/recent", [], type=list)[:12]:
            path = Path(value)
            item = QListWidgetItem(
                icon("document"),
                path.parent.name + (" · " + tr("missing") if not path.is_file() else ""),
            )
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            item.setSizeHint(QSize(220, 30))
            self.recents.addItem(item)
        if not self.recents.count():
            item = QListWidgetItem(tr("No recent projects"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recents.addItem(item)
        self.models.clear()
        labels = {key: label for key, label, _ in MODELS}
        keys = self.settings.value("projects/templates/recent", ["blank"], type=list)
        for key in keys[:5]:
            if key in labels:
                item = QListWidgetItem(labels[key])
                item.setData(Qt.ItemDataRole.UserRole, key)
                item.setSizeHint(QSize(220, 30))
                self.models.addItem(item)
        if self.models.count():
            self.models.setCurrentRow(0)

    def choose_project(self, operation):
        """Cancel keeps the launcher; the workbench appears only after a valid switch."""
        if self._choosing:
            return
        self._choosing = True
        before = (self.window.project.id, self.window.path)
        try:
            operation()
            if (self.window.project.id, self.window.path) != before:
                # The workbench becomes visible before the last dialog closes: there is
                # no window-less gap that would quit QApplication prematurely.
                self.window.set_mode("map")
                self.window.resize(1280, 800)
                self.window.show()
                self.accept()
                self.window.raise_()
                self.window.activateWindow()
        finally:
            self._choosing = False

    def new_project(self, key):
        """Every template lives in the small creation dialog's selector."""
        self.choose_project(lambda: self.window.new_project_dialog(key))

    def open_project(self):
        """The selector reads data and never runs the document's scripts or functions."""
        self.choose_project(self.window.open_project)

    def open_example(self):
        """Copy an example into a new folder and open it in the workbench."""
        self.choose_project(self.window.open_example_dialog)

    def open_recent(self, item):
        """Use the workbench's same validated, inert loading."""
        if item and item.data(Qt.ItemDataRole.UserRole):
            self.choose_project(lambda: self.window.open_recent(item))

    def recent_menu(self, point):
        """Removing the reference and moving to the trash stay distinct actions."""
        item = self.recents.itemAt(point)
        if not item or not item.data(Qt.ItemDataRole.UserRole):
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        self.window.refresh_recents()
        target = next(
            (
                self.window.recent_list.item(i)
                for i in range(self.window.recent_list.count())
                if self.window.recent_list.item(i).data(Qt.ItemDataRole.UserRole) == path
            ),
            None,
        )
        self.window.recent_list.setCurrentItem(target)
        menu = QMenu(self)
        menu.addAction(tr("Open"), lambda: self.open_recent(item))
        menu.addAction(
            tr("Remove from list"), lambda: (self.window.remove_recent(), self.refresh())
        )
        menu.addAction(tr("Move to trash…"), lambda: (self.window.trash_recent(), self.refresh()))
        menu.exec(self.recents.viewport().mapToGlobal(point))
