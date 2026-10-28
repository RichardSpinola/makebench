# SPDX-License-Identifier: MIT
"""Our own vector symbols, with no external icon library dependency."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

PATHS = {
    "edit": '<path d="m4 16 12-12 4 4L8 20H4zM13 7l4 4"/>',
    "align-left": '<path d="M4 3v18M8 5h12v5H8zM8 14h8v5H8z"/>',
    "align-right": '<path d="M20 3v18M4 5h12v5H4zM8 14h8v5H8z"/>',
    "align-center": '<path d="M12 2v20M4 5h16v4H4zM7 15h10v4H7z"/>',
    "align-top": '<path d="M3 4h18M5 8h5v12H5zM14 8h5v8h-5z"/>',
    "align-bottom": '<path d="M3 20h18M5 4h5v12H5zM14 8h5v8h-5z"/>',
    "width": '<path d="M3 4v16M21 4v16M3 12h18M7 8l-4 4 4 4M17 8l4 4-4 4"/>',
    "height": '<path d="M4 3h16M4 21h16M12 3v18M8 7l4-4 4 4M8 17l4 4 4-4"/>',
    "distribute": '<path d="M3 3v18M21 3v18M9 6h6v12H9zM3 12h6M15 12h6"/>',
    "zoom-in": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 10h6M10 7v6"/>',
    "zoom-out": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 10h6"/>',
    "fit": '<path d="M3 9V3h6M15 3h6v6M21 15v6h-6M9 21H3v-6M7 7h10v10H7z"/>',
    "actual": '<path d="M6 7h2v10M14 7h2v10"/>',
    "trash": '<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
    "separator": '<path d="M3 12h18"/>',
    "spacer": '<path d="m3 12 4-4M3 12l4 4M3 12h18M21 12l-4-4M21 12l-4 4"/>',
    "settings": '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
    "pan": '<path d="M12 2v20M2 12h20M8 6l4-4 4 4M8 18l4 4 4-4M6 8l-4 4 4 4M18 8l4 4-4 4"/>',
    "map": '<rect x="2" y="3" width="7" height="6" rx="1"/><rect x="15" y="15" width="7" height="6" rx="1"/><path d="M6 9v9h9"/>',
    "logic": '<path d="M4 4h12v5h4v6h-4v5H4zM8 8h4M8 16h4"/>',
    "code": '<path d="m8 6-6 6 6 6M16 6l6 6-6 6M14 3l-4 18"/>',
    "export": '<path d="M12 16V2M7 7l5-5 5 5M4 13v8h16v-8"/>',
    "new": '<path d="M12 4v16M4 12h16"/>',
    "add": '<path d="M12 4v16M4 12h16"/>',
    "remove": '<path d="M4 12h16"/>',
    "run": '<path d="m7 4 13 8-13 8z"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="1"/>',
    "home": '<path d="m3 11 9-8 9 8M6 9v12h12V9M10 21v-7h4v7"/>',
    "open": '<path d="M3 8V5h7l3 3h8v12H3zM3 9h18"/>',
    "save": '<path d="M4 3h13l3 3v15H4zM8 3v6h8V3M8 21v-8h8v8"/>',
    "undo": '<path d="M4 10h10a6 6 0 0 1 0 12M4 10l5-5M4 10l5 5"/>',
    "float": '<path d="M9 3h12v10H9zM9 7h12M6 9H3v12h12v-4"/>',
    "close": '<path d="m6 6 12 12M18 6 6 18"/>',
    "redo": '<path d="M20 10H10a6 6 0 0 0 0 12M20 10l-5-5M20 10l-5 5"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    "select": '<path d="m5 3 13 10-7 1-3 7z"/>',
    "window": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M6 6.5h1M10 6.5h1"/>',
    "container": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 10h18M10 10v11"/>',
    "button": '<rect x="3" y="6" width="18" height="12" rx="3"/><path d="M8 12h8"/>',
    "label": '<path d="M4 5h16M12 5v15M8 20h8"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="2"/><path d="m3 17 6-6 5 5 3-3 4 4"/>',
    "text_input": '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 12h5M15 9v6"/>',
    "text_area": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 13h10M7 17h6"/>',
    "checkbox": '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="m7 12 3 3 7-7"/>',
    "number": '<rect x="3" y="7" width="18" height="10" rx="2"/><path d="m14 11 2 2 2-2"/><path d="M7 12h3"/>',
    "slider": '<path d="M4 12h16"/><circle cx="14" cy="12" r="3"/>',
    "progress": '<rect x="2" y="8" width="20" height="8" rx="2"/><path d="M5 11v2M8 11v2M11 11v2"/>',
    "output": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m6 9 3 3-3 3M12 15h5"/>',
    "pages": '<path d="M3 7h18v14H3zM3 7V3h7v4M10 3h7v4"/>',
    "pieces": '<path d="M12 3 4 7v10l8 4 8-4V7l-8-4z"/><path d="m4 7 8 4 8-4M12 11v10"/>',
    "history": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "plugins": '<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="13" width="8" height="8" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/><path d="M17 3v8M13 7h8"/>',
    "page": '<path d="M5 2h9l5 5v15H5zM14 2v6h5M8 12h8M8 16h8"/>',
    # Menu commands.
    "example": '<path d="M2 5h7a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H2zM22 5h-7a3 3 0 0 0-3 3v13a2 2 0 0 1 2-2h7z"/>',
    "save-as": '<path d="M12 21H4V3h13l3 3v5M8 3v6h8V3"/><path d="m14 21 1-3 5-5 2 2-5 5z"/>',
    "share": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/>',
    "git": '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/><path d="M6 7v10M18 9a6 6 0 0 1-6 6H8"/>',
    "start-window": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M10 12l5 3-5 3z"/>',
    "quit": '<path d="M14 4H5v16h9M10 12h11M17 8l4 4-4 4"/>',
    "duplicate": '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
    "move-up": '<path d="M12 20V4M6 10l6-6 6 6"/>',
    "move-down": '<path d="M12 4v16M6 14l6 6 6-6"/>',
    "align-middle": '<path d="M2 12h20M5 5h5v14H5zM14 8h5v8h-5z"/>',
    "piece-add": '<path d="M12 3 4 7v10l8 4 8-4V7z"/><path d="M12 8v8M8 12h8"/>',
    "panel-left": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
    "panel-right": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
    "panels": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>',
    "command": '<path d="M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z"/>',
    "focus": '<path d="M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5"/><circle cx="12" cy="12" r="3"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "components": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "data": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "properties": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 8h4M7 12h10M7 16h7"/>',
    "restore": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5"/>',
    "grid": '<path d="M3 3h18v18H3zM9 3v18M15 3v18M3 9h18M3 15h18"/>',
    "window-add": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M12 12v6M9 15h6"/>',
    "state-add": '<circle cx="9" cy="12" r="6"/><circle cx="9" cy="12" r="2"/><path d="M19 9v6M16 12h6"/>',
    "flag": '<path d="M5 21V4M5 4h12l-2 4 2 4H5"/>',
    "app-settings": '<path d="M6 3v18M12 3v18M18 3v18"/><circle cx="6" cy="8" r="2"/><circle cx="12" cy="15" r="2"/><circle cx="18" cy="10" r="2"/>',
    "debug": '<rect x="7" y="7" width="10" height="14" rx="5"/><path d="M12 11v10M7 13H3M21 13h-4M7 18l-3 2M17 18l3 2M7 9 4 6M17 9l3-3M9 7a3 3 0 0 1 6 0"/>',
    "continue": '<path d="M5 4v16M9 4l11 8-11 8z"/>',
    "step-over": '<path d="M4 14a8 8 0 0 1 15-4M19 4v6h-6"/><circle cx="12" cy="19" r="2"/>',
    "step-into": '<path d="M12 3v11M7 9l5 5 5-5"/><circle cx="12" cy="19" r="2"/>',
    "step-out": '<path d="M12 14V3M7 8l5-5 5 5"/><circle cx="12" cy="19" r="2"/>',
    "themes": '<path d="M12 3a9 9 0 1 0 0 18c1.5 0 2-1 2-2s-1-2 0-3h3a4 4 0 0 0 4-4c0-5-4-9-9-9z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="15" cy="7" r="1"/>',
    "about": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "tips": '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
    "keyboard": '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h1M10 10h1M14 10h1M18 10h1M7 14h10"/>',
    "diagnostics": '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 1-1 1.7M12 16.5v.5"/>',
}


def vector_icon(name):
    """Render the SVG at sharp sizes for common and HiDPI screens."""
    theme = getattr(QApplication.instance(), "makebench_theme", None)
    color = (
        theme.tokens["text"]
        if theme
        else QApplication.palette().color(QPalette.ColorRole.Text).name()
    )
    content = PATHS.get(name, PATHS["page"])
    data = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{content}</svg>'
    renderer = QSvgRenderer(QByteArray(data.encode("utf-8")))
    result = QIcon()
    for size in (16, 20, 24, 32, 48, 64):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        result.addPixmap(pixmap)
    return result
