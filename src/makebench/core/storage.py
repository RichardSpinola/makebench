"""Validated reading and atomic writing of Makebench documents."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

from makebench.core.project import Project, ProjectError
from makebench.i18n import tr


class StorageError(ProjectError):
    """Access or format failure that can be shown to the user."""


def load_project(path: str | Path) -> Project:
    """Load and validate a UTF-8 document without running project code."""
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise StorageError(
            tr("Could not open {name}: {error}").format(name=source.name, error=exc)
        ) from exc
    return Project.from_dict(data)


def save_project(project: Project, path: str | Path) -> Path | None:
    """Validate before writing and replace the file only after the write succeeds.

    If writing or replacing fails, the previous document stays intact. The
    temporary file is created in the destination folder. Returns the `.bak-vN`
    copy created by this format upgrade, or None.
    """
    destination = Path(path)
    created: Path | None = None
    data = project.to_dict()
    Project.from_dict(data)
    try:
        text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise StorageError(
            tr("The project contains data that cannot be saved: {error}").format(error=exc)
        ) from exc
    if data["format_version"] >= 5 and destination.is_file():
        try:
            previous = json.loads(destination.read_text(encoding="utf-8"))
            backup = destination.with_name(
                destination.name + f".bak-v{previous.get('format_version', 4)}"
            )
            if (
                isinstance(previous.get("format_version"), int)
                and previous["format_version"] < data["format_version"]
                and not backup.exists()
            ):
                with backup.open("xb") as handle:
                    handle.write(destination.read_bytes())
                    handle.flush()
                    os.fsync(handle.fileno())
                created = backup
        except (OSError, ValueError) as exc:
            raise StorageError(
                tr("Could not keep the previous copy: {error}").format(error=exc)
            ) from exc
    if destination.is_file() and destination.read_text(encoding="utf-8") == text:
        return created
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists():
            temporary.chmod(destination.stat().st_mode & 0o777)
        os.replace(temporary, destination)
    except OSError as exc:
        raise StorageError(
            tr("Could not save {name}: {error}").format(name=destination.name, error=exc)
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return created


def save_workspace(
    project: Project, source, assets, path: str | Path, saved: dict | None = None
) -> tuple[dict, Path | None]:
    """Single save path for the editor and `Document`: assets, sources and JSON.

    Validate the document before touching the disk. Assets and Python files are
    written before the JSON, which confirms the save; only then are deleted
    modules removed. `saved` is the dict of the last save to the same path: when
    it equals the current one, the JSON is not rewritten and older formats keep
    their bytes. This is not a single transaction: a JSON failure leaves the
    sources already written and the document still unsaved, with a StorageError
    explaining that state. Returns the saved dict and the `.bak-vN` copy created,
    or None.
    """
    target = Path(path).resolve()
    project.python_files = sorted(source.modules)
    data = project.to_dict()
    Project.from_dict(data)
    assets.write_referenced(target.parent, project.asset_paths())
    source.write(target)
    backup = None
    if saved is None or data != saved or not target.is_file():
        try:
            backup = save_project(project, target)
        except (OSError, ProjectError) as exc:
            raise StorageError(
                tr(
                    "{error} Python files and assets were already written, but the project file ({name}) was not. The project still has unsaved changes: free up space or check permissions and save again."
                ).format(error=exc, name=target.name)
            ) from exc
    source.mark_saved()
    assets.root = target.parent
    return deepcopy(data), backup
