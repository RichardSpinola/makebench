# SPDX-License-Identifier: MIT
"""Web view windows: a window whose whole content is one HTML page.

The page is kept in the window's `web_page` property, so saving, undo, history and export
need nothing new. Images come from the project's assets folder; before showing the page,
the runtime writes it with those images to a private folder and loads it from there.
"""

from __future__ import annotations

import atexit
import re
import shutil
import tempfile
from pathlib import Path

WEB_PAGE = "web_page"
MAX_PAGE = 2_000_000
ASSET_REFERENCE = re.compile(r"assets/[0-9a-f]{64}\.(?:png|jpg|webp|svg)")


def is_web(node) -> bool:
    """Whether a window shows a web page instead of components."""
    return isinstance(node.properties.get(WEB_PAGE), str)


def page_assets(html: str) -> set[str]:
    """Images of the project that the page uses."""
    return set(ASSET_REFERENCE.findall(html))


def materialize(html: str, read_asset) -> Path:
    """Write the page and its images to a private folder; return the page's path.

    A missing image is left out, so the page still opens and shows it as broken.
    """
    folder = Path(tempfile.mkdtemp(prefix="makebench-web-"))
    atexit.register(shutil.rmtree, folder, True)
    for name in page_assets(html):
        try:
            data = read_asset(name)
        except (OSError, ValueError):
            continue
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    page = folder / "index.html"
    page.write_text(html, encoding="utf-8")
    return page
