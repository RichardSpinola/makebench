# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless document (tools and tests), history and recovery, with no implicit execution."""

import base64
import json
import os
from pathlib import Path
from makebench.core.project import Project
from makebench.core.history import History
from makebench.core.source import SourceBuffer
from makebench.core.storage import load_project, save_workspace
from makebench.core.assets import AssetStore


class Document:
    """Single data authority; widgets never silently replace the model."""

    def __init__(self, project=None, path=None):
        """Read only JSON, images and Python text; never imports the user's file."""
        self.path = Path(path).resolve() if path else None
        self.project = project or (load_project(self.path) if self.path else Project.empty())
        self.source = SourceBuffer.load(self.path)
        self.assets = AssetStore(self.path.parent if self.path else None)
        self.history = History(self.project)
        self.saved = self.project.to_dict()

    @property
    def dirty(self):
        """Include Python source and structural changes in the same close warning."""
        return self.history.dirty or self.source.dirty

    def edit(self, change):
        """Validate a change atomically and keep IDs/unknown extensions."""
        before = self.project.to_dict()
        try:
            change(self.project)
            Project.from_dict(self.project.to_dict())
            self.history.push(self.project)
        except Exception:
            self.project = Project.from_dict(before)
            raise

    def save(self, path=None):
        """Use the editor's save path; keep JSON bytes/mtime when unedited."""
        target = Path(path or self.path).resolve()
        self.saved, backup = save_workspace(
            self.project,
            self.source,
            self.assets,
            target,
            self.saved if target == self.path else None,
        )
        self.path = target
        self.history.mark_saved()
        return backup

    def recovery(self, path):
        """Write an inert snapshot, including text with syntax errors and images."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "project": self.project.to_dict(),
            "source": self.source.text,
            "modules": getattr(self.source.text, "modules", {}),
            "path": str(self.path) if self.path else None,
            "assets": {
                name: base64.b64encode(self.assets.read(name)).decode()
                for name in self.project.asset_paths()
            },
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)

    @classmethod
    def recover(cls, path):
        """Open a snapshot without running code or replacing the source project."""
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        doc = cls(Project.from_dict(value["project"]))
        from .source import SourceText

        doc.source.text = SourceText(value["source"], value.get("modules", {}))
        doc.source.saved_text = value["source"] + "\0"
        for name, data in value.get("assets", {}).items():
            AssetStore.inside(Path("/tmp/makebench-recovery"), name)
            doc.assets._cache[name] = base64.b64decode(data, validate=True)
        return doc
