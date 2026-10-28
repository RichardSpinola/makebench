# SPDX-License-Identifier: MIT
"""The Qt widget that shows a Web view window's page."""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel

from makebench.core.web import materialize
from makebench.i18n import tr


def web_widget(html, read_asset, parent=None):
    """Show the page; links to websites open in the browser instead of inside the window."""
    try:
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        label = QLabel(tr("This window needs Qt WebEngine to show its page."), parent)
        label.setWordWrap(True)
        return label
    page_path = materialize(html, read_asset)
    folder = page_path.parent

    class Page(QWebEnginePage):
        def acceptNavigationRequest(self, url, navigation_type, main_frame):
            """Stay on the page's own files; websites belong to the browser."""
            if url.scheme() in {"http", "https", "mailto"}:
                if navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                    QDesktopServices.openUrl(url)
                return False
            if url.isLocalFile():
                return Path(url.toLocalFile()).resolve().is_relative_to(folder)
            return url.scheme() in {"data", "about"}

    view = QWebEngineView(parent)
    page = Page(view)
    view.setPage(page)
    view.setUrl(QUrl.fromLocalFile(str(page_path)))
    view.setAccessibleName(tr("Web page"))
    return view
