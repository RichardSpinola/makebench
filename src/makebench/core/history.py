"""Whole-document history, independent of the editor widgets."""

from __future__ import annotations

from copy import deepcopy
from makebench.core.project import Project


class History:
    """Keeps snapshots for undo/redo and to detect saved changes."""

    def __init__(self, project: Project) -> None:
        """Start a history whose current document is considered saved."""
        self._states = [project.to_dict()]
        self._index = 0
        self._saved = project.to_dict()

    @property
    def can_undo(self) -> bool:
        """There is a change before the current one."""
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        """There is an undone change that can be reapplied."""
        return self._index < len(self._states) - 1

    @property
    def dirty(self) -> bool:
        """Compare the current document with the last successful save."""
        return self._states[self._index] != self._saved

    def push(self, project: Project) -> bool:
        """Record real changes and drop the redo branch when editing."""
        state = project.to_dict()
        if state == self._states[self._index]:
            return False
        self._states = self._states[: self._index + 1]
        self._states.append(deepcopy(state))
        self._index += 1
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
