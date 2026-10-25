# SPDX-License-Identifier: MIT
"""Read-only environment report, with no subprocesses or installation."""

import importlib.metadata
import locale
import os
import platform
from .environment import gtk_support, build_tools
from makebench import __version__
from makebench.i18n import tr


def environment_report(desktop=None):
    """Build copyable text; graphical details can be appended by the GTK UI."""
    try:
        qt = importlib.metadata.version("PySide6")
    except importlib.metadata.PackageNotFoundError:
        qt = tr("Not installed (optional for Qt applications)")
    gtk = gtk_support()
    found, absent = tr("Detected"), tr("Missing")
    lines = [
        f"Makebench {__version__}",
        f"Python {platform.python_version()}",
        tr("System {system} {machine}").format(
            system=platform.system(), machine=platform.machine()
        ),
        "Editor: Qt Widgets",
        f"PySide6: {qt}",
        f"Locale: {locale.getlocale()}",
        "LANG: " + os.environ.get("LANG", tr("Not set")),
        "PyGObject: " + (found if gtk["pygobject"] else absent),
        "GTK4: " + (found if gtk["gtk4"] else absent),
        "libadwaita: " + (found if gtk["adwaita"] else absent),
    ]
    try:
        import gi

        gi.require_version("WebKit", "6.0")
        webkit = True
    except (ImportError, ValueError):
        webkit = False
    lines.append(
        "WebKitGTK 6 (Blockly): "
        + (found if webkit else tr("Missing — native action editing available"))
    )
    lines.extend(f"{key}: {value}" for key, value in (desktop or {}).items())
    lines.extend(f"{key}: {value or absent}" for key, value in build_tools().items())
    lines.append(tr("Detecting pkexec does not validate the Polkit agent or real authentication."))
    return "\n".join(lines)
