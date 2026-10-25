"""Inert native thumbnails, with a bounded cache and serialized GTK rendering."""

from collections import OrderedDict
import base64
import hashlib
import json
from PySide6.QtCore import QObject, QTimer, Signal, Qt, QSize
from PySide6.QtGui import QPixmap, QImage
from makebench.core.project import Project
from .native_preview import GtkPreviewJob
from .theme import manager
from makebench.i18n import tr


class ThumbnailCache(QObject):
    """Receive only composition and images: never the user's source or runnable events."""

    ready = Signal(str, QPixmap, str)

    def __init__(self, parent):
        """The LRU cache keeps at most 96 small images; only one GTK helper is active."""
        super().__init__(parent)
        self.cache = OrderedDict()
        self.pending = OrderedDict()
        self.wanted = {}
        self.delivered = {}
        self.failures = {}
        self.asset_versions = {}
        self.resources = {}
        self.job = None
        self.closed = False
        self.active = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self.next)

    def request(self, key, root, backend, read_asset):
        """Invalidate by effective composition, images and theme, without rebuilding the map."""
        assets = {}
        for node in root.walk():
            for name in (node.properties.get("source"), node.properties.get("icon")):
                if name and name not in assets:
                    try:
                        assets[name] = read_asset(name)
                    except (OSError, ValueError):
                        assets[name] = b""
        self.resources[key] = set(assets)
        fingerprints = {}
        for name, raw in assets.items():
            previous = self.asset_versions.get(name)
            if previous is None or previous[0] is not raw:
                self.asset_versions[name] = (raw, hashlib.sha256(raw).hexdigest())
            fingerprints[name] = self.asset_versions[name][1]
        data = {"root": root.to_dict(), "assets": fingerprints, "visible_pages": {}}
        signature = hashlib.sha256(
            (
                json.dumps(data, sort_keys=True)
                + backend
                + str(manager().tokens)
                + str(manager().scale)
            ).encode()
        ).hexdigest()
        self.wanted[key] = signature
        if self.delivered.get(key) == signature or self.failures.get(key) == signature:
            return
        if signature in self.cache:
            self.cache.move_to_end(signature)
            self.delivered[key] = signature
            self.ready.emit(key, self.cache[signature], "")
            return
        if self.active == (key, signature):
            return
        previous = self.pending.get(key)
        if previous and previous[0] == signature:
            return
        data["assets"] = {name: base64.b64encode(raw).decode() for name, raw in assets.items()}
        self.pending[key] = (signature, backend, data)
        if self.job is None:
            self.timer.start()

    def next(self):
        """Qt renders one card per event; GTK draws outside the interface thread."""
        if self.closed or self.job or not self.pending:
            return
        key, (signature, backend, data) = self.pending.popitem(last=False)
        if self.wanted.get(key) != signature:
            self.timer.start()
            return
        if backend == "gtk":
            job = GtkPreviewJob(data, self)
            self.job = job
            self.active = (key, signature)
            job.ready.connect(
                lambda image, _info: self.complete(
                    key, signature, QPixmap.fromImage(QImage.fromData(image))
                )
            )
            job.failed.connect(lambda error: self.fail(key, signature, error))

            def finished():
                """The next card starts only after the private display is cleaned up."""
                self.job = None
                self.active = None
                job.deleteLater()
                if self.pending:
                    self.timer.start()

            job.finished.connect(finished)
            job.start()
        else:
            try:
                self.complete(key, signature, self.qt_image(data))
            except Exception as exc:
                self.fail(key, signature, str(exc))
            if self.pending:
                self.timer.start()

    def qt_image(self, data):
        """Use the same renderer and decoration as the Designer, with no RuntimeSession."""
        from .canvas import PreviewCanvas

        document = Project.empty().to_dict()
        document["ui"] = data["root"]
        document["ui"]["properties"].pop("initial_state", None)
        project = Project.from_dict(document)
        canvas = PreviewCanvas()
        canvas.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        canvas.read_asset = lambda key: base64.b64decode(data["assets"][key])
        canvas.set_project(project)
        width = min(1600, max(400, project.root.properties.get("width", 640) + 40))
        height = min(1200, max(360, project.root.properties.get("height", 480) + 78))
        try:
            canvas.resize(width, height)
            canvas.ensurePolished()
            canvas.show()
            canvas.layout().activate()
            return canvas.grab()
        finally:
            canvas.hide()
            canvas.deleteLater()

    def complete(self, key, signature, pixmap):
        """Old results never replace a composition edited while rendering."""
        if self.closed or self.wanted.get(key) != signature:
            return
        image = pixmap.scaled(
            QSize(276, 174),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if image.isNull():
            self.fail(key, signature, tr("The renderer did not produce a valid image."))
            return
        self.delivered[key] = signature
        self.failures.pop(key, None)
        self.cache[signature] = image
        self.cache.move_to_end(signature)
        while len(self.cache) > 96:
            self.cache.popitem(last=False)
        self.ready.emit(key, image, "")

    def retain(self, keys):
        """Drop requests for removed, collapsed or other-project cards."""
        self.resources = {key: value for key, value in self.resources.items() if key in keys}
        used = set().union(*self.resources.values()) if self.resources else set()
        self.asset_versions = {
            name: value for name, value in self.asset_versions.items() if name in used
        }
        self.delivered = {key: value for key, value in self.delivered.items() if key in keys}
        self.failures = {key: value for key, value in self.failures.items() if key in keys}
        self.wanted = {key: value for key, value in self.wanted.items() if key in keys}
        self.pending = OrderedDict(
            (key, value) for key, value in self.pending.items() if key in keys
        )

    def fail(self, key, signature, error):
        """A failure is stable until the composition changes or a refresh is requested."""
        if self.closed or self.wanted.get(key) != signature:
            return
        self.failures[key] = signature
        self.ready.emit(key, QPixmap(), error)

    def invalidate(self, key):
        """Allow retrying after fixing assets or installing GTK support."""
        self.delivered.pop(key, None)
        self.failures.pop(key, None)
        signature = self.wanted.get(key)
        if signature:
            self.cache.pop(signature, None)

    def shutdown(self):
        """Close only the thumbnail helper created by the editor."""
        self.closed = True
        self.timer.stop()
        self.pending.clear()
        if self.job and self.job.isRunning():
            self.job.cancel.set()
            self.job.wait(100)
        return not (self.job and self.job.isRunning())
