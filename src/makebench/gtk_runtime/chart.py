# SPDX-License-Identifier: MIT
"""GTK 4 chart drawn with cairo from the shapes of ``core.chart``."""

import math

from makebench.core.chart import layout, series_color


def hex_rgb(color):
    """(r, g, b) between 0 and 1 for a #rrggbb color."""
    return tuple(int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))


def draw(cr, width, height, chart, ink):
    """Paint ``chart`` (an object with type, title, labels, values and accent) on ``cr``."""
    cr.set_font_size(11)
    for shape in layout(chart.type, chart.title, chart.labels, chart.values, width, height):
        kind = shape[0]
        if kind == "text":
            _, x, y, text, align, role = shape
            cr.select_font_face(
                "sans-serif", 0, 1 if role == "title" else 0
            )  # slant normal, weight bold for the title
            cr.set_source_rgba(*ink)
            extents = cr.text_extents(text)
            left = x - (
                extents.x_advance / 2
                if align == "center"
                else extents.x_advance
                if align == "right"
                else 0
            )
            cr.move_to(left, y + 4)
            cr.show_text(text)
        elif kind == "axis":
            cr.set_source_rgba(*ink[:3], 0.45)
            cr.set_line_width(1)
            cr.move_to(shape[1], shape[2])
            cr.line_to(shape[3], shape[4])
            cr.stroke()
        elif kind == "rect":
            cr.set_source_rgb(*hex_rgb(series_color(shape[5], chart.accent)))
            cr.rectangle(*shape[1:5])
            cr.fill()
        elif kind == "line":
            cr.set_source_rgb(*hex_rgb(series_color(shape[2], chart.accent)))
            cr.set_line_width(2)
            for index, (x, y) in enumerate(shape[1]):
                (cr.move_to if index == 0 else cr.line_to)(x, y)
            cr.stroke()
        elif kind == "dot":
            cr.set_source_rgb(*hex_rgb(series_color(shape[3], chart.accent)))
            cr.arc(shape[1], shape[2], 3.5, 0, 2 * math.pi)
            cr.fill()
        elif kind == "slice":
            _, cx, cy, radius, start, span, color = shape
            cr.set_source_rgb(*hex_rgb(series_color(color, chart.accent)))
            cr.move_to(cx, cy)
            # Layout angles run counterclockwise; cairo's y axis points down.
            begin, end = -math.radians(start), -math.radians(start + span)
            (cr.arc if span < 0 else cr.arc_negative)(cx, cy, radius, begin, end)
            cr.close_path()
            cr.fill()
