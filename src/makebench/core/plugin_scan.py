# SPDX-License-Identifier: MIT
"""Read a plugin's source without running it: what it can do, and a fingerprint of its files.

The scan is a help, not a guarantee: Python is dynamic, so a plugin can hide what it does.
It finds the plain cases and makes a plugin declare them in `plugin.json`, so the person
sees them before turning it on.
"""

import ast
import hashlib
from pathlib import Path

from makebench.i18n import tr

# Permission name -> imported modules that give it.
MODULE_PERMISSIONS = {
    "network": {
        "socket",
        "ssl",
        "http",
        "urllib",
        "ftplib",
        "smtplib",
        "xmlrpc",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
    },
    "programs": {"subprocess", "pty", "multiprocessing", "pexpect"},
    "native-code": {"ctypes", "cffi"},
}
# Permission name -> called names ("os.system", or a bare name).
CALL_PERMISSIONS = {
    "programs": {"os.system", "os.popen", "os.spawnl", "os.spawnv", "os.execv", "os.execl"},
    "dynamic-code": {"eval", "exec", "compile", "__import__", "importlib.import_module"},
    "files-outside": {"shutil.rmtree", "os.remove", "os.unlink", "os.rmdir"},
}
PERMISSION_TEXT = {
    "network": lambda: tr("Connects to the network"),
    "programs": lambda: tr("Runs other programs"),
    "native-code": lambda: tr("Loads native code"),
    "dynamic-code": lambda: tr("Builds and runs code at run time"),
    "files-outside": lambda: tr("Deletes files"),
}


def permissions_of(source: str) -> set[str]:
    """Permissions a Python source plainly uses; a syntax error counts as `dynamic-code`."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {"dynamic-code"}
    found = set()
    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]
        for module in modules:
            for permission, names in MODULE_PERMISSIONS.items():
                if module.split(".")[0] in names:
                    found.add(permission)
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            for permission, names in CALL_PERMISSIONS.items():
                if name in names:
                    found.add(permission)
    return found


def _dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def plugin_files(folder: Path) -> list[Path]:
    """Every regular file of a plugin, in a stable order."""
    return sorted(
        p for p in Path(folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts
    )


def scan_folder(folder: Path) -> set[str]:
    """Union of the permissions used by the plugin's Python files."""
    found = set()
    for path in plugin_files(folder):
        if path.suffix == ".py":
            found |= permissions_of(path.read_text(encoding="utf-8", errors="replace"))
    return found


def folder_hash(folder: Path) -> str:
    """SHA-256 over the relative names and contents of the plugin's files."""
    digest = hashlib.sha256()
    for path in plugin_files(folder):
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def undeclared(folder: Path, declared) -> list[str]:
    """Permissions the code uses that `plugin.json` did not declare."""
    declared = {str(item) for item in declared or ()}
    return sorted(scan_folder(folder) - declared)


def describe(permissions) -> list[str]:
    """Readable lines for a set of permissions."""
    return [PERMISSION_TEXT[p]() for p in sorted(permissions) if p in PERMISSION_TEXT]
