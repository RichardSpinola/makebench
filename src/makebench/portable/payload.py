# SPDX-License-Identifier: MIT
"""Helper run only in the isolated Ubuntu 24.04 SDK, never importing the project."""

from __future__ import annotations
import compileall
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

GLIBC = {
    "libc.so.6",
    "libm.so.6",
    "libpthread.so.0",
    "libdl.so.2",
    "librt.so.1",
    "libutil.so.1",
    "libresolv.so.2",
    "libanl.so.1",
    "libBrokenLocale.so.1",
    "libnss_dns.so.2",
    "libnss_files.so.2",
}


def copy_tree(source, destination):
    """Copy an SDK tree keeping relative links, skipping Python caches."""
    if Path(source).exists():
        shutil.copytree(
            source,
            destination,
            dirs_exist_ok=True,
            symlinks=True,
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", "test", "tests", "idlelib", "tkinter", "ensurepip"
            ),
        )


def elf(path):
    """Recognize executables/libraries by signature, without running them."""
    try:
        with path.open("rb") as stream:
            return stream.read(4) == b"\x7fELF"
    except OSError:
        return False


def collect_libraries(appdir):
    """Close the ELF dependencies of Python/Qt/GTK; glibc and drivers belong to the system."""
    library = appdir / "usr/lib"
    library.mkdir(parents=True, exist_ok=True)
    pending = [
        path
        for path in (appdir / "usr").rglob("*")
        if path.is_file() and not path.is_symlink() and elf(path)
    ]
    visited = set()
    missing = set()
    while pending:
        binary = pending.pop()
        if binary in visited:
            continue
        visited.add(binary)
        result = subprocess.run(["ldd", str(binary)], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if "=> not found" in line:
                missing.add(line.strip().split()[0])
                continue
            match = re.search(r"=>\s+(/\S+)", line)
            if not match:
                continue
            source = Path(match[1])
            name = line.split()[0]
            if name in GLIBC or name.startswith("ld-linux") or source.is_relative_to(appdir):
                continue
            target = library / name
            if not target.exists():
                shutil.copy2(source.resolve(), target)
                pending.append(target)
    return sorted(missing)


def build(root, backend, editor=False):
    """Include interpreter, stdlib, verified wheels and GTK; compile without importing sources."""
    root = Path(root)
    usr = root / "usr"
    site = usr / "lib/python3.12/site-packages"
    site.mkdir(parents=True, exist_ok=True)
    (usr / "bin").mkdir(parents=True, exist_ok=True)
    shutil.copy2("/usr/bin/python3.12", usr / "bin/python3.12")
    copy_tree("/usr/lib/python3.12", usr / "lib/python3.12")
    python_launcher = '#!/bin/sh\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)\nexport MAKEBENCH_ORIGINAL_PYTHONHOME="${PYTHONHOME-}"\nexport MAKEBENCH_ORIGINAL_PYTHONPATH="${PYTHONPATH-}"\nexport MAKEBENCH_ORIGINAL_LD_LIBRARY_PATH="${LD_LIBRARY_PATH-}"\nexport MAKEBENCH_ORIGINAL_PATH="$PATH"\nexport PYTHONHOME="$HERE/usr"\nexport PYTHONPATH="$HERE/usr/lib/python3.12/site-packages"\nexport LD_LIBRARY_PATH="$HERE/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\nexport GI_TYPELIB_PATH="$HERE/usr/lib/girepository-1.0"\nexport GIO_MODULE_DIR="$HERE/usr/lib/gio/modules"\nexport GSETTINGS_SCHEMA_DIR="$HERE/usr/share/glib-2.0/schemas"\nexport XDG_DATA_DIRS="$HERE/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"\nexport QT_PLUGIN_PATH="$HERE/usr/lib/python3.12/site-packages/PySide6/Qt/plugins"\nexec "$HERE/usr/bin/python3.12" "$@"\n'
    (usr / "bin/python3").write_text(python_launcher)
    (usr / "bin/python3").chmod(0o755)
    wheels = root.parent / "wheels"
    files = sorted(str(path) for path in wheels.glob("*.whl"))
    if files:
        subprocess.run(
            [
                "python3.12",
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-index",
                "--no-deps",
                "--no-compile",
                "--target",
                str(site),
                *files,
            ],
            check=True,
        )
    if backend == "gtk" or editor:
        for package in ("gi", "cairo"):
            copy_tree("/usr/lib/python3/dist-packages/" + package, site / package)
        copy_tree("/usr/lib/x86_64-linux-gnu/girepository-1.0", usr / "lib/girepository-1.0")
        copy_tree("/usr/lib/x86_64-linux-gnu/gio/modules", usr / "lib/gio/modules")
        copy_tree("/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0", usr / "lib/gdk-pixbuf-2.0")
        copy_tree("/usr/share/glib-2.0/schemas", usr / "share/glib-2.0/schemas")
        copy_tree("/usr/share/icons/Adwaita", usr / "share/icons/Adwaita")
        copy_tree("/usr/share/icons/hicolor", usr / "share/icons/hicolor")
        copy_tree("/usr/share/mime", usr / "share/mime")
        for pattern in (
            "/usr/bin/gtk4-broadwayd",
            "/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders",
        ):
            path = Path(pattern)
            if path.exists():
                shutil.copy2(path, usr / "bin" / path.name)
        # Typelibs open these libraries by name; they do not show up in _gi's ldd.
        for name in (
            "libgtk-4.so.1",
            "libadwaita-1.so.0",
            "libgirepository-1.0.so.1",
            "libgdk_pixbuf-2.0.so.0",
            "libcairo-gobject.so.2",
        ):
            source = Path("/usr/lib/x86_64-linux-gnu") / name
            if source.exists():
                shutil.copy2(source.resolve(), usr / "lib" / name)
    copy_tree("/usr/share/fonts/truetype/dejavu", usr / "share/fonts/truetype/dejavu")
    fonts = usr / "etc/fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    (fonts / "fonts.conf").write_text(
        '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>/usr/share/fonts</dir><dir>/usr/local/share/fonts</dir><dir prefix="relative">../../share/fonts</dir><cachedir prefix="xdg">fontconfig</cachedir></fontconfig>'
    )
    missing = collect_libraries(root)
    # Licenses and notices of the SDK packages ship with the redistributed libraries.
    copy_tree("/usr/share/doc", usr / "share/third-party-licenses")
    copy_tree("/usr/share/common-licenses", usr / "share/common-licenses")
    for link in list(root.rglob("*")):
        if not link.is_symlink():
            continue
        target = os.readlink(link)
        if target.startswith("/"):
            # Absolute links in SDK data cannot point outside the package.
            resolved = link.resolve()
            if resolved.is_file():
                link.unlink()
                shutil.copy2(resolved, link)
            elif resolved.is_dir():
                link.unlink()
                copy_tree(resolved, link)
            else:
                link.unlink()
    # compileall does not import modules or run project functions.
    if not compileall.compile_dir(root / "app", quiet=1, force=True):
        raise RuntimeError("Source incompatible with Python 3.12.")
    subprocess.run([str(usr / "bin/python3.12"), "--version"], check=True)
    distributions = {}
    for metadata in site.glob("*.dist-info/METADATA"):
        text = metadata.read_text()
        name = re.search(r"^Name: (.+)$", text, re.M)
        version = re.search(r"^Version: (.+)$", text, re.M)
        if name and version:
            distributions[name[1]] = version[1]
    manifest = {
        "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sdk_packages": Path("/opt/makebench-sdk-packages.txt").read_text(),
        "python": sys.version,
        "base": "Ubuntu 24.04",
        "architecture": "x86_64",
        "glibc_minimum": "2.39",
        "backend": backend,
        "editor": editor,
        "python_packages": distributions,
        "optional_elf_missing": missing,
        "remaining_system_requirements": [
            "Linux x86_64; glibc >=2.39",
            "X11 or Wayland server",
            "System graphics drivers",
            "/bin/sh and external programs used by the project",
            "FUSE to mount the AppImage, or --appimage-extract-and-run",
        ],
    }
    (root / "runtime-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], "--editor" in sys.argv[3:])
