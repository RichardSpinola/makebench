"""Readable error dialogs: what failed, why in plain words, and technical details on demand."""

from __future__ import annotations

import errno
import traceback

from PySide6.QtWidgets import QMessageBox

from makebench.core.project import ProjectError
from makebench.i18n import tr


def describe(error: BaseException | str) -> tuple[str, str]:
    """Return (summary, details) for an error, translating common system failures.

    Project errors already carry user-facing text. Operating-system errors become a
    short explanation naming the file, with the raw message kept as details.
    Anything else is unexpected: the summary stays short and the traceback goes to
    the details so it can be reported.
    """
    if isinstance(error, str):
        return error, ""
    if isinstance(error, ProjectError):
        return str(error), ""
    if isinstance(error, OSError):
        path = error.filename or tr("the file")
        messages = {
            errno.EACCES: tr("You do not have permission to use {path}."),
            errno.EPERM: tr("You do not have permission to use {path}."),
            errno.ENOSPC: tr("There is no free space left on the disk."),
            errno.EDQUOT: tr("Your disk quota is full."),
            errno.ENOENT: tr("{path} does not exist or was moved."),
            errno.EROFS: tr("{path} is on a read-only disk."),
            errno.EEXIST: tr("{path} already exists."),
            errno.EISDIR: tr("{path} is a folder, not a file."),
            errno.ENOTDIR: tr("Part of the path {path} is not a folder."),
        }
        summary = messages.get(error.errno)
        if summary:
            return summary.format(path=path), f"{type(error).__name__}: {error}"
        return tr("The system reported an error: {error}").format(
            error=error.strerror or error
        ), f"{type(error).__name__}: {error}"
    details = "".join(traceback.format_exception(error))
    return tr("Unexpected error: {error}").format(error=error), details


def show_error(parent, error: BaseException | str, action: str | None = None) -> QMessageBox:
    """Show a critical dialog titled by the failed action, with details collapsed.

    Returns the dialog (already finished) so tests can inspect it.
    """
    summary, details = describe(error)
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Icon.Critical)
    dialog.setWindowTitle(action or tr("Could not complete the action"))
    dialog.setText(action or tr("Could not complete the action"))
    dialog.setInformativeText(summary)
    if details:
        dialog.setDetailedText(details)
    dialog.setStandardButtons(QMessageBox.StandardButton.Close)
    from makebench.ui.dialogs import translate_buttons

    translate_buttons(dialog)
    dialog.exec()
    return dialog
