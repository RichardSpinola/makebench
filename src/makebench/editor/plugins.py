# SPDX-License-Identifier: GPL-3.0-or-later
"""Folder-based plugins (API v1). Every plugin is off until the person turns it on.

A plugin is a folder with `plugin.json` and `plugin.py`. Its `register(api)` function can add
menu commands, reusable pieces, code snippets and (API v2) project templates. Plugins run with
the user's permissions, so nothing is imported before the person enables it, and any failure
disables only that plugin. Official plugins ship inside Makebench and are off by default too.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import re
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from makebench.core import pieces as piece_library
from makebench.core import plugin_scan
from makebench.core.project import Project, ProjectError
from makebench.i18n import tr

API_VERSION = 2
SUPPORTED_APIS = {1, 2}
OFFICIAL_DIR = Path(__file__).resolve().parent.parent / "pluginpack"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def plugins_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "makebench" / "plugins"


@dataclass
class Plugin:
    id: str
    name: str
    version: str
    description: str
    author: str
    folder: Path
    enabled: bool = False
    error: str = ""
    incompatible: bool = False
    official: bool = False
    license: str = ""
    source: str = ""
    declared: list[str] = field(default_factory=list)
    detected: list[str] = field(default_factory=list)
    fingerprint: str = ""
    commands: list[tuple[str, Callable]] = field(default_factory=list)
    pieces: list[dict] = field(default_factory=list)
    snippets: dict[str, str] = field(default_factory=dict)
    templates: list[tuple[str, str, Callable]] = field(default_factory=list)

    def clear(self) -> None:
        """Forget everything `register` added."""
        self.commands, self.pieces, self.snippets, self.templates = [], [], {}, []


class Refusal(ProjectError):
    """Raised by a command that cannot run now; the message is shown and the plugin stays on."""


@dataclass
class CommandContext:
    """Where a command runs (API v2): the window being designed and the editor's helpers."""

    window: str
    parent: object = None
    read_asset: Callable[[str], bytes] | None = None
    import_image: Callable[[str], str] | None = None


def _takes_context(function: Callable) -> bool:
    """API v2 commands may take a second argument with the context."""
    try:
        inspect.signature(function).bind(None, None)
        return True
    except (TypeError, ValueError):
        return False


class Api:
    """What `register(api)` receives. Only these calls exist in API v1."""

    version = API_VERSION
    Refusal = Refusal

    def __init__(self, plugin: Plugin):
        self._plugin = plugin

    def add_command(self, name: str, function: Callable[..., None]) -> None:
        """Add a menu command; `function(project)` receives a copy it may change.

        With API v2, `function(project, context)` also receives a CommandContext.
        """
        if not callable(function) or not str(name).strip():
            raise ValueError("add_command needs a name and a function")
        self._plugin.commands.append((str(name).strip(), function))

    def add_piece(self, piece: dict) -> None:
        """Add a reusable piece (the dict format of a saved piece)."""
        if not isinstance(piece, dict) or piece.get("format") != piece_library.FORMAT:
            raise ValueError("add_piece needs a Makebench piece")
        self._plugin.pieces.append(piece)

    def add_snippet(self, name: str, code: str) -> None:
        """Add a code snippet offered in the Code area's suggestions."""
        if not str(name).isidentifier() or not isinstance(code, str):
            raise ValueError("add_snippet needs an identifier name and code text")
        self._plugin.snippets[str(name)] = code

    def add_template(self, name: str, description: str, build: Callable[[str], Project]) -> None:
        """Add a New project template (API v2); `build(name)` returns a new Project."""
        if not callable(build) or not str(name).strip():
            raise ValueError("add_template needs a name and a function")
        self._plugin.templates.append((str(name).strip(), str(description), build))


class PluginManager:
    def __init__(self, folder: Path | None = None, official: Path | None = OFFICIAL_DIR):
        self.folder = Path(folder) if folder else plugins_dir()
        self.official = Path(official) if official else None
        self.plugins: dict[str, Plugin] = {}
        self.scan()

    @property
    def _state_file(self) -> Path:
        return self.folder / "enabled.json"

    def _enabled_ids(self) -> set[str]:
        try:
            value = json.loads(self._state_file.read_text(encoding="utf-8"))
            return {item for item in value if isinstance(item, str)}
        except (OSError, ValueError, TypeError):
            return set()

    def _save_enabled(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        ids = sorted(plugin.id for plugin in self.plugins.values() if plugin.enabled)
        self._state_file.write_text(json.dumps(ids), encoding="utf-8")

    def scan(self) -> None:
        """Read the manifests only; no plugin code is imported."""
        previous = self.plugins
        self.plugins = {}
        folders = [(folder, True) for folder in self._folders(self.official)]
        folders += [(folder, False) for folder in self._folders(self.folder)]
        for folder, official in folders:
            manifest = folder / "plugin.json"
            if not manifest.is_file() or folder.name in self.plugins:
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if not ID_PATTERN.match(str(data.get("id", ""))) or data["id"] != folder.name:
                    raise ValueError(tr("The id must match the folder name."))
                plugin = Plugin(
                    id=data["id"],
                    name=str(data.get("name") or data["id"]),
                    version=str(data.get("version", "")),
                    description=str(data.get("description", "")),
                    author=str(data.get("author", "")),
                    folder=folder,
                    official=official,
                    license=str(data.get("license", "")),
                    source=str(data.get("source", "")),
                    declared=[str(item) for item in data.get("permissions", [])]
                    if isinstance(data.get("permissions", []), list)
                    else [],
                    detected=sorted(plugin_scan.scan_folder(folder)),
                    fingerprint=plugin_scan.folder_hash(folder),
                )
                if data.get("api") not in SUPPORTED_APIS:
                    plugin.incompatible = True
                    plugin.error = tr(
                        "Needs plugin API {api}; this editor offers API {have}."
                    ).format(api=data.get("api"), have=API_VERSION)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                plugin = Plugin(
                    folder.name, folder.name, "", "", "", folder, error=str(exc), incompatible=True
                )
            old = previous.get(plugin.id)
            if old is not None:
                plugin.enabled, plugin.commands = old.enabled, old.commands
                plugin.pieces, plugin.snippets = old.pieces, old.snippets
                plugin.templates = old.templates
            self.plugins[plugin.id] = plugin

    @staticmethod
    def _folders(root: Path | None) -> list[Path]:
        return sorted(root.iterdir()) if root and root.is_dir() else []

    def load_enabled(self) -> None:
        """At start: load the plugins the person turned on before."""
        for plugin_id in self._enabled_ids():
            if plugin_id in self.plugins:
                self.enable(plugin_id)

    def enable(self, plugin_id: str) -> bool:
        plugin = self.plugins.get(plugin_id)
        if plugin is None or plugin.incompatible:
            return False
        plugin.error = ""
        plugin.clear()
        try:
            name = f"makebench_plugin_{plugin.id.replace('-', '_')}"
            spec = importlib.util.spec_from_file_location(name, plugin.folder / "plugin.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            module.register(Api(plugin))
        except Exception:
            self._fail(plugin, traceback.format_exc(limit=3))
            return False
        plugin.enabled = True
        self._save_enabled()
        return True

    def disable(self, plugin_id: str) -> None:
        plugin = self.plugins.get(plugin_id)
        if plugin:
            plugin.enabled = False
            plugin.clear()
            sys.modules.pop(f"makebench_plugin_{plugin.id.replace('-', '_')}", None)
            self._save_enabled()

    def _fail(self, plugin: Plugin, message: str) -> None:
        plugin.enabled = False
        plugin.error = message.strip()
        plugin.clear()
        if plugin.folder.exists():
            self._save_enabled()

    def run_command(
        self,
        plugin_id: str,
        index: int,
        project: Project,
        context: CommandContext | None = None,
    ) -> Project:
        """Run a command on a copy of the project; return the changed copy.

        A Refusal is passed on as it is. Any other failure turns the plugin off and is
        raised as ProjectError.
        """
        plugin = self.plugins[plugin_id]
        work = Project.from_dict(project.to_dict())
        function = plugin.commands[index][1]
        try:
            if _takes_context(function):
                function(work, context or CommandContext(project.root.id))
            else:
                function(work)
            return Project.from_dict(work.to_dict())
        except Refusal:
            raise
        except Exception as exc:
            self._fail(plugin, traceback.format_exc(limit=3))
            raise ProjectError(
                tr("The plugin {name} failed and was turned off: {error}").format(
                    name=plugin.name, error=exc
                )
            ) from exc

    def templates(self) -> list[tuple[str, str, str]]:
        """(key, name, description) of every template offered by an enabled plugin."""
        return [
            (f"plugin:{plugin.id}:{index}", name, description)
            for plugin in self.plugins.values()
            for index, (name, description, _) in enumerate(plugin.templates)
        ]

    def make_template(self, key: str, name: str) -> Project:
        """Build a plugin template; a failing plugin is turned off."""
        _, plugin_id, index = key.split(":")
        plugin = self.plugins[plugin_id]
        try:
            project = plugin.templates[int(index)][2](name)
            return Project.from_dict(project.to_dict())
        except Exception as exc:
            self._fail(plugin, traceback.format_exc(limit=3))
            raise ProjectError(
                tr("The plugin {name} failed and was turned off: {error}").format(
                    name=plugin.name, error=exc
                )
            ) from exc

    def snippets(self) -> dict[str, str]:
        found = {}
        for plugin in self.plugins.values():
            found.update(plugin.snippets)
        return found

    def pieces(self) -> list[dict]:
        return [piece for plugin in self.plugins.values() for piece in plugin.pieces]

    def install_from(self, source: Path) -> str:
        """Copy a plugin folder into the plugins folder (it stays off)."""
        source = Path(source)
        try:
            data = json.loads((source / "plugin.json").read_text(encoding="utf-8"))
            plugin_id = data["id"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ProjectError(tr("That folder has no valid plugin.json.")) from exc
        if not ID_PATTERN.match(str(plugin_id)) or not (source / "plugin.py").is_file():
            raise ProjectError(tr("That folder is not a valid plugin."))
        target = self.folder / plugin_id
        if target.exists() or plugin_id in self.plugins:
            raise ProjectError(tr("A plugin with this id is already installed."))
        self.folder.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        self.scan()
        return plugin_id
