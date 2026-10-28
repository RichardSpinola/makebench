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
    if style["text"]:
        rules.append(f'#{name} *[mbChart="true"] {{ color: {style["text"]}; }}')
    if style["accent"]:
        rules.append(f'#{name} *[mbChart="true"] {{ qproperty-accent: "{style["accent"]}"; }}')
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


# Per-component look: flat optional properties, so states, copy and paste stay simple.
STYLE_KEYS = (
    "style_color",
    "style_background",
    "style_font_size",
    "style_bold",
    "style_italic",
    "style_radius",
)
FONT_SIZES = (1, 96)
RADII = (0, 48)


def style_error(properties):
    """The first invalid style key, or None; empty colors and zero sizes mean "default"."""
    for key in ("style_color", "style_background"):
        value = properties.get(key, "")
        if value and not valid_color(value):
            return key
    size = properties.get("style_font_size", 0)
    if type(size) is not int or size and not FONT_SIZES[0] <= size <= FONT_SIZES[1]:
        return "style_font_size"
    radius = properties.get("style_radius", 0)
    if type(radius) is not int or not RADII[0] <= radius <= RADII[1]:
        return "style_radius"
    for key in ("style_bold", "style_italic"):
        if type(properties.get(key, False)) is not bool:
            return key
    return None


def component_style(properties):
    """Only the style values that change something; invalid values are dropped."""
    if style_error(properties):
        return {}
    return {key: properties[key] for key in STYLE_KEYS if properties.get(key)}


def _text_rules(style, css):
    """Color and font declarations, written the same way for Qt and GTK."""
    rules = []
    if style.get("style_color"):
        rules.append(f"color: {style['style_color']};")
    if style.get("style_font_size"):
        rules.append(f"font-size: {style['style_font_size']}pt;")
    if style.get("style_bold"):
        rules.append("font-weight: bold;")
    if style.get("style_italic"):
        rules.append("font-style: italic;")
    return " ".join(rules)


def _box_rules(style, css):
    """Background and rounded corners; GTK needs the shorthand to drop theme gradients."""
    rules = []
    if style.get("style_background"):
        name = "background" if css else "background-color"
        rules.append(f"{name}: {style['style_background']};")
    if style.get("style_radius"):
        rules.append(f"border-radius: {style['style_radius']}px;")
    return " ".join(rules)


def component_qss(properties, container=False):
    """Stylesheet set on the component's own widget, marked with mbOwn="true".

    Qt does not pass color and font to children, so a container repeats them for its
    contents; a child with its own style still wins, because its sheet is closer.
    """
    style = component_style(properties)
    if not style:
        return ""
    own = '*[mbOwn="true"]'
    text, box = _text_rules(style, False), _box_rules(style, False)
    rules = []
    if text and container:
        rules.append(f"{own} QLabel, {own} QCheckBox, {own} QPushButton {{ {text} }}")
    if text or box:
        rules.append(f"{own} {{ {text} {box} }}".replace("  ", " "))
    return "\n".join(rules)


def gtk_component_css(properties, scope, name):
    """CSS for the widget with class ``name`` inside the window with class ``scope``."""
    style = component_style(properties)
    if not style:
        return ""
    text, box = _text_rules(style, True), _box_rules(style, True)
    rules = []
    if text:
        rules.append(f".{scope} .{name}, .{scope} .{name} label {{ {text} }}")
    if box:
        rules.append(f".{scope} .{name} {{ {box} }}")
    return "\n".join(rules)
