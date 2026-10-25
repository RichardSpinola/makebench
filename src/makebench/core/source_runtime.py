"""Importação dos módulos congelados, usada exclusivamente no worker em execução."""

import importlib.abc
import importlib.util
import linecache
import sys
from pathlib import Path
from .source import validate_manifest


class SnapshotImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Fornece apenas makebench_user do snapshot, sem recorrer a arquivos mutáveis."""

    def __init__(self, modules, root):
        """Valida textos e monta nomes de arquivo para traceback e pontos de parada."""
        validate_manifest(list(modules))
        self.modules = dict(modules)
        self.root = Path(root)
        self.names = {}
        for path in modules:
            name = path[:-3].replace("/", ".")
            if name.endswith(".__init__"):
                name = name[: -len(".__init__")]
            self.names[name] = path
        self.filenames = {str(self.root / path): path for path in modules}

    def find_spec(self, fullname, path=None, target=None):
        """Impede que imports do pacote reservado escapem do snapshot iniciado."""
        if fullname != "makebench_user" and not fullname.startswith("makebench_user."):
            return None
        if fullname not in self.names:
            raise ModuleNotFoundError("Módulo não declarado no projeto: " + fullname, name=fullname)
        name = self.names[fullname]
        return importlib.util.spec_from_loader(
            fullname, self, is_package=name.endswith("/__init__.py")
        )

    def create_module(self, spec):
        """Usa o módulo padrão do Python, sem inicialização antecipada."""
        return None

    def exec_module(self, module):
        """Compila e executa o texto congelado somente durante import explícito."""
        name = self.names[module.__name__]
        filename = str(self.root / name)
        text = self.modules[name]
        module.__file__ = filename
        if name.endswith("/__init__.py"):
            module.__path__ = [str(Path(filename).parent)]
        linecache.cache[filename] = (len(text), None, text.splitlines(True), filename)
        exec(compile(text, filename, "exec"), module.__dict__)

    def install(self):
        """Registra o snapshot no worker recém-iniciado, antes da fonte de entrada."""
        sys.meta_path.insert(0, self)
