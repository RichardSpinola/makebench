# SPDX-License-Identifier: MIT
"""Sharing documents and assets, always as inert data."""

import json
from pathlib import Path, PurePosixPath
import stat
import zipfile
from .project import ProjectError
from .storage import load_project, save_project
from .source import source_path
from makebench.i18n import tr

MAX_BUNDLE_SIZE = 100 * 1024 * 1024


def write_bundle(project, source, read_asset, destination):
    """Create a portable ZIP; never includes arbitrary files from the user's folder."""
    destination = Path(destination)
    temporary = destination.with_name("." + destination.name + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "project.makebench.json",
                json.dumps(project.to_dict(), ensure_ascii=False, indent=2),
            )
            archive.writestr("project.actions.py", source)
            from .source import source_files, ENTRY_FILE, validate_manifest

            files = source_files(source)
            validate_manifest(list(project.python_files))
            if set(files) - {ENTRY_FILE} != set(project.python_files):
                raise ProjectError(tr("The manifest and the modules do not match."))
            for name, text in files.items():
                if name != ENTRY_FILE:
                    archive.writestr(name, text)
            for name in sorted(project.asset_paths()):
                archive.writestr(name, read_asset(name))
            archive.writestr(
                "README.txt",
                tr(
                    "Makebench project. Open project.makebench.json.\nOpening never runs code. Testing runs Python and scripts with your permissions.\n"
                ),
            )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def read_bundle(source, destination):
    """Extract a project into a new folder; reject escapes, links and excessive size."""
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ProjectError(tr("Choose an empty folder to extract the project."))
    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            if len(members) > 2000 or sum(item.file_size for item in members) > MAX_BUNDLE_SIZE:
                raise ProjectError(tr("The project exceeds the limit of 100 MiB or 2000 files."))
            if "project.makebench.json" not in archive.namelist():
                raise ProjectError(tr("The package does not contain project.makebench.json."))
            from .project import Project

            project = Project.from_dict(json.loads(archive.read("project.makebench.json")))
            allowed_modules = set(project.python_files)
            names = set()
            for item in members:
                path = PurePosixPath(item.filename)
                if (
                    not path.parts
                    or path.is_absolute()
                    or ".." in path.parts
                    or "\\" in item.filename
                    or stat.S_ISLNK(item.external_attr >> 16)
                    or item.filename in names
                ):
                    raise ProjectError(tr("The file contains a path or link that is not allowed."))
                names.add(item.filename)
                if not (
                    item.is_dir()
                    and path.parts[0] == "assets"
                    or item.filename
                    in {"project.makebench.json", "project.actions.py", "README.txt", "LEIA-ME.txt"}
                    or len(path.parts) > 1
                    and path.parts[0] == "assets"
                    or item.filename in allowed_modules
                    or item.is_dir()
                    and any(name.startswith(item.filename) for name in allowed_modules)
                ):
                    raise ProjectError(
                        tr("The package contains files outside the project and assets.")
                    )
            if "project.makebench.json" not in names:
                raise ProjectError(tr("The package does not contain project.makebench.json."))
            from .project import Project

            Project.from_dict(json.loads(archive.read("project.makebench.json")))
            if not allowed_modules <= names:
                raise ProjectError(tr("The package does not contain all declared modules."))
            destination.mkdir(parents=True, exist_ok=True)
            for item in members:
                path = destination / item.filename
                if item.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as stream, path.open("xb") as output:
                        import shutil

                        shutil.copyfileobj(stream, output)
    except (zipfile.BadZipFile, UnicodeError, ValueError) as exc:
        raise ProjectError(tr("Invalid project package: {error}").format(error=exc)) from exc
    return destination / "project.makebench.json"
