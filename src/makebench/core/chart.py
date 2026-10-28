# SPDX-License-Identifier: MIT
"""Chart geometry with no graphical dependency, drawn by Qt and by GTK from the same shapes.

``layout`` turns a chart type and its data into plain shapes in pixels, so both toolkits
paint the same picture and the geometry can be tested without a screen.
"""

import math

CHART_TYPES = ("bar", "line", "pie")
SAMPLE_LABELS = ["A", "B", "C", "D"]
SAMPLE_VALUES = [3, 5, 2, 4]
SERIES = ["#3584e4", "#33d17a", "#f6d32d", "#ff7800", "#e01b24", "#9141ac", "#986a44", "#5e5c64"]
MAX_POINTS = 500


def series_color(index, accent=""):
    """Color of the nth bar or slice; the accent of the window replaces the first one."""
    return accent if index == 0 and accent else SERIES[index % len(SERIES)]


def nice_ceiling(top):
    """Round a positive maximum up to 1, 2, 5 times a power of ten, for the value axis."""
    if top <= 0:
        return 1
    scale = 10 ** math.floor(math.log10(top))
    for step in (1, 2, 5, 10):
        if top <= step * scale:
            return step * scale
    return 10 * scale


def format_number(value):
    """Short text for an axis or a slice: no trailing .0."""
    return f"{value:.4g}"


def layout(chart_type, title, labels, values, width, height):
    """Shapes for one chart in a ``width`` x ``height`` area.

    Each shape is a tuple: ``("text", x, y, text, align, role)`` (align left/center/right
    around the middle of y; role title/label/value), ``("rect", x, y, w, h, color)``,
    ``("line", [(x, y), ...], color)``, ``("dot", x, y, color)``,
    ``("axis", x1, y1, x2, y2)`` and ``("slice", cx, cy, radius, start, span, color)``
    with angles in degrees, counterclockwise from 3 o'clock. A color is a series index.
    """
    shapes = []
    pairs = list(zip(labels, values))[:MAX_POINTS]
    top = 6
    if title:
        shapes.append(("text", width / 2, 12, title, "center", "title"))
        top = 28
    if not pairs or width < 60 or height < 60:
        return shapes
    if chart_type == "pie":
        return shapes + pie(pairs, width, height, top)
    return shapes + plot(chart_type, pairs, width, height, top)


def plot(chart_type, pairs, width, height, top):
    """Axes, bars or a line with points."""
    shapes = []
    left, right, bottom = 44, 10, height - 22
    ceiling = nice_ceiling(max([0, *(v for _, v in pairs)]))
    low = min(0, *(v for _, v in pairs))
    if low < 0:
        ceiling_low = -nice_ceiling(-low)
    else:
        ceiling_low = 0
    span = ceiling - ceiling_low

    def y_of(value):
        """Vertical position of a value between the floor and the ceiling."""
        return bottom - (value - ceiling_low) / span * (bottom - top)

    for tick in sorted({ceiling_low, 0, ceiling}):
        shapes.append(("text", left - 6, y_of(tick), format_number(tick), "right", "value"))
    shapes.append(("axis", left, top, left, bottom))
    shapes.append(("axis", left, y_of(0), width - right, y_of(0)))
    slot = (width - left - right) / len(pairs)
    points = []
    for index, (label, value) in enumerate(pairs):
        middle = left + slot * (index + 0.5)
        if chart_type == "bar":
            body = slot * 0.7
            shapes.append(
                (
                    "rect",
                    middle - body / 2,
                    min(y_of(value), y_of(0)),
                    body,
                    abs(y_of(value) - y_of(0)),
                    index,
                )
            )
        else:
            points.append((middle, y_of(value)))
        shapes.append(("text", middle, height - 10, str(label), "center", "label"))
    if points:
        shapes.append(("line", points, 0))
        shapes.extend(("dot", x, y, 0) for x, y in points)
    return shapes


def pie(pairs, width, height, top):
    """Slices with a legend on the right; negative values count as zero."""
    shapes = []
    amounts = [max(0, v) for _, v in pairs]
    total = sum(amounts)
    legend = min(110, width * 0.35)
    radius = max(10, min(width - legend - 20, height - top - 10) / 2)
    cx, cy = 10 + radius, top + (height - top) / 2
    start = 90.0
    for index, amount in enumerate(amounts):
        if total and amount:
            span = -360.0 * amount / total
            shapes.append(("slice", cx, cy, radius, start, span, index))
            start += span
    x = cx + radius + 16
    for index, (label, value) in enumerate(pairs[:12]):
        y = top + 8 + index * 18
        shapes.append(("rect", x, y - 5, 10, 10, index))
        shapes.append(("text", x + 16, y, f"{label} ({format_number(value)})", "left", "label"))
    return shapes
