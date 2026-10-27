# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent, fixed-size launcher; the workbench appears when a project opens."""

import datetime
import json
import zlib
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from makebench import __version__
from makebench.core.templates import MODELS
from makebench.i18n import tr

from .settings import preference
from .theme import blend, icon, manager

LOGO = Path(__file__).with_name("makebench.svg")
RETRO_LOGO = Path(__file__).with_name("makebench-retro.svg")
DETAIL_ROLE = Qt.ItemDataRole.UserRole + 1
SWATCH_ROLE = Qt.ItemDataRole.UserRole + 2
SWATCHES = ("#c4762b", "#3a83c9", "#3d8b5a", "#9a5bb5", "#b5544a", "#3f8f8f")


def tips():
    """One short hint at a time, cycled by "Next"."""
    return [
        tr(
            "Any panel becomes a floating window with the button in its title. "
            "To put it back, use View › Panels › Restore layout."
        ),
        tr("Nothing in your project runs until you press F5 (Run)."),
        tr("Examples open as a copy, so you can change them freely."),
        tr("Right-click a recent project to remove it from the list or move it to the trash."),
        tr("Download from Git brings the project together with its history."),
    ]


def retro(settings=None):
    return preference("appearance/logo", settings) == "retro"


def logo_renderer(settings=None):
    return QSvgRenderer(str(RETRO_LOGO if retro(settings) else LOGO))


_watermarks = {}


def watermark_image(retro_style, size):
    """The emblem in grays, keeping its shapes; drawn faint behind the start page."""
    key = (retro_style, size.width(), size.height())
    if key not in _watermarks:
        image = QImage(size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        QSvgRenderer(str(RETRO_LOGO if retro_style else LOGO)).render(painter)
        painter.end()
        gray = image.convertToFormat(QImage.Format.Format_Grayscale8).convertToFormat(
            QImage.Format.Format_ARGB32
        )
        gray.setAlphaChannel(image.convertToFormat(QImage.Format.Format_Alpha8))
        _watermarks[key] = gray
    return _watermarks[key]


def paint_watermark(widget, settings=None):
    """Draw the big faded emblem in the lower left, like an editor with nothing open."""
    if not preference("appearance/watermark", settings):
        return
    old_style = retro(settings)
    size = QSize(1000, 588) if old_style else QSize(860, 860)
    painter = QPainter(widget)
    painter.setOpacity(0.06 if manager().tokens["dark"] else 0.05)
    painter.drawImage(-70, widget.height() - size.height() + 250, watermark_image(old_style, size))
    painter.end()


class HomeBackground(QWidget):
    """The workbench's start page, with the emblem behind it."""

    def paintEvent(self, event):
        super().paintEvent(event)
        paint_watermark(self)


class StartupBanner(QWidget):
    """Our own vector illustration with theme colors and a drag area."""

    def __init__(self, parent):
        """Reserve the top strip without a window title or resize handles."""
        super().__init__(parent)
        self.setFixedHeight(160)
        self.setAccessibleName("Makebench")
        self.settings = parent.settings
        self.close_button = QToolButton(self)
        self.close_button.setIcon(icon("close"))
        self.close_button.setProperty("makebenchIcon", "close")
        self.close_button.setIconSize(QSize(12, 12))
        self.close_button.setToolTip(tr("Close"))
        self.close_button.setAccessibleName(tr("Close the start window"))
        self.close_button.setAutoRaise(True)
        self.close_button.setFixedSize(26, 26)
        self.close_button.clicked.connect(parent.reject)

    def resizeEvent(self, event):
        """Keep the X inside the illustration, in the same corner at any DPI scale."""
        self.close_button.move(self.width() - 34, 8)
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        """The compositor can move the window by dragging the header, without resizing."""
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        """Accent wash, three connected windows and the emblem with the name."""
        t = manager().tokens
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(blend(t["panel"], t["accent"], 0.11)))
        painter.fillRect(QRect(0, self.height() - 1, self.width(), 1), QColor(t["border"]))
        line = QColor(t["muted"])
        line.setAlphaF(0.45)
        painter.setPen(QPen(line, 1.5))
        for x, y, w, h in ((502, 28, 108, 72), (634, 80, 82, 58), (480, 114, 78, 34)):
            painter.drawRoundedRect(QRectF(x, y, w, h), 4, 4)
            painter.drawLine(x + 1, y + 16, x + w - 1, y + 16)
        painter.setPen(QPen(QColor(t["accent"]), 2))
        painter.drawPolyline([QPointF(610, 64), QPointF(650, 64), QPointF(650, 80)])
        painter.drawLine(518, 100, 518, 114)
        top = (self.height() - 72) // 2
        if retro(self.settings):
            tile = QRect(22, top + 8, 76, 56)
            painter.fillRect(tile, QColor("#d8d8d8" if t["dark"] else "#ffffff"))
            painter.setPen(QColor(t["border"]))
            painter.drawRect(tile.adjusted(0, 0, -1, -1))
            logo_renderer(self.settings).render(painter, QRectF(27, top + 16, 66, 40))
        else:
            logo_renderer(self.settings).render(painter, QRectF(22, top, 72, 72))
        painter.setPen(QColor(t["text"]))
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() * 2)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(110, top + 4, 360, 40), Qt.AlignmentFlag.AlignVCenter, "Makebench")
        painter.setFont(self.font())
        painter.setPen(QColor(t["muted"]))
        painter.drawText(
            QRect(112, top + 44, 360, 24),
            Qt.AlignmentFlag.AlignVCenter,
            tr("Linux applications, built by you."),
        )
        painter.end()


class LauncherDelegate(QStyledItemDelegate):
    """Compact rows: optional color square, the name, and a dimmed line below it."""

    def paint(self, painter, option, index):
        t = manager().tokens
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        selected = opt.state & QStyle.StateFlag.State_Selected
        painter.save()
        if selected:
            painter.fillRect(opt.rect, QColor(t["fill"]))
        elif opt.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(opt.rect, QColor(t["hover"]))
        rect = opt.rect.adjusted(6, 3, -6, -3)
        swatch = index.data(SWATCH_ROLE)
        if swatch:
            square = QRect(rect.left(), rect.center().y() - 5, 10, 10)
            painter.fillRect(square, QColor(swatch))
            painter.setPen(QColor(t["on_accent"] if selected else t["muted"]))
            painter.drawRect(square)
            rect.setLeft(square.right() + 9)
        name_font = QFont(opt.font)
        if swatch:
            name_font.setWeight(QFont.Weight.DemiBold)
        small = QFont(opt.font)
        small.setPointSizeF(opt.font.pointSizeF() * 0.88)
        line = opt.fontMetrics.height()
        painter.setFont(name_font)
        painter.setPen(QColor(t["on_accent"] if selected else t["text"]))
        enabled = opt.state & QStyle.StateFlag.State_Enabled
        if not enabled:
            painter.setPen(QColor(t["muted"]))
        painter.drawText(QRect(rect.left(), rect.top(), rect.width(), line), 0, opt.text)
        detail = index.data(DETAIL_ROLE)
        if detail:
            painter.setFont(small)
            painter.setPen(QColor(t["on_accent"] if selected else t["muted"]))
            metrics = painter.fontMetrics()
            painter.drawText(
                QRect(rect.left(), rect.top() + line, rect.width(), metrics.height()),
                0,
                metrics.elidedText(detail, Qt.TextElideMode.ElideMiddle, rect.width()),
            )
        painter.restore()

    def sizeHint(self, option, index):
        lines = 2 if index.data(DETAIL_ROLE) else 1
        return QSize(200, option.fontMetrics.height() * lines + 8)


def short_path(path):
    text = str(path)
    home = str(Path.home())
    return "~" + text[len(home) :] if text.startswith(home + "/") else text


def when(timestamp):
    """Today, yesterday or the short date."""
    day = datetime.date.fromtimestamp(timestamp)
    today = datetime.date.today()
    if day == today:
        return tr("today")
    if day == today - datetime.timedelta(days=1):
        return tr("yesterday")
    return day.strftime("%d/%m")


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
        self.setFixedSize(760, 630)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        self.banner = StartupBanner(self)
        outer.addWidget(self.banner)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 14, 18, 12)
        layout.setSpacing(14)
        commands = QHBoxLayout()
        commands.setSpacing(6)
        self.open_button = self._command(tr("Open project…"), self.open_project)
        self.open_button.setDefault(True)
        self.open_button.setAutoDefault(True)
        self.new_button = self._command(tr("New project…"), lambda: self.new_project("blank"))
        self.example_button = self._command(tr("Open example…"), self.open_example)
        self.example_button.setToolTip(
            tr("Open a copy of an example project; nothing runs until you press F5.")
        )
        self.git_button = self._command(tr("Download from Git…"), self.clone_project)
        self.git_button.setToolTip(tr("Download a project from a Git repository address"))
        for button in (self.open_button, self.new_button, self.example_button, self.git_button):
            commands.addWidget(button)
        commands.addStretch()
        layout.addLayout(commands)
        self.recovery_row = self._recovery_row()
        layout.addWidget(self.recovery_row)
        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(0)
        recent_header = QHBoxLayout()
        recent_header.setContentsMargins(0, 0, 0, 4)
        recent_header.addWidget(self._heading(tr("Recent")))
        recent_header.addStretch()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Filter…"))
        self.filter.setAccessibleName(tr("Filter recent projects"))
        self.filter.setClearButtonEnabled(True)
        self.filter.setFixedWidth(150)
        self.filter.textChanged.connect(self.filter_recents)
        recent_header.addWidget(self.filter)
        left.addLayout(recent_header)
        left.addWidget(self._rule())
        self.recents = self._list(tr("Recent projects"))
        self.recents.itemActivated.connect(self.open_recent)
        self.recents.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recents.customContextMenuRequested.connect(self.recent_menu)
        left.addWidget(self.recents, 1)
        columns.addLayout(left, 115)
        right = QVBoxLayout()
        right.setSpacing(0)
        models_heading = self._heading(tr("New from template"))
        models_heading.setMinimumHeight(self.filter.sizeHint().height())
        models_heading.setContentsMargins(0, 0, 0, 4)
        right.addWidget(models_heading)
        right.addWidget(self._rule())
        self.models = self._list(tr("Templates"))
        self.models.itemActivated.connect(
            lambda item: self.new_project(item.data(Qt.ItemDataRole.UserRole))
        )
        right.addWidget(self.models, 1)
        columns.addLayout(right, 100)
        layout.addLayout(columns, 1)
        outer.addWidget(content, 1)
        outer.addWidget(self._tip_row())
        outer.addWidget(self._footer())
        self.refresh()

    def _command(self, text, callback):
        button = QPushButton(text)
        button.setMinimumHeight(28)
        button.clicked.connect(callback)
        return button

    @staticmethod
    def _heading(text):
        label = QLabel(text)
        font = QFont(label.font())
        font.setWeight(QFont.Weight.DemiBold)
        label.setFont(font)
        return label

    @staticmethod
    def _rule():
        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setFixedHeight(1)
        return rule

    def _list(self, name):
        view = QListWidget()
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setAccessibleName(name)
        view.setItemDelegate(LauncherDelegate(view))
        view.setMouseTracking(True)
        view.setAutoFillBackground(False)
        view.viewport().setAutoFillBackground(False)
        return view

    def _recovery_row(self):
        row = QFrame()
        row.setObjectName("recovery_row")
        line = QHBoxLayout(row)
        line.setContentsMargins(10, 3, 4, 3)
        line.setSpacing(8)
        self.recovery_label = QLabel()
        line.addWidget(self.recovery_label, 1)
        recover = QPushButton(tr("Recover"))
        recover.clicked.connect(lambda: self.choose_project(self.window.recover_latest))
        line.addWidget(recover)
        discard = QToolButton()
        discard.setIcon(icon("close"))
        discard.setProperty("makebenchIcon", "close")
        discard.setAutoRaise(True)
        discard.setToolTip(tr("Discard recovery"))
        discard.setAccessibleName(tr("Discard recovery"))
        discard.clicked.connect(self.discard_recovery)
        line.addWidget(discard)
        return row

    def _tip_row(self):
        holder = QWidget()
        margin = QHBoxLayout(holder)
        margin.setContentsMargins(18, 0, 18, 12)
        self.tip_box = QFrame()
        self.tip_box.setObjectName("tip_box")
        line = QHBoxLayout(self.tip_box)
        line.setContentsMargins(10, 6, 6, 6)
        line.setSpacing(10)
        mark = QLabel("i")
        mark.setFixedSize(18, 18)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setObjectName("tip_mark")
        line.addWidget(mark)
        self.tip = QLabel()
        self.tip.setWordWrap(True)
        line.addWidget(self.tip, 1)
        self.next_tip_button = QPushButton(tr("Next ›"))
        self.next_tip_button.clicked.connect(self.next_tip)
        line.addWidget(self.next_tip_button)
        margin.addWidget(self.tip_box)
        self.tip_index = self.settings.value("v1/projects/tip", 0, type=int)
        self.show_tip()
        return holder

    def _footer(self):
        footer = QFrame()
        footer.setObjectName("launcher_footer")
        line = QHBoxLayout(footer)
        line.setContentsMargins(18, 8, 18, 8)
        line.setSpacing(14)
        self.show_at_startup = QCheckBox(tr("Show at startup"))
        self.show_at_startup.setChecked(preference("projects/startup", self.settings))
        self.show_at_startup.toggled.connect(
            lambda enabled: self.settings.setValue("v1/projects/startup", enabled)
        )
        line.addWidget(self.show_at_startup)
        self.guide_link = QLabel(f'<a href="guide">{tr("Your first app in 5 minutes")}</a>')
        self.guide_link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.guide_link.linkActivated.connect(self.open_guide)
        line.addWidget(self.guide_link)
        line.addStretch()
        self.version = QLabel(__version__)
        line.addWidget(self.version)
        return footer

    def restyle(self):
        """Colors from the theme tokens; the frame, the tip and the warning row."""
        t = manager().tokens
        # The amber of the design: the theme's warning hue reads as an error here.
        warn = QColor("#e0a43a" if t["dark"] else "#b7791f")
        soft = blend(t["panel"], warn.name(), 0.12)
        self.recovery_row.setStyleSheet(
            f"#recovery_row {{ border: 1px solid {warn.name()}; border-radius: 3px;"
            f" background: {soft}; }}"
        )
        self.tip_box.setStyleSheet(
            f"#tip_box {{ border: 1px solid {t['border']};"
            f" background: {blend(t['panel'], t['raised'], 0.5)}; }}"
            f" #tip_mark {{ border: 1px solid {t['control']}; color: {t['info']};"
            f" font-weight: 700; font-family: serif; }}"
        )
        self.open_button.setStyleSheet(
            f"QPushButton {{ background: {t['fill']}; color: {t['on_accent']};"
            f" border: 1px solid {t['fill']}; border-radius: 3px; padding: 0 10px; }}"
            f" QPushButton:hover {{ background: {t['pressed']}; }}"
        )
        self.findChild(QFrame, "launcher_footer").setStyleSheet(
            f"#launcher_footer {{ border-top: 1px solid {t['border']}; }}"
            f" #launcher_footer QLabel {{ color: {t['muted']}; }}"
        )
        self.guide_link.setText(
            f'<a href="guide" style="color: {t["info"]}; text-decoration: none">'
            f"{tr('Your first app in 5 minutes')}</a>"
        )
        self.update()

    def showEvent(self, event):
        self.restyle()
        manager().changed.connect(self.restyle, Qt.ConnectionType.UniqueConnection)
        super().showEvent(event)

    def paintEvent(self, event):
        """Our own outline replaces the external frame."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QColor(manager().tokens["border"]))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()

    def refresh(self):
        """Short names in the content; full paths in tooltips and the context menu."""
        self.recents.clear()
        for value in self.settings.value("projects/recent", [], type=list)[:12]:
            path = Path(value)
            found = path.is_file()
            detail = short_path(path.parent)
            if found:
                detail += " · " + when(path.stat().st_mtime)
            else:
                detail += " · " + tr("missing")
            item = QListWidgetItem(path.parent.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setData(DETAIL_ROLE, detail)
            item.setData(
                SWATCH_ROLE,
                SWATCHES[zlib.crc32(str(path).encode()) % len(SWATCHES)] if found else "#777777",
            )
            item.setToolTip(str(path))
            self.recents.addItem(item)
        if not self.recents.count():
            item = QListWidgetItem(tr("No recent projects"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recents.addItem(item)
        else:
            self.recents.setCurrentRow(0)
        self.models.clear()
        recent = self.settings.value("projects/templates/recent", [], type=list)
        order = {key: i for i, key in enumerate(recent)}
        for key, label, description in sorted(
            MODELS, key=lambda m: order.get(m[0], len(order) + MODELS.index(m))
        ):
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setData(DETAIL_ROLE, description)
            self.models.addItem(item)
        self.refresh_recovery()
        self.filter_recents()

    def refresh_recovery(self):
        recoveries = getattr(self.window, "recoveries", [])
        self.recovery_row.setVisible(bool(recoveries))
        if not recoveries:
            return
        detail = ""
        try:
            data = json.loads((recoveries[0] / "session.json").read_text(encoding="utf-8"))
            moment = datetime.datetime.fromtimestamp(float(data.get("time", 0)))
            detail = tr("{name}, {day} at {time}").format(
                name=data.get("name") or tr("Untitled"),
                day=when(moment.timestamp()),
                time=moment.strftime("%H:%M"),
            )
        except (OSError, ValueError, TypeError):
            pass
        self.recovery_label.setText(
            tr("Previous session available") + (f" — {detail}" if detail else "")
        )

    def discard_recovery(self):
        self.window.discard_recovery()
        self.refresh_recovery()

    def filter_recents(self):
        query = self.filter.text().casefold()
        for index in range(self.recents.count()):
            item = self.recents.item(index)
            text = f"{item.text()} {item.data(DETAIL_ROLE) or ''} {item.toolTip()}"
            item.setHidden(bool(query) and query not in text.casefold())

    def show_tip(self):
        hints = tips()
        self.tip_index %= len(hints)
        self.tip.setText(f"<b>{tr('Tip:')}</b> {hints[self.tip_index]}")

    def next_tip(self):
        self.tip_index += 1
        self.settings.setValue("v1/projects/tip", self.tip_index % len(tips()))
        self.show_tip()

    def open_guide(self, _link=""):
        from .settings import open_checklist

        open_checklist(self.window)

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
                if not self.window.isVisible():
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

    def clone_project(self):
        """Download a repository and open the project inside it."""
        self.choose_project(self.window.clone_project_dialog)

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


def show_startup(window):
    """Open the launcher again over the workbench (Start page, File menu)."""
    dialog = getattr(window, "startup_dialog", None)
    if dialog is None or not isinstance(dialog, StartupDialog):
        dialog = StartupDialog(window)
        window.startup_dialog = dialog
    else:
        dialog.refresh()
    dialog.show()
    if window.isVisible():
        frame = window.frameGeometry()
        dialog.move(frame.center() - dialog.rect().center())
    dialog.raise_()
    dialog.activateWindow()
    return dialog
