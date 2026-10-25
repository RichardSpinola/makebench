# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation transactions: one edit never shows empty intermediate panels."""

from contextlib import contextmanager


@contextmanager
def hold_updates(widget):
    """Group repaints and respect an external transaction already in progress."""
    enabled = widget.updatesEnabled()
    if enabled:
        widget.setUpdatesEnabled(False)
    try:
        yield
    finally:
        if enabled:
            widget.setUpdatesEnabled(True)
            widget.update()
