"""Histórico do documento completo, independente dos widgets do editor."""

from __future__ import annotations

from copy import deepcopy
from makebench.core.project import Project


class History:
    """Mantém retratos para desfazer/refazer e identificar alterações salvas."""

    def __init__(self, project: Project) -> None:
        """Inicia um histórico com o documento considerado salvo."""
        self._states = [project.to_dict()]
        self._index = 0
        self._saved = project.to_dict()

    @property
    def can_undo(self) -> bool:
        """Há uma alteração anterior à atual."""
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        """Há uma alteração desfeita que pode ser reaplicada."""
        return self._index < len(self._states) - 1

    @property
    def dirty(self) -> bool:
        """Compara o documento atual com o último salvamento bem-sucedido."""
        return self._states[self._index] != self._saved

    def push(self, project: Project) -> bool:
        """Registra mudanças reais e descarta o ramo de refazer ao editar."""
        state = project.to_dict()
        if state == self._states[self._index]:
            return False
        self._states = self._states[: self._index + 1]
        self._states.append(deepcopy(state))
        self._index += 1
        return True

    def mark_saved(self) -> None:
        """Atualiza o retrato salvo sem apagar o histórico de alterações."""
        self._saved = deepcopy(self._states[self._index])

    def undo(self) -> Project:
        """Retorna o documento anterior; mantém o atual se estiver no início."""
        if self.can_undo:
            self._index -= 1
        return Project.from_dict(self._states[self._index])

    def redo(self) -> Project:
        """Retorna o próximo documento; mantém o atual se estiver no fim."""
        if self.can_redo:
            self._index += 1
        return Project.from_dict(self._states[self._index])
