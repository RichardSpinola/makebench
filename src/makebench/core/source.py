"""Fontes Python inertes, módulos locais, conflitos e gravação atômica por arquivo."""

from __future__ import annotations
import json
import keyword
import os
from pathlib import Path, PurePosixPath
import tempfile
from .project import ProjectError

DEFAULT_SOURCE = '''"""Funções próprias do projeto. Abrir o Makebench não executa este arquivo.

Cada função recebe ctx (contexto do aplicativo) e valor (entrada do bloco).
Use F5 para testar estas funções no processo do aplicativo.
"""


def saudacao(ctx, valor):
    """Exemplo de função que pode ser chamada por um bloco."""
    return f"Olá, {valor or 'Linux'}!"
'''
ENTRY_FILE = "@actions"
MAX_FILES = 256
MAX_BYTES = 8 * 1024 * 1024


def validate_module_name(name):
    """Aceita somente módulos Python dentro do pacote reservado, sem travessia."""
    if not isinstance(name, str) or len(name) > 240 or "\\" in name:
        raise ProjectError("Caminho de módulo inválido.")
    path = PurePosixPath(name)
    if (
        len(path.parts) < 2
        or path.parts[0] != "makebench_user"
        or path.as_posix() != name
        or path.suffix != ".py"
    ):
        raise ProjectError("Módulos devem estar em makebench_user e terminar em .py.")
    if any(not p.isidentifier() or keyword.iskeyword(p) for p in (*path.parts[1:-1], path.stem)):
        raise ProjectError("Use nomes Python válidos para os módulos e pastas.")
    return name


def validate_manifest(names):
    """Valida lista limitada de arquivos declarados; não procura nem importa módulos."""
    if (
        not isinstance(names, list)
        or len(names) > MAX_FILES
        or len(set(n for n in names if isinstance(n, str))) != len(names)
    ):
        raise ProjectError("Lista de módulos inválida (máximo 256 arquivos, sem repetição).")
    for name in names:
        validate_module_name(name)
    if names and "makebench_user/__init__.py" not in names:
        raise ProjectError("O pacote precisa de makebench_user/__init__.py.")
    seen = set()
    for name in names:
        module = name[:-3].replace("/", ".")
        if module.endswith(".__init__"):
            module = module[:-9]
        if module in seen:
            raise ProjectError("Há um módulo e um pacote com o mesmo nome.")
        seen.add(module)
        for parent in PurePosixPath(name).parents:
            if str(parent) == ".":
                break
            if (parent / "__init__.py").as_posix() not in names:
                raise ProjectError("Falta o inicializador de pacote: " + str(parent))
    return names


def module_path(root, name):
    """Recusa links em qualquer segmento, inclusive dentro da raiz do projeto."""
    validate_module_name(name)
    path = Path(root)
    for part in PurePosixPath(name).parts:
        path = path / part
        if path.is_symlink():
            raise ProjectError("Módulos e suas pastas não podem ser links simbólicos.")
    return path


class SourceText(str):
    """Texto compatível com APIs antigas acompanhado de uma cópia dos módulos."""

    def __new__(cls, text, modules=None):
        """Congela os conteúdos auxiliares para construir/exportar sem ler widgets."""
        value = super().__new__(cls, text)
        value.modules = dict(modules or {})
        return value


def source_files(source):
    """Retorna os arquivos do snapshot, conservando a entrada dos projetos antigos."""
    return {ENTRY_FILE: str(source), **getattr(source, "modules", {})}


def source_signature(source):
    """Assinatura estável que também detecta alterações em módulos auxiliares."""
    return tuple(sorted(source_files(source).items()))


def source_path(project_path):
    """Deriva arquivo irmão: project.makebench.json → project.actions.py."""
    name = project_path.name
    stem = (
        name[: -len(".makebench.json")] if name.endswith(".makebench.json") else project_path.stem
    )
    return project_path.with_name(stem + ".actions.py")


def _read(path):
    """Lê somente arquivos regulares, recusando links e volumes excessivos."""
    if path.is_symlink():
        raise ProjectError("O arquivo Python não pode ser um link simbólico.")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ProjectError("Arquivo Python inválido ou maior que 8 MiB.")
    return path.read_bytes()


def _atomic_write(path, data):
    """Substitui um arquivo após flush/fsync; não confirma o documento completo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".actions-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


class SourceBuffer:
    """Texto de entrada e módulos com conflito externo e recuperação independentes."""

    def __init__(self, text=DEFAULT_SOURCE, saved_text=DEFAULT_SOURCE, path=None, original=None):
        """Preserva o construtor antigo; nenhum conteúdo é avaliado."""
        self._text = str(text)
        self.saved_text = saved_text
        self.path = path
        self.original = original
        self.modules = {}
        self._saved_names = ()
        self._deleted = {}

    @property
    def text(self):
        """Entrega snapshot textual compatível com a API de execução/exportação."""
        return SourceText(
            self._text, {name: str(buffer.text) for name, buffer in self.modules.items()}
        )

    @text.setter
    def text(self, value):
        """Substitui só a entrada; módulos não são apagados por edição do texto."""
        self._text = str(value)
        if isinstance(value, SourceText):
            self.modules = {
                name: SourceBuffer(text, text + "\0") for name, text in value.modules.items()
            }

    @property
    def dirty(self):
        """Inclui criação, exclusão, renomeação e edição dos módulos."""
        return (
            self._text != self.saved_text
            or tuple(sorted(self.modules)) != self._saved_names
            or any(b.dirty for b in self.modules.values())
        )

    @classmethod
    def load(cls, project_path):
        """Carrega somente os arquivos declarados no JSON, sempre como UTF-8."""
        if project_path is None:
            return cls()
        path = source_path(project_path)
        data = _read(path)
        try:
            text = data.decode("utf-8") if data is not None else DEFAULT_SOURCE
            buffer = cls(text, text, path, data)
            raw = (
                json.loads(Path(project_path).read_text(encoding="utf-8"))
                if Path(project_path).exists()
                else {}
            )
            names = validate_manifest(raw.get("python_files", []))
            total = len(data or b"")
            for name in names:
                target = module_path(path.parent, name)
                payload = _read(target)
                if payload is None:
                    raise ProjectError("Módulo ausente: " + name)
                total += len(payload)
                if total > MAX_BYTES:
                    raise ProjectError("As fontes excedem 8 MiB.")
                value = payload.decode("utf-8")
                buffer.modules[name] = cls(value, value, target, payload)
            buffer._saved_names = tuple(sorted(names))
            return buffer
        except UnicodeDecodeError as exc:
            raise ProjectError("Arquivos Python precisam estar em UTF-8.") from exc
        except (ValueError, TypeError) as exc:
            raise ProjectError("Manifesto de fontes inválido: " + str(exc)) from exc

    def add_module(self, name, text=""):
        """Cria pacote/pastas explicitamente sem sobrescrever módulos existentes."""
        validate_module_name(name)
        if name in self.modules:
            raise ProjectError("Já existe esse módulo.")
        names = [PurePosixPath(name)]
        for parent in PurePosixPath(name).parents:
            if str(parent) == ".":
                break
            init = (parent / "__init__.py").as_posix()
            if init not in self.modules and init != name:
                names.append(PurePosixPath(init))
        if len(self.modules) + len(names) > MAX_FILES:
            raise ProjectError("Máximo de 256 arquivos Python.")
        validate_manifest([*self.modules, *(path.as_posix() for path in names)])
        for path in reversed(names):
            key = path.as_posix()
            buffer = SourceBuffer(text if key == name else "", "\0")
            target = module_path(self.path.parent, key) if self.path else None
            if target in self._deleted:
                buffer.path = target
                buffer.original = self._deleted.pop(target)
            self.modules[key] = buffer

    def rename_module(self, old, new):
        """Renomeia arquivo sem reescrever imports nem descartar edições pendentes."""
        if old.endswith("/__init__.py"):
            raise ProjectError("O inicializador do pacote não pode ser renomeado.")
        validate_module_name(new)
        if new in self.modules:
            raise ProjectError("Já existe esse módulo.")
        buffer = self.modules[old]
        self.add_module(new, str(buffer.text))
        self.remove_module(old)

    def remove_module(self, name):
        """Retira do manifesto; só remove arquivo original após salvar todo o projeto."""
        if name.endswith("/__init__.py"):
            raise ProjectError("O inicializador do pacote não pode ser excluído.")
        buffer = self.modules.pop(name)
        if buffer.path:
            self._deleted[buffer.path] = buffer.original

    def write(self, project_path):
        """Verifica todos os conflitos antes de gravar; JSON confirma o salvamento."""
        entry = source_path(project_path)
        if not entry.parent.is_dir():
            raise OSError("A pasta de destino não existe.")
        targets = [(self, entry)] + [
            (buffer, module_path(entry.parent, name))
            for name, buffer in sorted(self.modules.items())
        ]
        total = 0
        for buffer, target in targets:
            current = _read(target)
            data = buffer._text.encode("utf-8")
            total += len(data)
            if target == buffer.path and current != buffer.original:
                raise ProjectError(
                    "O arquivo mudou fora do Makebench: "
                    + str(target)
                    + ". Salve em outra pasta ou reabra para revisar."
                )
            if target != buffer.path and current is not None and current != data:
                raise ProjectError("O destino já contém outro arquivo Python: " + str(target))
        for target, original in self._deleted.items():
            if target.is_relative_to(entry.parent) and _read(target) != original:
                raise ProjectError("O módulo excluído mudou fora do Makebench: " + str(target))
        if total > MAX_BYTES:
            raise ProjectError("As fontes excedem 8 MiB.")
        for buffer, target in targets:
            data = buffer._text.encode("utf-8")
            if _read(target) != data:
                _atomic_write(target, data)
            buffer.path, buffer.original = target, data

    def mark_saved(self):
        """Confirma depois do JSON; exclusões são condicionadas aos bytes originais."""
        for target, original in self._deleted.items():
            if self.path and target.is_relative_to(self.path.parent) and _read(target) == original:
                target.unlink(missing_ok=True)
        self._deleted.clear()
        self.saved_text = self._text
        self._saved_names = tuple(sorted(self.modules))
        for buffer in self.modules.values():
            buffer.mark_saved()
