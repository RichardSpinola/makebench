"""Imagens portáveis: importação explícita e recursos relativos ao projeto."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImageReader

from makebench.core.storage import StorageError


class AssetStore:
    """Mantém imagens em memória até salvar e resolve apenas caminhos locais.

    O cache persiste no Salvar como, permitindo desfazer a exclusão de uma imagem
    mesmo depois de trocar a pasta do documento. Nunca lê URLs ou caminhos externos
    indicados por um projeto; só a importação explícita aceita um arquivo externo.
    """

    def __init__(self, root: Path | None = None) -> None:
        """Associa o documento à pasta em que seus recursos são encontrados."""
        self.root = root.resolve() if root else None
        self._cache: dict[str, bytes] = {}

    @staticmethod
    def _inside(root: Path, source: str) -> Path:
        """Recusa caminhos absolutos, travessia e links que escapem do projeto."""
        parts = PurePosixPath(source)
        if parts.is_absolute() or ".." in parts.parts or "\\" in source or not parts.parts or parts.parts[0] != "assets":
            raise StorageError("O recurso precisa estar dentro da pasta assets do projeto.")
        path = (root / source).resolve()
        if not path.is_relative_to(root.resolve()):
            raise StorageError("O caminho da imagem aponta para fora do projeto.")
        return path

    def import_image(self, path: Path) -> str:
        """Valida PNG/JPEG/WebP/SVG e reserva uma cópia identificada pelo conteúdo."""
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise StorageError(f"Não foi possível ler a imagem: {exc}") from exc
        buffer = QBuffer()
        buffer.setData(QByteArray(data))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer)
        format_name = bytes(reader.format()).decode("ascii", errors="replace").lower()
        if format_name not in {"png", "jpeg", "jpg", "webp", "svg"} or reader.read().isNull():
            raise StorageError("Escolha uma imagem PNG, JPEG, WebP ou SVG válida.")
        extension = "jpg" if format_name == "jpeg" else format_name
        relative = f"assets/{hashlib.sha256(data).hexdigest()}.{extension}"
        self._cache[relative] = data
        return relative

    def read(self, source: str) -> bytes:
        """Lê uma imagem confinada ao projeto ou já importada nesta sessão."""
        if source in self._cache:
            return self._cache[source]
        if self.root is None:
            raise StorageError("Salve o projeto ou selecione a imagem novamente.")
        try:
            data = self._inside(self.root, source).read_bytes()
        except OSError as exc:
            raise StorageError(f"Imagem não encontrada: {source}") from exc
        self._cache[source] = data
        return data

    def write_referenced(self, root: Path, sources: set[str]) -> None:
        """Copia recursos antes do JSON, sem substituir arquivos de conteúdo diferente."""
        root = root.resolve()
        for source in sorted(sources):
            data = self.read(source)
            destination = self._inside(root, source)
            temporary = None
            try:
                if destination.exists():
                    if destination.read_bytes() != data:
                        raise StorageError(f"Já existe outra imagem em {source}; escolha outra pasta de destino.")
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Um link atômico não substitui um arquivo criado por outro processo.
                os.link(temporary, destination)
            except OSError as exc:
                raise StorageError(f"Não foi possível copiar a imagem {source}: {exc}") from exc
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
