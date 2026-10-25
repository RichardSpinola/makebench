"""Paletas de QA lidas dos esquemas KDE instalados; não é código do produto."""

import configparser
from pathlib import Path
from PySide6.QtGui import QColor, QPalette


def kde_palette(name):
    """Carrega BreezeLight/Dark reais para simular o desktop no Qt offscreen."""
    file = Path("/usr/share/color-schemes") / (
        "BreezeDark.colors" if name == "dark" else "BreezeLight.colors"
    )
    if not file.exists():
        raise RuntimeError("QA de esquema exige arquivo KDE instalado: " + str(file))
    config = configparser.ConfigParser(interpolation=None)
    config.read(file)
    palette = QPalette()
    mapping = {
        "Window": ("Window", "BackgroundNormal"),
        "WindowText": ("Window", "ForegroundNormal"),
        "Base": ("View", "BackgroundNormal"),
        "AlternateBase": ("View", "BackgroundAlternate"),
        "Text": ("View", "ForegroundNormal"),
        "Button": ("Button", "BackgroundNormal"),
        "ButtonText": ("Button", "ForegroundNormal"),
        "Highlight": ("Selection", "BackgroundNormal"),
        "Accent": ("Selection", "BackgroundNormal"),
        "HighlightedText": ("Selection", "ForegroundNormal"),
        "ToolTipBase": ("Tooltip", "BackgroundNormal"),
        "ToolTipText": ("Tooltip", "ForegroundNormal"),
        "PlaceholderText": ("View", "ForegroundInactive"),
        "Link": ("View", "ForegroundLink"),
        "LinkVisited": ("View", "ForegroundVisited"),
        "Mid": ("Window", "ForegroundInactive"),
    }
    for role, (section, key) in mapping.items():
        if config.has_option("Colors:" + section, key):
            value = config.get("Colors:" + section, key)
            color = QColor(*map(int, value.split(",")[:3]))
            palette.setColor(getattr(QPalette.ColorRole, role), color)
    return palette
