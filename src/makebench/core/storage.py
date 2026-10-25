"""Leitura validada e gravação atômica de documentos Makebench."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

from makebench.core.project import Project, ProjectError


class StorageError(ProjectError):
    """Falha de acesso ou formato que pode ser apresentada ao usuário."""


def load_project(path: str | Path) -> Project:
    """Carrega e valida um documento UTF-8 sem executar código do projeto."""
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise StorageError(f"Não foi possível abrir {source.name}: {exc}") from exc
    return Project.from_dict(data)


def save_project(project: Project, path: str | Path) -> Path | None:
    """Valida antes de escrever e substitui o arquivo somente após a gravação.

    Se a escrita ou a substituição falhar, o documento anterior permanece
    intacto. O arquivo temporário é criado no mesmo diretório do destino.
    Retorna a cópia `.bak-vN` criada nesta atualização de formato, ou None.
    """
    destination = Path(path)
    created: Path | None = None
    data = project.to_dict()
    Project.from_dict(data)
    try:
        text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise StorageError(f"O projeto contém dados que não podem ser salvos: {exc}") from exc
    if data['format_version']>=5 and destination.is_file():
        try:
            previous=json.loads(destination.read_text(encoding='utf-8'))
            backup=destination.with_name(destination.name+f".bak-v{previous.get('format_version',4)}")
            if isinstance(previous.get('format_version'),int) and previous['format_version'] < data['format_version'] and not backup.exists():
                with backup.open('xb') as handle:
                    handle.write(destination.read_bytes());handle.flush();os.fsync(handle.fileno())
                created=backup
        except (OSError,ValueError) as exc:raise StorageError(f'Não foi possível preservar a cópia anterior: {exc}') from exc
    if destination.is_file() and destination.read_text(encoding='utf-8')==text:return created
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists():
            temporary.chmod(destination.stat().st_mode & 0o777)
        os.replace(temporary, destination)
    except OSError as exc:
        raise StorageError(f"Não foi possível salvar {destination.name}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return created


def save_workspace(project: Project, source, assets, path: str | Path, saved: dict | None = None) -> tuple[dict, Path | None]:
    """Caminho único de salvamento do editor e de `Document`: recursos, fontes e JSON.

    Valida o documento antes de tocar no disco. Recursos e arquivos Python são
    gravados antes do JSON, que confirma o salvamento; só então módulos excluídos
    são removidos. `saved` é o dicionário do último salvamento no mesmo caminho:
    se for igual ao atual, o JSON não é regravado e formatos antigos mantêm seus
    bytes. Não é uma transação única: falha no JSON deixa as fontes já gravadas e
    o documento continua não salvo. Retorna o dicionário salvo e a cópia
    `.bak-vN` criada, ou None.
    """
    target = Path(path).resolve()
    project.python_files = sorted(source.modules)
    data = project.to_dict()
    Project.from_dict(data)
    assets.write_referenced(target.parent, project.asset_paths())
    source.write(target)
    backup = None
    if saved is None or data != saved or not target.is_file():
        backup = save_project(project, target)
    source.mark_saved()
    assets.root = target.parent
    return deepcopy(data), backup
