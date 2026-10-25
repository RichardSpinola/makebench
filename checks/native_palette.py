# SPDX-License-Identifier: GPL-3.0-or-later
"""QA palettes read from the installed KDE schemes; not product code."""

import configparser
from pathlib import Path
from PySide6.QtGui import QColor, QPalette


def kde_palette(name):
    """Load the real BreezeLight/Dark to simulate the desktop in offscreen Qt."""
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
