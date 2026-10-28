# SPDX-License-Identifier: MIT
"""Makebench's Qt visual identity, with the desktop's contrast and accent."""

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory
from makebench.i18n import tr

ACCENTS = {
    "system": None,
    "blue": "#3584e4",
    "green": "#26a269",
    "yellow": "#e5a50a",
    "red": "#c01c28",
    "purple": "#9141ac",
    "pink": "#d56199",
    "gray": "#77767b",
}
PALETTES = {
    "light": dict(
        canvas="#e7edf5",
        panel="#f5f7fb",
        raised="#ffffff",
        header="#ffffff",
        sidebar="#f0f3f8",
        border="#d3dce9",
        control="#72819a",
        text="#202a3a",
        muted="#52617a",
        accent="#2968c6",
        fill="#2968c6",
        on_accent="#ffffff",
        success="#187346",
        warning="#805b00",
        error="#b82e38",
        info="#245eb5",
        guide="#8545a0",
        hover="#e8edf5",
        selection="#dce8fb",
    ),
    "dark": dict(
        canvas="#121720",
        panel="#1d2430",
        raised="#283244",
        header="#202937",
        sidebar="#19212d",
        border="#39465d",
        control="#8293af",
        text="#e8eef8",
        muted="#a9b8d0",
        accent="#82b1ff",
        fill="#82b1ff",
        on_accent="#132136",
        success="#8ff0a4",
        warning="#f8e45c",
        error="#ff9393",
        info="#a0c4ff",
        guide="#e1a2ee",
        hover="#303c50",
        selection="#2d405c",
    ),
}


def contrast(first, second):
    """WCAG ratio of two sRGB colors for text and interactive boundaries."""

    def luminance(value):
        """Linearize sRGB channels before combining them by luminance."""
        c = QColor(value)
        channels = [c.redF(), c.greenF(), c.blueF()]
        return sum(
            (v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) * w
            for v, w in zip(channels, (0.2126, 0.7152, 0.0722))
        )

    a, b = sorted((luminance(first), luminance(second)))
    return (b + 0.05) / (a + 0.05)


def blend(first, second, amount):
    """Mix colors without compositor-dependent transparency."""
    a, b = QColor(first), QColor(second)
    return QColor(
        *[round(x * (1 - amount) + y * amount) for x, y in zip(a.getRgb()[:3], b.getRgb()[:3])]
    ).name()


def legible(color, backgrounds, ratio):
    """Adjust lightness minimally until the required contrast is reached."""
    if all(contrast(color, b) >= ratio for b in backgrounds):
        return QColor(color).name()
    target = max(("#000000", "#ffffff"), key=lambda c: min(contrast(c, b) for b in backgrounds))
    for step in range(1, 101):
        candidate = blend(color, target, step / 100)
        if all(contrast(candidate, b) >= ratio for b in backgrounds):
            return candidate
    return target


LOOKS = ("makebench", "native")


def look_tokens(theme, dark):
    """Tokens for one of Makebench's own color themes (`.mbtheme`), same keys as native."""
    c = theme["dark" if dark else "light"]
    base = PALETTES["dark" if dark else "light"]
    t = {
        "dark": dark,
        # The creation area sits a step below the window; panel headers a step above it.
        "canvas": blend(c["win"], "#000000", 0.12 if dark else 0.08),
        "panel": c["win"],
        "raised": c["base"],
        "header": blend(c["win"], c["fg"], 0.035),
        "sidebar": c["side"],
        "border": c["line"],
        "button": c["btn"],
        "button_border": c["btnLine"],
        "text": c["fg"],
        "system_accent": theme["accent"],
    }
    surfaces = [t["panel"], t["raised"], t["sidebar"], t["button"]]
    t["accent"] = legible(theme["accent"], [t["panel"], t["raised"]], 3)
    t["accent_adjusted"] = t["accent"] != theme["accent"]
    t["fill"] = t["accent"]
    t["on_accent"] = max(("#ffffff", "#000000"), key=lambda v: contrast(v, t["fill"]))
    t["muted"] = legible(c["mut"], surfaces, 4.5)
    t["control"] = legible(c["btnLine"], [t["panel"], t["raised"]], 3)
    for key in ("success", "warning", "error", "guide"):
        t[key] = legible(base[key], surfaces, 4.5)
    t["info"] = legible(t["accent"], surfaces, 4.5)
    t["hover"] = blend(t["panel"], t["text"], 0.07)
    t["selection"] = blend(t["panel"], t["accent"], 0.25)
    t["pressed"] = blend(t["accent"], t["on_accent"], 0.15)
    return t


def look_palette(t):
    """A complete QPalette for the tokens, so every native style draws with them."""
    p = QPalette()
    disabled = blend(t["text"], t["panel"], 0.55)
    roles = {
        "Window": t["panel"],
        "WindowText": t["text"],
        "Base": t["raised"],
        "AlternateBase": t["sidebar"],
        "Text": t["text"],
        "Button": t["button"],
        "ButtonText": t["text"],
        "BrightText": "#ffffff",
        "Highlight": t["fill"],
        "HighlightedText": t["on_accent"],
        "PlaceholderText": t["muted"],
        "ToolTipBase": t["button"],
        "ToolTipText": t["text"],
        "Link": t["info"],
        "LinkVisited": t["guide"],
        "Light": blend(t["button"], "#ffffff", 0.12),
        "Midlight": blend(t["button"], t["button_border"], 0.5),
        "Mid": t["border"],
        "Dark": blend(t["panel"], "#000000", 0.35),
        "Shadow": blend(t["panel"], "#000000", 0.6),
    }
    if hasattr(QPalette.ColorRole, "Accent"):
        roles["Accent"] = t["fill"]
    for name, value in roles.items():
        p.setColor(getattr(QPalette.ColorRole, name), QColor(value))
    for name in ("WindowText", "Text", "ButtonText", "PlaceholderText"):
        p.setColor(
            QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, name), QColor(disabled)
        )
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(t["border"]))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(t["text"]))
    return p


def derive_tokens(palette, dark=False, accent="system", system_surfaces=True):
    """Produce testable tokens without changing the desktop QPalette or the document."""
    t = dict(PALETTES["dark" if dark else "light"], dark=dark)
    if system_surfaces:
        window = palette.color(QPalette.ColorRole.Window).name()
        text = palette.color(QPalette.ColorRole.WindowText).name()
        is_dark = QColor(window).lightnessF() < 0.45
        if is_dark == dark and contrast(text, window) >= 4.5:
            base = palette.color(QPalette.ColorRole.Base).name()
            t.update(
                panel=window, text=text, raised=base if contrast(text, base) >= 4.5 else t["raised"]
            )
    raw = ACCENTS.get(accent)
    if raw is None:
        for role in (
            getattr(QPalette.ColorRole, "Accent", QPalette.ColorRole.Highlight),
            QPalette.ColorRole.Highlight,
        ):
            value = palette.color(role)
            if value.isValid() and contrast(value.name(), t["panel"]) > 1.1:
                raw = value.name()
                break
    raw = raw or ACCENTS["blue"]
    t["system_accent"] = raw
    t["accent"] = legible(raw, [t["panel"], t["raised"]], 3)
    t["accent_adjusted"] = QColor(raw).name() != t["accent"]
    t["fill"] = t["accent"]
    t["on_accent"] = max(("#ffffff", "#000000"), key=lambda c: contrast(c, t["fill"]))
    for key in ("muted", "success", "warning", "error", "info", "guide"):
        t[key] = legible(
            t["accent"] if key == "info" else t[key], [t["panel"], t["raised"], t["canvas"]], 4.5
        )
    t["control"] = legible(t["control"], [t["panel"], t["raised"]], 3)
    t["hover"] = blend(t["panel"], t["text"], 0.07)
    t["selection"] = blend(t["panel"], t["accent"], 0.15)
    t["pressed"] = blend(t["accent"], t["on_accent"], 0.15)
    return t


class ThemeManager(QObject):
    """Makebench's own colors by default, or the desktop's palette; never a global stylesheet.

    The native look keeps the desktop's widget style (Breeze, Fusion…). The Makebench look
    draws with Fusion, because Breeze paints menu and tool bars in the desktop's header
    colors whatever the palette says, which left dark bars with dark text in light mode.
    """

    changed = Signal(dict)

    def __init__(self, app):
        """Keep the desktop's choices; Breeze is the native fallback in a KDE session."""
        import os

        super().__init__(app)
        self.app = app
        self._applying = False
        self.settings = QSettings("Makebench", "Makebench")
        self.base_font = QFont(app.font())
        if (
            app.platformName() != "offscreen"
            and "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "")
            and app.style().objectName().lower() == "fusion"
            and not os.environ.get("QT_STYLE_OVERRIDE")
            and "Breeze" in QStyleFactory.keys()
        ):
            app.setStyle(QStyleFactory.create("Breeze"))
        self.native_style = app.style().name()
        self.system_palette = QPalette(app.palette())
        self.mode = "system"
        self.accent = "system"
        self.look = self.settings.value("v1/appearance/look", "makebench")
        if self.look not in LOOKS:
            self.look = "makebench"
        self.color_theme = self.settings.value("v1/appearance/color_theme", "Makebench")
        self.scale = 100
        self.reduce_motion = False
        if not self.settings.value("v2/native_theme", False, type=bool):
            self.settings.setValue("v1/appearance/theme", "system")
            self.settings.setValue("v1/appearance/accent", "system")
            self.settings.setValue("v2/native_theme", True)
        app.styleHints().colorSchemeChanged.connect(lambda _: self.apply())
        app.paletteChanged.connect(self.palette_changed)
        self.apply()

    def repair_bar_palette(self, widget):
        """Use only native colors to repair illegible text in Qt/KDE headers."""
        native = self.app.palette()
        # Breeze can combine the application background with the header palette text.
        # The application's full palette keeps those roles consistent.
        if widget.palette() != native:
            widget.setPalette(native)

    def palette_changed(self, palette):
        """Follow real desktop changes while the application is open."""
        if self._applying or self.look != "native":
            return
        self.system_palette = QPalette(palette)
        self.apply()

    def set_mode(self, mode):
        """Ask the Qt platform for the scheme; the Makebench look follows the same choice."""
        if mode not in {"system", "light", "dark"}:
            raise ValueError(tr("Unknown theme"))
        self.mode = mode
        self.settings.setValue("v1/appearance/theme", mode)
        self.app.styleHints().setColorScheme(
            {
                "system": Qt.ColorScheme.Unknown,
                "light": Qt.ColorScheme.Light,
                "dark": Qt.ColorScheme.Dark,
            }[mode]
        )
        self.apply()

    def set_accent(self, _value):
        """The accent belongs to the system theme, as the author requested."""
        self.accent = "system"
        self.settings.setValue("v1/appearance/accent", "system")
        self.apply()

    def apply(self):
        """Set the palette for the chosen look and publish tokens for canvas, maps and syntax."""
        if self._applying:
            return
        self._applying = True
        p = self.system_palette
        previous = getattr(self, "tokens", None)
        if self.app.styleSheet():
            self.app.setStyleSheet("")
        role = lambda name: p.color(getattr(QPalette.ColorRole, name)).name()
        dark = p.color(QPalette.ColorRole.Window).lightnessF() < 0.45
        wanted = "fusion" if self.look == "makebench" else self.native_style
        if self.app.style().name().lower() != wanted.lower():
            self.app.setStyle(QStyleFactory.create(wanted))
        if self.look == "makebench":
            scheme = self.app.styleHints().colorScheme()
            if self.mode != "system":
                dark = self.mode == "dark"
            elif scheme != Qt.ColorScheme.Unknown:
                dark = scheme == Qt.ColorScheme.Dark
            t = look_tokens(self.selected_theme(), dark)
            palette = look_palette(t)
            if self.app.palette() != palette:
                self.app.setPalette(palette)
            # Fusion fills check boxes with Base, which vanishes on dark cards.
            box = QPalette(palette)
            if t["dark"]:
                box.setColor(QPalette.ColorRole.Base, QColor(blend(t["raised"], t["text"], 0.24)))
            for name in ("QCheckBox", "QRadioButton"):
                self.app.setPalette(box, name)
            self._class_palettes = True
        else:
            if self.app.palette().resolveMask():
                # Back from the Makebench look: an empty palette returns to the desktop's.
                self.app.setPalette(QPalette())
                self.system_palette = p = QPalette(self.app.palette())
            if getattr(self, "_class_palettes", False):
                # Desktop colors are never replaced; only undo our own check box tint.
                for name in ("QCheckBox", "QRadioButton"):
                    self.app.setPalette(self.app.palette(), name)
                self._class_palettes = False
            t = None
        self.tokens = t = t or {
            "dark": dark,
            "canvas": role("AlternateBase"),
            "panel": role("Window"),
            "raised": role("Base"),
            "header": role("Window"),
            "sidebar": role("Window"),
            "border": role("Mid"),
            "control": role("Mid"),
            "text": role("WindowText"),
            "muted": role("PlaceholderText"),
            "accent": role("Highlight"),
            "fill": role("Highlight"),
            "on_accent": role("HighlightedText"),
            "success": role("Link"),
            "warning": role("LinkVisited"),
            "error": role("LinkVisited"),
            "info": role("Link"),
            "guide": role("Link"),
            "hover": role("AlternateBase"),
            "selection": role("Highlight"),
            "pressed": role("Highlight"),
            "system_accent": role("Highlight"),
            "accent_adjusted": False,
        }
        t["look"] = self.look
        font = QFont(self.look_font() if self.look == "makebench" else self.base_font)
        font.setPointSizeF(max(8, font.pointSizeF()) * self.scale / 100)
        font_changed = self.app.font() != font
        if font_changed:
            self.app.setFont(font)
        for effect in (
            Qt.UIEffect.UI_AnimateMenu,
            Qt.UIEffect.UI_FadeMenu,
            Qt.UIEffect.UI_AnimateCombo,
            Qt.UIEffect.UI_AnimateTooltip,
            Qt.UIEffect.UI_FadeTooltip,
        ):
            self.app.setEffectEnabled(effect, not self.reduce_motion)
        self._applying = False
        if previous != t or font_changed:
            self.changed.emit(t)

    def selected_theme(self):
        """The chosen `.mbtheme`; the built-in one when it is missing or broken."""
        from . import themes

        for theme in themes.installed():
            if theme["name"] == self.color_theme:
                return theme
        return themes.validate(themes.BUILTIN)

    def look_font(self):
        """Noto Sans at the desktop's size when installed, otherwise the desktop font."""
        from PySide6.QtGui import QFontDatabase

        font = QFont(self.base_font)
        if "Noto Sans" in QFontDatabase.families():
            font.setFamily("Noto Sans")
        return font

    def set_color_theme(self, name):
        """Use one of the installed `.mbtheme` files with Makebench's own look."""
        self.color_theme = name
        self.settings.setValue("v1/appearance/color_theme", name)
        self.set_look("makebench")

    def set_look(self, look):
        """Switch between Makebench's colors and the desktop's palette."""
        if look not in LOOKS:
            raise ValueError(tr("Unknown theme"))
        self.look = look
        self.settings.setValue("v1/appearance/look", look)
        self.apply()


def manager():
    """Single service, also available in direct widget tests."""
    app = QApplication.instance()
    if not hasattr(app, "makebench_theme"):
        app.makebench_theme = ThemeManager(app)
    return app.makebench_theme


def icon(name):
    """Prefer system symbols and use our own vectors as a recolored fallback."""
    aliases = {
        "new": "document-new-symbolic",
        "open": "document-open-symbolic",
        "save": "document-save-symbolic",
        "undo": "edit-undo-symbolic",
        "redo": "edit-redo-symbolic",
        "run": "media-playback-start-symbolic",
        "stop": "media-playback-stop-symbolic",
        "home": "go-home-symbolic",
        "search": "edit-find-symbolic",
        "add": "list-add-symbolic",
        "remove": "list-remove-symbolic",
        "save-as": "document-save-as-symbolic",
        "quit": "application-exit-symbolic",
        "duplicate": "edit-copy-symbolic",
        "move-up": "go-up-symbolic",
        "move-down": "go-down-symbolic",
        "about": "help-about-symbolic",
        "help": "help-contents-symbolic",
        "keyboard": "input-keyboard-symbolic",
    }
    themed = QIcon.fromTheme(aliases.get(name, name))
    if not themed.isNull():
        from PySide6.QtGui import QPainter, QPixmap

        color = QColor(manager().tokens["text"])
        result = QIcon()
        for size in (16, 20, 24, 32, 48, 64):
            pix = themed.pixmap(size, size)
            painter = QPainter(pix)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(pix.rect(), color)
            painter.end()
            result.addPixmap(pix)
        return result
    from .icons import vector_icon

    return vector_icon(name)
