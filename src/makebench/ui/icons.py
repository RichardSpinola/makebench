# SPDX-License-Identifier: GPL-3.0-or-later
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
    "redo": '<path d="M20 10H10a6 6 0 0 0 0 12M20 10l-5-5M20 10l-5 5"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    "select": '<path d="m5 3 13 10-7 1-3 7z"/>',
    "window": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M6 6.5h1M10 6.5h1"/>',
    "container": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 10h18M10 10v11"/>',
    "button": '<rect x="3" y="6" width="18" height="12" rx="3"/><path d="M8 12h8"/>',
    "label": '<path d="M4 5h16M12 5v15M8 20h8"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="2"/><path d="m3 17 6-6 5 5 3-3 4 4"/>',
    "text_input": '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 12h5M15 9v6"/>',
    "checkbox": '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="m7 12 3 3 7-7"/>',
    "progress": '<rect x="2" y="8" width="20" height="8" rx="2"/><path d="M5 11v2M8 11v2M11 11v2"/>',
    "output": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m6 9 3 3-3 3M12 15h5"/>',
    "pages": '<path d="M3 7h18v14H3zM3 7V3h7v4M10 3h7v4"/>',
    "page": '<path d="M5 2h9l5 5v15H5zM14 2v6h5M8 12h8M8 16h8"/>',
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
