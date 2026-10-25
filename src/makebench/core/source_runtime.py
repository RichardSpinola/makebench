# SPDX-License-Identifier: GPL-3.0-or-later
"""Importing frozen modules, used only in the running worker."""

import importlib.abc
import importlib.util
import linecache
import sys
from pathlib import Path
from .source import validate_manifest
from makebench.i18n import tr


class SnapshotImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Provide only makebench_user from the snapshot, never from mutable files."""

    def __init__(self, modules, root):
        """Validate texts and build file names for tracebacks and breakpoints."""
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
        """Keep imports of the reserved package from escaping the started snapshot."""
        if fullname != "makebench_user" and not fullname.startswith("makebench_user."):
            return None
        if fullname not in self.names:
            raise ModuleNotFoundError(
                tr("Module not declared in the project: {name}").format(name=fullname),
                name=fullname,
            )
        name = self.names[fullname]
        return importlib.util.spec_from_loader(
            fullname, self, is_package=name.endswith("/__init__.py")
        )

    def create_module(self, spec):
        """Use Python's default module, with no early initialization."""
        return None

    def exec_module(self, module):
        """Compile and run the frozen text only during an explicit import."""
        name = self.names[module.__name__]
        filename = str(self.root / name)
        text = self.modules[name]
        module.__file__ = filename
        if name.endswith("/__init__.py"):
            module.__path__ = [str(Path(filename).parent)]
        linecache.cache[filename] = (len(text), None, text.splitlines(True), filename)
        exec(compile(text, filename, "exec"), module.__dict__)

    def install(self):
        """Register the snapshot in the freshly started worker, before the entry source."""
        sys.meta_path.insert(0, self)
