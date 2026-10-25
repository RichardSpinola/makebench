"""Whole-document history, independent of the editor widgets."""

from __future__ import annotations

from copy import deepcopy
from makebench.core.project import Project

DEFAULT_LIMIT = 200


class History:
    """Keeps labeled snapshots for undo/redo and to detect saved changes.

    Each snapshot after the first carries the name of the change that produced
    it ("Move component"), so the interface can say what Undo will revert. Only
    the newest `limit` changes are kept; dropping old ones never affects whether
    the document counts as saved.
    """

    def __init__(self, project: Project, limit: int = DEFAULT_LIMIT) -> None:
        """Start a history whose current document is considered saved."""
        self._states = [project.to_dict()]
        self._labels = [""]
        self._index = 0
        self._saved = project.to_dict()
        self.limit = max(1, limit)

    @property
    def can_undo(self) -> bool:
        """There is a change before the current one."""
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        """There is an undone change that can be reapplied."""
        return self._index < len(self._states) - 1

    @property
    def undo_label(self) -> str:
        """Name of the change Undo would revert, or an empty string."""
        return self._labels[self._index] if self.can_undo else ""

    @property
    def redo_label(self) -> str:
        """Name of the change Redo would reapply, or an empty string."""
        return self._labels[self._index + 1] if self.can_redo else ""

    @property
    def dirty(self) -> bool:
        """Compare the current document with the last successful save."""
        return self._states[self._index] != self._saved

    def push(self, project: Project, label: str = "") -> bool:
        """Record real changes and drop the redo branch when editing.

        Returns False when the document did not change. The oldest snapshots are
        discarded once more than `limit` changes are stored.
        """
        state = project.to_dict()
        if state == self._states[self._index]:
            return False
        self._states = self._states[: self._index + 1]
        self._labels = self._labels[: self._index + 1]
        self._states.append(deepcopy(state))
        self._labels.append(label)
        self._index += 1
        overflow = len(self._states) - 1 - self.limit
        if overflow > 0:
            del self._states[:overflow]
            del self._labels[:overflow]
            self._labels[0] = ""
            self._index -= overflow
        return True

    def mark_saved(self) -> None:
        """Update the saved snapshot without clearing the change history."""
        self._saved = deepcopy(self._states[self._index])

    def undo(self) -> Project:
        """Return the previous document; keep the current one at the start."""
        if self.can_undo:
            self._index -= 1
        return Project.from_dict(self._states[self._index])

    def redo(self) -> Project:
        """Return the next document; keep the current one at the end."""
        if self.can_redo:
            self._index += 1
        return Project.from_dict(self._states[self._index])
