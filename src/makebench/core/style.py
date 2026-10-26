# SPDX-License-Identifier: MIT
"""Per-window look: theme, accent and background, shared by the editor and the apps.

The values live in optional window properties (``theme``, ``accent``, ``background``), so
projects without them open and look exactly as before.
"""

import re

THEMES = ("system", "light", "dark")
_HEX = re.compile(r"#[0-9a-fA-F]{6}")

PALETTES = {
    "light": {"background": "#fafafa", "text": "#202020"},
    "dark": {"background": "#242424", "text": "#f0f0f0"},
}


def valid_color(value):
    """Accept only #rrggbb, so a value can never smuggle extra CSS into a stylesheet."""
    return isinstance(value, str) and bool(_HEX.fullmatch(value))


def window_style(properties):
    """Normalize the look of one window; unknown or invalid values fall back to the system."""
    theme = properties.get("theme", "system")
    if theme not in THEMES:
        theme = "system"
    accent = properties.get("accent", "")
    background = properties.get("background", "")
    palette = PALETTES.get(theme)
    return {
        "theme": theme,
        "accent": accent if valid_color(accent) else "",
        "background": background
        if valid_color(background)
        else (palette["background"] if palette else ""),
        "text": palette["text"] if palette else "",
    }


def is_default(style):
    """True when nothing needs to be applied."""
    return not any(style.values()) or style == {
        "theme": "system",
        "accent": "",
        "background": "",
        "text": "",
    }


def qt_stylesheet(style, name):
    """Stylesheet scoped to the widget called ``name``; it never reaches other windows."""
    if is_default(style):
        return ""
    rules = []
    if style["background"]:
        rules.append(f"#{name} {{ background-color: {style['background']}; }}")
    if style["text"]:
        rules.append(
            f"#{name} QLabel, #{name} QCheckBox {{ color: {style['text']}; }}"
            f"#{name} QLineEdit, #{name} QPlainTextEdit, #{name} QTextEdit "
            f"{{ background-color: {style['background']}; color: {style['text']}; }}"
        )
    if style["accent"]:
        rules.append(
            f"#{name} QPushButton {{ background-color: {style['accent']}; color: white; "
            "border: none; border-radius: 4px; padding: 5px 12px; }"
            f"#{name} QPushButton:disabled {{ background-color: #888888; }}"
            f"#{name} QProgressBar::chunk {{ background-color: {style['accent']}; }}"
        )
    return "\n".join(rules)


def gtk_css(style, name):
    """CSS for a GTK widget with the CSS name class ``name``."""
    if is_default(style):
        return ""
    rules = []
    if style["background"]:
        rules.append(f".{name} {{ background-color: {style['background']}; }}")
    if style["text"]:
        rules.append(f".{name} label, .{name} checkbutton {{ color: {style['text']}; }}")
    if style["accent"]:
        rules.append(
            f".{name} button {{ background: {style['accent']}; color: white; }}"
            f".{name} progressbar progress {{ background: {style['accent']}; }}"
        )
    return "\n".join(rules)
