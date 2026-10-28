# SPDX-License-Identifier: MIT
"""Coordination of real windows and states over a single run session."""

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QMainWindow, QScrollArea
from makebench.core.project import ComponentKind, ProjectError
from .view import RuntimeView
from makebench.i18n import tr


class AppWindow(QMainWindow):
    """Additional application window; supervision stays in the controller."""

    def __init__(self, owner, root, view):
        """Keep a reference to the controller until the last window closes."""
        super().__init__()
        self.owner = owner
        self.identifier = root.id
        self.setWindowIcon(owner.windowIcon())
        if root.properties.get("icon"):
            from PySide6.QtGui import QIcon, QPixmap

            pixmap = QPixmap()
            pixmap.loadFromData(owner.read_asset(root.properties["icon"]))
            self.setWindowIcon(QIcon(pixmap))
        self.setWindowTitle(root.properties.get("title", owner.project.name))
        self.resize(root.properties.get("width", 640), root.properties.get("height", 480))
        if not root.properties.get("resizable", True):
            self.setFixedSize(self.size())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(view)
        self.setCentralWidget(scroll)

    def closeEvent(self, event):
        """Remove the window without abandoning administrative tasks or ordinary processes."""
        if self.owner.session.closed:
            event.accept()
            return
        if self.owner.session.admin_active:
            self.owner.state.setText(tr("Wait for the administrative task to finish."))
            event.ignore()
            return
        from makebench.terminal.components import stop_components

        def finish():
            stop_components(self.owner.views[self.identifier].widgets)
            self.owner.stop_timer(self.identifier)
            self.owner.open_windows.discard(self.identifier)
            self.hide()
            self.owner.stop_if_last()

        event.ignore()
        self.owner.close_with_event(self.identifier, finish)


class RuntimeNavigation:
    """Apply declared navigation; every operation receives already-validated IDs."""

    def install_navigation(self, read_asset):
        """Register the start window and prepare scopes without starting the worker."""
        self.read_asset = read_asset
        self.views = {self.root_window_id: self.view}
        self.app_windows = {self.root_window_id: self}
        self.open_windows = {self.root_window_id}
        self.active_states = {}
        self.current_window = self.root_window_id
        self._queued_flows = []
        self._timers = {}
        self._closing = {}
        self.view.window_id = self.root_window_id
        for root in self.project.roots:
            self.active_states[root.id] = root.properties.get("initial_state", "@default")
        self.apply_state(self.root_window_id, self.active_states[self.root_window_id])

    def apply_state(self, window_id, state):
        """Restore default properties and apply differences without duplicating components."""
        effective = self.project.effective_root(window_id, state)
        self.active_states[window_id] = state
        view = self.views.get(window_id)
        if view:
            for node in effective.walk():
                widget = view.widgets[node.id]
                p = node.properties
                if node.kind in {
                    ComponentKind.LABEL,
                    ComponentKind.BUTTON,
                    ComponentKind.TEXT_INPUT,
                    ComponentKind.CHECKBOX,
                    ComponentKind.OUTPUT,
                }:
                    if node.kind == ComponentKind.OUTPUT:
                        widget.clear()
                        widget.setPlaceholderText(p.get("text", ""))
                    elif hasattr(widget, "setPlainText"):
                        widget.setPlainText(p.get("text", ""))
                    else:
                        widget.setText(p.get("text", ""))
                if node.kind == ComponentKind.CHECKBOX:
                    widget.setChecked(p.get("checked", False))
                if node.kind == ComponentKind.PROGRESS:
                    widget.setValue(p.get("value", 0))
                if node.kind == ComponentKind.IMAGE:
                    from PySide6.QtGui import QPixmap

                    pixmap = QPixmap()
                    if p.get("source"):
                        pixmap.loadFromData(self.read_asset(p["source"]))
                    widget.image = pixmap
                    widget.setAccessibleName(p.get("alt_text", tr("Image")))
                    widget.update()
                view.set_enabled(node.id, p.get("enabled", True))
                view.set_visible(node.id, p.get("visible", True))
                if node.kind == ComponentKind.PAGES:
                    view.show_page(p["initial_page"])
            window = self.app_windows.get(window_id)
            if window:
                window.setWindowTitle(
                    (tr("[Test]") + " " if self.supervision else "")
                    + effective.properties.get("title", self.project.name)
                )

    def open_app_window(self, identifier, close_current=False):
        """Create or re-show a real window; never duplicates an open instance."""
        root = next((r for r in self.project.roots if r.id == identifier), None)
        if root is None:
            raise ValueError(tr("The window does not exist."))
        was_open = identifier in self.open_windows
        if identifier not in self.views:
            view = RuntimeView(self.project, self.read_asset, window_root=root)
            view.window_id = identifier
            view.clicked.connect(self._clicked)
            view.changed.connect(self._changed)
            window = AppWindow(self, root, view)
            self.views[identifier] = view
            self.app_windows[identifier] = window
        elif not was_open:
            self.views[identifier].reset()
        if not was_open:
            self.active_states[identifier] = root.properties.get("initial_state", "@default")
            self.apply_state(identifier, self.active_states[identifier])
        self.views[identifier].set_busy(self.session.busy)
        self.open_windows.add(identifier)
        window = self.app_windows[identifier]
        window.show()
        window.raise_()
        if close_current and self.current_window != identifier:
            self.close_app_window(self.current_window, check_last=False)
        if not was_open:
            from makebench.terminal.components import start_components

            start_components(root, self.views[identifier].widgets, self.session.root)
            self.queue_event(identifier, "start")
            self.start_timer(identifier)
        return not was_open

    def close_app_window(self, identifier, check_last=True):
        """Close an interface keeping the controller alive until the session is cleaned up."""
        if self.session.admin_active:
            raise ValueError(tr("Wait for the administrative task to finish."))
        from makebench.terminal.components import stop_components

        if identifier in self.views:
            stop_components(self.views[identifier].widgets)
        self.open_windows.discard(identifier)
        self.stop_timer(identifier)
        if identifier in self.app_windows:
            self.app_windows[identifier].hide()
        if check_last:
            self.stop_if_last()

    def stop_if_last(self):
        """End after replying to the worker, when no application windows are open."""
        if not self.open_windows:
            self.close_pending = True
            QTimer.singleShot(0, self.stop)

    def has_flow(self, identifier, kind):
        """Whether an event of this kind is bound to the component."""
        return any(
            f["event"] == {"kind": kind, "component": identifier} for f in self.project.workflows
        )

    def start_timer(self, window_id):
        """Tick the window's timer flow while it is open; a tick during a task is skipped."""
        root = next((r for r in self.project.roots if r.id == window_id), None)
        seconds = root.properties.get("timer_seconds", 0) if root else 0
        if not seconds or not self.has_flow(window_id, "timer") or window_id in self._timers:
            return
        timer = QTimer(self)
        timer.setInterval(seconds * 1000)
        timer.timeout.connect(lambda: self._tick(window_id))
        self._timers[window_id] = timer
        timer.start()

    def stop_timer(self, window_id):
        """Stop the window's timer when it closes."""
        timer = self._timers.pop(window_id, None)
        if timer:
            timer.stop()

    def _tick(self, window_id):
        """Run the timer flow only for an open window and an idle session."""
        if window_id in self.open_windows and self.session.active and not self.session.busy:
            self.queue_event(window_id, "timer")

    def close_with_event(self, identifier, action):
        """Run the window's close flow first; `action` closes once it ends (at once without one)."""
        if (
            self.session.active
            and not self.session.busy
            and identifier not in self._closing
            and self.has_flow(identifier, "close")
        ):
            self._closing[identifier] = action
            self.queue_event(identifier, "close")
            return
        action()

    def finish_closing(self):
        """Close the windows whose close flow has ended."""
        if self._closing and not self._queued_flows and not self.session.busy:
            pending, self._closing = list(self._closing.values()), {}
            for action in pending:
                action()

    def widget_for(self, identifier):
        """Find controls in any window already created."""
        if identifier not in {n.id for n in self.project.walk()}:
            node = next(
                (n for n in self.project.walk() if n.properties.get("code_name") == identifier),
                None,
            )
            if node:
                identifier = node.id
        for view in self.views.values():
            if identifier in view.widgets:
                return view, view.widgets[identifier]
        return None, None

    def queue_event(self, component, kind):
        """Pick the specific filter before the generic one; keep document order."""
        owner = self.project.window_of(component)
        if owner is None:
            return
        state = self.active_states[owner.id]
        matches = [
            f
            for f in self.project.workflows
            if f["event"] == {"kind": kind, "component": component}
        ]
        specific = [f for f in matches if state in f.get("states", [])]
        flows = specific or [f for f in matches if not f.get("states")]
        self._queued_flows.extend(f["id"] for f in flows)
        self.dispatch_next()

    def dispatch_next(self):
        """Fire a pending flow only after the previous one replied."""
        if self._queued_flows and self.session.active and not self.session.busy:
            flow_id = self._queued_flows.pop(0)
            flow = next(f for f in self.project.workflows if f["id"] == flow_id)
            self.current_window = self.project.window_of(flow["event"]["component"]).id
            self.session.dispatch(flow_id)
