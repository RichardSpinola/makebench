# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only detection of optional libraries and tools."""

import importlib.util
import shutil
from makebench.i18n import tr

GTK_HELP = tr(
    "GTK4 is not available in this Python. Debian/Ubuntu: python3-gi, gir1.2-gtk-4.0 and, optionally, gir1.2-adw-1. Fedora: python3-gobject, gtk4 and, optionally, libadwaita. Install them with your distribution's package manager; Makebench does not install packages."
)


def gtk_support():
    """Detect introspection without initializing GTK, opening windows or starting processes."""
    result = {"pygobject": False, "gtk4": False, "adwaita": False, "reason": ""}
    try:
        import gi

        result["pygobject"] = True
        gi.require_version("Gtk", "4.0")
        result["gtk4"] = True
        try:
            gi.require_version("Adw", "1")
            result["adwaita"] = True
        except (ValueError, ImportError):
            pass
    except (ValueError, ImportError) as exc:
        result["reason"] = str(exc)
    return result


def build_tools():
    """Return tool paths without installing or running any of them."""
    return {
        name: shutil.which(name)
        for name in (
            "dpkg-deb",
            "appimagetool",
            "flatpak-builder",
            "appstreamcli",
            "flatpak-builder-lint",
            "rpmbuild",
            "pkexec",
        )
    }
