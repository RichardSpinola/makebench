# SPDX-License-Identifier: GPL-3.0-or-later
"""Plugins › Themes: pick, preview, create and import `.mbtheme` color themes."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from makebench.i18n import tr
from makebench.ui import themes
from makebench.ui.theme import manager

from .errors import show_error
from .look import DETAIL_ROLE, TwoLineDelegate, button_row, header, make_muted

DESKTOP = "\x00desktop"


def color_names() -> list[tuple[str, str]]:
    return [
        ("win", tr("Background")),
        ("side", tr("Bars")),
        ("base", tr("Panels")),
        ("line", tr("Lines")),
        ("btn", tr("Buttons")),
        ("fg", tr("Text")),
        ("mut", tr("Dim text")),
        ("accent", tr("Accent")),
    ]


class ThemePreview(QWidget):
    """A small editor window painted with one theme's colors."""

    def __init__(self):
        super().__init__()
        self.colors = None
        self.accent = "#3a83c9"
        self.setMinimumSize(320, 190)

    def show_theme(self, colors, accent):
        self.colors, self.accent = colors, accent
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.colors is None:
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, tr("Your desktop's colors"))
            return
        c = {key: QColor(value) for key, value in self.colors.items()}
        accent = QColor(self.accent)
        w, h = box.width(), box.height()
        painter.setPen(c["line"])
        painter.setBrush(c["win"])
        painter.drawRoundedRect(box, 6, 6)
        bar = QRectF(box.left(), box.top(), w, 24)
        painter.fillRect(bar.adjusted(1, 1, -1, 0), c["side"])
        painter.setPen(c["fg"])
        painter.drawText(bar.adjusted(10, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, "Makebench")
        side = QRectF(box.left() + 1, bar.bottom(), 44, h - 25)
        painter.fillRect(side, c["side"])
        for row in range(4):
            slot = QRectF(side.left() + 10, side.top() + 10 + row * 30, 24, 22)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent if row == 0 else c["btn"])
            painter.drawRoundedRect(slot, 4, 4)
        panel = QRectF(side.right() + 10, bar.bottom() + 10, w * 0.32, h - 45)
        canvas = QRectF(
            panel.right() + 10, panel.top(), box.right() - panel.right() - 20, panel.height()
        )
        for area in (panel, canvas):
            painter.setPen(c["line"])
            painter.setBrush(c["base"])
            painter.drawRoundedRect(area, 4, 4)
        for row in range(4):
            line = QRectF(panel.left() + 8, panel.top() + 10 + row * 20, panel.width() - 16, 14)
            if row == 1:
                painter.fillRect(line.adjusted(-4, -2, 4, 2), accent)
                painter.setPen(QColor("#ffffff"))
            else:
                painter.setPen(c["fg"] if row % 2 == 0 else c["mut"])
            painter.drawText(
                line, Qt.AlignmentFlag.AlignVCenter, tr("Item {number}").format(number=row + 1)
            )
        button = QRectF(canvas.left() + 12, canvas.bottom() - 34, 84, 24)
        painter.setPen(c["btnLine"])
        painter.setBrush(c["btn"])
        painter.drawRoundedRect(button, 4, 4)
        painter.setPen(c["fg"])
        painter.drawText(button, Qt.AlignmentFlag.AlignCenter, tr("Button"))
        painter.setPen(c["mut"])
        painter.drawText(
            canvas.adjusted(12, 10, -12, -40),
            Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
            tr("Dim text sits next to normal text."),
        )


class Swatch(QPushButton):
    """A color sample that opens a color picker on editable themes."""

    picked = Signal(str, str)

    def __init__(self, key, label):
        super().__init__()
        self.key, self.value = key, "#000000"
        self.label = label
        self.setMinimumHeight(30)
        self.clicked.connect(self._pick)

    def show_color(self, value, editable):
        self.value = value
        self.setText(f"{self.label}  {value}")
        self.setEnabled(editable)
        self.setToolTip("" if editable else tr("Built-in themes can't be changed. Make a new one."))
        text = "#000000" if QColor(value).lightnessF() > 0.55 else "#ffffff"
        self.setStyleSheet(f"QPushButton {{ background: {value}; color: {text}; }}")

    def _pick(self):
        color = QColorDialog.getColor(QColor(self.value), self, self.label)
        if color.isValid():
            self.picked.emit(self.key, color.name())


class ThemesDialog(QDialog):
    def __init__(self, parent=None, folder=None):
        super().__init__(parent)
        self.folder = folder
        self.theme_manager = manager()
        self.setWindowTitle(tr("Themes"))
        self.resize(820, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(
            header(
                tr("Themes"),
                tr("Choose the colors of the Makebench window. Your apps keep their own look."),
            )
        )
        split = QSplitter()
        left = QWidget()
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setItemDelegate(TwoLineDelegate(self.list))
        self.list.currentItemChanged.connect(self._show)
        column.addWidget(self.list, 1)
        new = QPushButton(tr("New theme…"))
        new.clicked.connect(self._new)
        load = QPushButton(tr("Import…"))
        load.clicked.connect(self._import)
        column.addLayout(button_row(new, load))
        split.addWidget(left)
        right = QWidget()
        side = QVBoxLayout(right)
        side.setContentsMargins(8, 0, 0, 0)
        top = QHBoxLayout()
        self.title = QLabel()
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        top.addWidget(self.title, 1)
        self.mode = QComboBox()
        self.mode.addItems([tr("Dark"), tr("Light")])
        self.mode.setCurrentIndex(0 if self.theme_manager.tokens.get("dark") else 1)
        self.mode.currentIndexChanged.connect(self._show)
        top.addWidget(self.mode)
        side.addLayout(top)
        self.about = make_muted(QLabel())
        self.about.setWordWrap(True)
        side.addWidget(self.about)
        self.preview = ThemePreview()
        side.addWidget(self.preview, 1)
        side.addWidget(QLabel(tr("Theme colors")))
        grid = QGridLayout()
        self.swatches = {}
        for index, (key, label) in enumerate(color_names()):
            swatch = Swatch(key, label)
            swatch.picked.connect(self._change_color)
            grid.addWidget(swatch, index // 4, index % 4)
            self.swatches[key] = swatch
        side.addLayout(grid)
        note = make_muted(
            QLabel(tr("A theme is a simple JSON file (.mbtheme) you can share with other people."))
        )
        note.setWordWrap(True)
        side.addWidget(note)
        self.apply_button = QPushButton()
        self.apply_button.clicked.connect(self._apply)
        self.export_button = QPushButton(tr("Export .mbtheme…"))
        self.export_button.clicked.connect(self._export)
        folder_button = QPushButton(tr("Open themes folder"))
        folder_button.clicked.connect(self._open_folder)
        side.addLayout(button_row(self.apply_button, trailing=[self.export_button, folder_button]))
        split.addWidget(right)
        split.setSizes([260, 560])
        layout.addWidget(split, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._fill()

    def _in_use(self, name) -> bool:
        if name == DESKTOP:
            return self.theme_manager.look == "native"
        return self.theme_manager.look == "makebench" and name == self.theme_manager.color_theme

    def _fill(self, select=None):
        self.themes = {theme["name"]: theme for theme in themes.installed(self.folder)}
        current = select or (
            DESKTOP if self.theme_manager.look == "native" else self.theme_manager.color_theme
        )
        self.list.clear()
        rows = [(name, theme["path"]) for name, theme in self.themes.items()]
        rows.append((DESKTOP, None))
        for name, path in rows:
            kind = tr("Built-in") if path is None else tr("Yours")
            if name == DESKTOP:
                kind = tr("Follows your desktop")
            detail = kind + (" · " + tr("In use") if self._in_use(name) else "")
            item = QListWidgetItem(tr("Desktop colors") if name == DESKTOP else name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setData(DETAIL_ROLE, detail)
            self.list.addItem(item)
            if name == current:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None:
            self.list.setCurrentRow(0)

    def _current(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _show(self, *_):
        name = self._current()
        if name is None:
            return
        self.apply_button.setText(tr("In use") if self._in_use(name) else tr("Apply"))
        self.apply_button.setEnabled(not self._in_use(name))
        theme = self.themes.get(name)
        desktop = theme is None
        self.export_button.setEnabled(not desktop)
        self.mode.setEnabled(not desktop)
        for swatch in self.swatches.values():
            swatch.setVisible(not desktop)
        if desktop:
            self.title.setText(tr("Desktop colors"))
            self.about.setText(tr("Uses your system's palette, as in other KDE or GNOME apps."))
            self.preview.show_theme(None, "")
            return
        self.title.setText(theme["name"])
        about = theme.get("about", "")
        if theme["path"] is None:
            about = tr("The default theme: sober, dense and at home among Qt programs.")
        self.about.setText(about)
        colors = theme["dark" if self.mode.currentIndex() == 0 else "light"]
        self.preview.show_theme(colors, theme["accent"])
        editable = theme["path"] is not None
        for key, swatch in self.swatches.items():
            swatch.show_color(theme["accent"] if key == "accent" else colors[key], editable)

    def _clean(self, theme):
        return {key: value for key, value in theme.items() if key != "path"}

    def _change_color(self, key, value):
        theme = self.themes.get(self._current())
        if theme is None or theme["path"] is None:
            return
        if key == "accent":
            theme["accent"] = value
        else:
            theme["dark" if self.mode.currentIndex() == 0 else "light"][key] = value
        try:
            themes.save(theme["path"], self._clean(theme))
        except (themes.ThemeError, OSError) as exc:
            show_error(self, exc, tr("Save theme"))
            return
        if self._in_use(theme["name"]):
            self.theme_manager.apply()
        self._show()

    def _apply(self):
        name = self._current()
        if name == DESKTOP:
            self.theme_manager.set_look("native")
        elif name is not None:
            self.theme_manager.set_color_theme(name)
        self._fill(select=name)

    def _new(self):
        base = self.themes.get(self._current()) or self.themes[themes.BUILTIN["name"]]
        name, ok = QInputDialog.getText(
            self, tr("New theme"), tr("Name:"), text=tr("{name} copy").format(name=base["name"])
        )
        if not ok or not name.strip():
            return
        theme = {**self._clean(base), "name": name.strip(), "about": ""}
        if theme["name"] in self.themes:
            show_error(self, tr("There is already a theme with this name."), tr("New theme"))
            return
        try:
            themes.add(theme, self.folder)
        except (themes.ThemeError, OSError) as exc:
            show_error(self, exc, tr("New theme"))
            return
        self._fill(select=theme["name"])

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Import theme"), "", tr("Makebench themes (*.mbtheme)")
        )
        if not path:
            return
        try:
            theme = themes.import_theme(path, self.folder)
        except (themes.ThemeError, OSError) as exc:
            show_error(self, exc, tr("Import theme"))
            return
        self._fill(select=theme["name"])

    def _export(self):
        theme = self.themes.get(self._current())
        if theme is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export theme"),
            f"{themes.slug(theme['name'])}.mbtheme",
            tr("Makebench themes (*.mbtheme)"),
        )
        if not path:
            return
        try:
            themes.save(path, self._clean(theme))
        except (themes.ThemeError, OSError) as exc:
            show_error(self, exc, tr("Export theme"))

    def _open_folder(self):
        folder = self.folder or themes.user_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
