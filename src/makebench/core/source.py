"""Arquivo Python próprio: leitura como texto, conflitos e escrita atômica."""

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile

from .project import ProjectError

DEFAULT_SOURCE = '''"""Funções próprias do projeto. Abrir o Makebench não executa este arquivo.

Cada função recebe ctx (contexto do aplicativo) e valor (entrada do bloco).
O runtime de execução será conectado na etapa M4.
"""


def saudacao(ctx, valor):
    """Exemplo de função que pode ser chamada por um bloco."""
    return f"Olá, {valor or 'Linux'}!"
'''


def source_path(project_path: Path) -> Path:
    """Deriva arquivo irmão: project.makebench.json → project.actions.py."""
    name = project_path.name
    stem = name[:-len(".makebench.json")] if name.endswith(".makebench.json") else project_path.stem
    return project_path.with_name(stem + ".actions.py")


def _read(path: Path) -> bytes | None:
    """Lê arquivo irmão, recusando links que poderiam escapar do projeto."""
    if path.is_symlink():
        raise ProjectError("O arquivo de funções não pode ser um link simbólico.")
    return path.read_bytes() if path.exists() else None


@dataclass
class SourceBuffer:
    """Mantém texto editável e conteúdo original para evitar sobrescrita externa."""
    text: str = DEFAULT_SOURCE
    saved_text: str = DEFAULT_SOURCE
    path: Path | None = None
    original: bytes | None = None

    @property
    def dirty(self) -> bool:
        """Detecta alterações independentes do histórico de blocos/interface."""
        return self.text != self.saved_text

    @classmethod
    def load(cls, project_path: Path | None) -> SourceBuffer:
        """Carrega somente texto UTF-8; conteúdo nunca é importado."""
        if project_path is None:
            return cls()
        path = source_path(project_path)
        data = _read(path)
        try:
            text = data.decode("utf-8") if data is not None else DEFAULT_SOURCE
        except UnicodeDecodeError as exc:
            raise ProjectError("O arquivo de funções precisa estar em UTF-8.") from exc
        return cls(text, text, path, data)

    def write(self, project_path: Path) -> None:
        """Grava fonte sem apagar edições externas nem conflitos no Salvar como.

        saved_text só é confirmado depois que o JSON também foi salvo. Se este
        falhar, o fingerprint já escrito permite nova tentativa sem conflito.
        """
        path = source_path(project_path)
        current = _read(path)
        data = self.text.encode("utf-8")
        if path == self.path:
            if current != self.original:
                raise ProjectError("O arquivo de funções mudou fora do Makebench. Salve como em outra pasta ou reabra o projeto para revisar as mudanças.")
        elif current is not None and current != data:
            raise ProjectError("O destino já contém outro arquivo de funções. Escolha outro nome ou outra pasta.")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".actions-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        self.path, self.original = path, data

    def mark_saved(self) -> None:
        """Confirma o texto após persistência completa do projeto."""
        self.saved_text = self.text
