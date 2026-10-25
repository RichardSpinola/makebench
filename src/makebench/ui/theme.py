"""Identidade visual Qt do Makebench, com contraste e destaque do desktop."""

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

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
    """Razão WCAG de duas cores sRGB para texto e limites interativos."""

    def luminance(value):
        """Lineariza os canais sRGB antes da combinação por luminância."""
        c = QColor(value)
        channels = [c.redF(), c.greenF(), c.blueF()]
        return sum(
            (v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) * w
            for v, w in zip(channels, (0.2126, 0.7152, 0.0722))
        )

    a, b = sorted((luminance(first), luminance(second)))
    return (b + 0.05) / (a + 0.05)


def blend(first, second, amount):
    """Mistura cores sem transparência dependente do compositor."""
    a, b = QColor(first), QColor(second)
    return QColor(
        *[round(x * (1 - amount) + y * amount) for x, y in zip(a.getRgb()[:3], b.getRgb()[:3])]
    ).name()


def legible(color, backgrounds, ratio):
    """Ajusta luminosidade minimamente até atingir o contraste requerido."""
    if all(contrast(color, b) >= ratio for b in backgrounds):
        return QColor(color).name()
    target = max(("#000000", "#ffffff"), key=lambda c: min(contrast(c, b) for b in backgrounds))
    for step in range(1, 101):
        candidate = blend(color, target, step / 100)
        if all(contrast(candidate, b) >= ratio for b in backgrounds):
            return candidate
    return target


def derive_tokens(palette, dark=False, accent="system", system_surfaces=True):
    """Produz tokens testáveis sem alterar QPalette do desktop ou o documento."""
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
    """Usa o estilo e a paleta nativos de Qt/KDE, sem folha de estilos própria."""

    changed = Signal(dict)

    def __init__(self, app):
        """Preserva escolhas do desktop; Breeze é a reserva nativa em uma sessão KDE."""
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
        self.system_palette = QPalette(app.palette())
        self.mode = "system"
        self.accent = "system"
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
        """Usa só cores nativas para reparar texto ilegível de cabeçalhos Qt/KDE."""
        native = self.app.palette()
        # Breeze pode combinar fundo do app com texto da paleta de cabeçalho.
        # A paleta completa do aplicativo mantém esses roles coerentes.
        if widget.palette() != native:
            widget.setPalette(native)

    def palette_changed(self, palette):
        """Acompanha alterações reais do desktop enquanto o aplicativo está aberto."""
        if self._applying:
            return
        self.system_palette = QPalette(palette)
        self.apply()

    def set_mode(self, mode):
        """Solicita o esquema à plataforma Qt; não fabrica uma paleta substituta."""
        if mode not in {"system", "light", "dark"}:
            raise ValueError("Tema desconhecido")
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
        """Destaque pertence ao tema do sistema, como solicitado pelo autor."""
        self.accent = "system"
        self.settings.setValue("v1/appearance/accent", "system")
        self.apply()

    def apply(self):
        """Lê roles da paleta Qt para desenho do canvas, mapas e sintaxe."""
        if self._applying:
            return
        self._applying = True
        p = self.system_palette
        previous = getattr(self, "tokens", None)
        if self.app.styleSheet():
            self.app.setStyleSheet("")
        role = lambda name: p.color(getattr(QPalette.ColorRole, name)).name()
        dark = p.color(QPalette.ColorRole.Window).lightnessF() < 0.45
        self.tokens = t = {
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
        font = QFont(self.base_font)
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


def manager():
    """Serviço único também disponível em testes diretos dos widgets."""
    app = QApplication.instance()
    if not hasattr(app, "makebench_theme"):
        app.makebench_theme = ThemeManager(app)
    return app.makebench_theme


def icon(name):
    """Prefere símbolos do sistema e usa vetores próprios como reserva recolorida."""
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
