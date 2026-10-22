"""Símbolos vetoriais próprios, sem dependência de biblioteca de ícones externa."""
from PySide6.QtCore import QByteArray,Qt
from PySide6.QtGui import QIcon,QPainter,QPalette,QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

PATHS={
    'new':'<path d="M12 4v16M4 12h16"/>',
    'add':'<path d="M12 4v16M4 12h16"/>',
    'remove':'<path d="M4 12h16"/>',
    'run':'<path d="m7 4 13 8-13 8z"/>',
    'stop':'<rect x="5" y="5" width="14" height="14" rx="1"/>',
    'home':'<path d="m3 11 9-8 9 8M6 9v12h12V9M10 21v-7h4v7"/>',
    'open':'<path d="M3 8V5h7l3 3h8v12H3zM3 9h18"/>',
    'save':'<path d="M4 3h13l3 3v15H4zM8 3v6h8V3M8 21v-8h8v8"/>',
    'undo':'<path d="M4 10h10a6 6 0 0 1 0 12M4 10l5-5M4 10l5 5"/>',
    'redo':'<path d="M20 10H10a6 6 0 0 0 0 12M20 10l-5-5M20 10l-5 5"/>',
    'search':'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    'select':'<path d="m5 3 13 10-7 1-3 7z"/>',
    'window':'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M6 6.5h1M10 6.5h1"/>',
    'container':'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 10h18M10 10v11"/>',
    'button':'<rect x="3" y="6" width="18" height="12" rx="3"/><path d="M8 12h8"/>',
    'label':'<path d="M4 5h16M12 5v15M8 20h8"/>',
    'image':'<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="2"/><path d="m3 17 6-6 5 5 3-3 4 4"/>',
    'text_input':'<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 12h5M15 9v6"/>',
    'checkbox':'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="m7 12 3 3 7-7"/>',
    'progress':'<rect x="2" y="8" width="20" height="8" rx="2"/><path d="M5 11v2M8 11v2M11 11v2"/>',
    'output':'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m6 9 3 3-3 3M12 15h5"/>',
    'pages':'<path d="M3 7h18v14H3zM3 7V3h7v4M10 3h7v4"/>',
    'page':'<path d="M5 2h9l5 5v15H5zM14 2v6h5M8 12h8M8 16h8"/>',
}


def vector_icon(name):
    """Renderiza SVG em tamanhos nítidos para telas comuns e HiDPI."""
    color=QApplication.palette().color(QPalette.ColorRole.Text).name()
    content=PATHS.get(name,PATHS['page'])
    data=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{content}</svg>'
    renderer=QSvgRenderer(QByteArray(data.encode('utf-8')));result=QIcon()
    for size in (16,20,24,32,48,64):
        pixmap=QPixmap(size,size);pixmap.fill(Qt.GlobalColor.transparent)
        painter=QPainter(pixmap);painter.setRenderHint(QPainter.RenderHint.Antialiasing);renderer.render(painter);painter.end()
        result.addPixmap(pixmap)
    return result
