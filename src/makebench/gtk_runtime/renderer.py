# SPDX-License-Identifier: MIT
"""Translation of the neutral model into real GTK4 controls."""

from pathlib import Path

from makebench.core.project import RANGE_DEFAULTS, RANGE_KINDS, ComponentKind, LayoutKind
from makebench.core.web import WEB_PAGE, is_web, materialize
from makebench.i18n import tr


def layout_spec(node):
    """Extract testable geometry without initializing GTK or running the project."""
    p = node.properties
    return {
        "kind": node.kind.value,
        "layout": node.layout.value,
        "spacing": p.get("spacing", 6),
        "padding": p.get("padding", 8),
        "columns": p.get("columns", 2),
        "align": p.get("align", "stretch"),
        "distribution": p.get("distribute", "start"),
        "size": p.get("size_mode", {}),
        "geometry": dict(node.geometry),
        "children": [layout_spec(c) for c in node.children],
    }


class GtkView:
    """One rendered window, with controls reachable through the ctx API."""

    def __init__(self, root, read_asset, clicked, changed=None):
        """Build widgets; never imports functions or starts document events."""
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk, Gdk, GLib, GObject

        self.Gtk, self.Gdk, self.GLib, self.GObject = Gtk, Gdk, GLib, GObject
        self.root = root
        self.read_asset = read_asset
        self.clicked = clicked
        self.changed = changed
        self.programmatic = False  # true while the app, not the user, edits a control
        self.widgets = {}
        self.frames = {}
        self.tabs = {}
        self.enabled = {}
        self.hints = set()  # outputs still showing their starting text
        self.ranges = set()  # numbers and sliders
        self.areas = set()  # long text inputs
        self.choices = set()  # choice lists
        self.dates = set()  # date pickers
        self.tables = {}  # id -> (Gio.ListStore, Gtk.SingleSelection)
        self.widget = self.web_page(root) if is_web(root) else self.render(root)
        self.style_changes = {}
        self.provider = None
        self.css_class = "mb-window-" + str(id(self))
        self.widget.add_css_class(self.css_class)
        self.apply_style()

    def apply_style(self):
        """One CssProvider per window, scoped by a class so other windows keep their look."""
        from makebench.core.style import gtk_css, window_style

        Gtk, Gdk = self.Gtk, self.Gdk
        css = gtk_css(window_style({**self.root.properties, **self.style_changes}), self.css_class)
        display = Gdk.Display.get_default()
        if self.provider is not None and display is not None:
            Gtk.StyleContext.remove_provider_for_display(display, self.provider)
            self.provider = None
        if css and display is not None:
            self.provider = Gtk.CssProvider()
            if hasattr(self.provider, "load_from_string"):
                self.provider.load_from_string(css)
            else:
                self.provider.load_from_data(css.encode())
            Gtk.StyleContext.add_provider_for_display(
                display, self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def change_style(self, **changes):
        """Used by ctx.set_theme/set_background while the application runs."""
        self.style_changes.update(changes)
        self.apply_style()

    def web_page(self, root):
        """Show the page with WebKitGTK; websites open in the browser, not in the window."""
        Gtk = self.Gtk
        try:
            import gi

            gi.require_version("WebKit", "6.0")
            from gi.repository import Gio, WebKit
        except (ImportError, ValueError):
            label = Gtk.Label(label=tr("This window needs WebKitGTK 6 to show its page."))
            label.set_wrap(True)
            self.widgets[root.id] = self.frames[root.id] = label
            return label
        page = materialize(root.properties[WEB_PAGE], self.read_asset)
        folder = page.parent

        def decide(_view, decision, kind):
            if kind != WebKit.PolicyDecisionType.NAVIGATION_ACTION:
                return False
            uri = decision.get_navigation_action().get_request().get_uri()
            scheme = uri.split(":", 1)[0]
            if scheme in {"http", "https", "mailto"}:
                Gio.AppInfo.launch_default_for_uri(uri, None)
                decision.ignore()
            elif scheme == "file":
                inside = Path(Gio.File.new_for_uri(uri).get_path()).resolve().is_relative_to(folder)
                decision.use() if inside else decision.ignore()
            elif scheme not in {"data", "about"}:
                decision.ignore()
            return True

        view = WebKit.WebView()
        view.connect("decide-policy", decide)
        view.set_vexpand(True)
        view.set_hexpand(True)
        view.load_uri(page.as_uri())
        self.widgets[root.id] = self.frames[root.id] = view
        return view

    def render(self, node):
        """Map every basic type, layout and initial value to GTK."""
        Gtk = self.Gtk
        p = node.properties
        k = node.kind
        text = p.get("text", "")
        if k == ComponentKind.PAGES:
            widget = Gtk.Notebook()
            self.tabs[node.id] = widget
            for child in node.children:
                widget.append_page(
                    self.render(child), Gtk.Label(label=child.properties.get("title", tr("Page")))
                )
            widget.set_current_page(
                next(i for i, c in enumerate(node.children) if c.id == p["initial_page"])
            )
        elif node.can_have_children:
            if node.layout == LayoutKind.FREE:
                widget = Gtk.Fixed()
            elif node.layout == LayoutKind.GRID:
                widget = Gtk.Grid(
                    row_spacing=p.get("spacing", 6), column_spacing=p.get("spacing", 6)
                )
            else:
                widget = Gtk.Box(
                    orientation=Gtk.Orientation.HORIZONTAL
                    if node.layout == LayoutKind.HORIZONTAL
                    else Gtk.Orientation.VERTICAL,
                    spacing=p.get("spacing", 6),
                )
            pad = p.get("padding", 8)
            for direction in ("top", "bottom", "start", "end"):
                getattr(widget, "set_margin_" + direction)(pad)
            if isinstance(widget, Gtk.Box) and p.get("distribute") in {"center", "end"}:
                widget.append(self.spacer(node))
            for index, child in enumerate(node.children):
                rendered = self.render(child)
                align = {
                    "start": Gtk.Align.START,
                    "center": Gtk.Align.CENTER,
                    "end": Gtk.Align.END,
                    "stretch": Gtk.Align.FILL,
                }[p.get("align", "stretch")]
                if node.layout == LayoutKind.VERTICAL:
                    rendered.set_halign(align)
                elif node.layout == LayoutKind.HORIZONTAL:
                    rendered.set_valign(align)
                if isinstance(widget, Gtk.Fixed):
                    widget.put(rendered, float(child.geometry["x"]), float(child.geometry["y"]))
                    rendered.set_size_request(child.geometry["width"], child.geometry["height"])
                elif isinstance(widget, Gtk.Grid):
                    widget.attach(
                        rendered, index % p.get("columns", 2), index // p.get("columns", 2), 1, 1
                    )
                else:
                    widget.append(rendered)
                    if p.get("distribute") == "space-between" and index < len(node.children) - 1:
                        widget.append(self.spacer(node))
            if isinstance(widget, Gtk.Box) and p.get("distribute", "start") in {"start", "center"}:
                widget.append(self.spacer(node))
            if p.get("alignment_preset") and isinstance(widget, Gtk.Grid):
                vertical, horizontal = p["alignment_preset"].split("-")
                mapping = {
                    "top": Gtk.Align.START,
                    "left": Gtk.Align.START,
                    "center": Gtk.Align.CENTER,
                    "right": Gtk.Align.END,
                    "bottom": Gtk.Align.END,
                }
                widget.set_halign(mapping[horizontal])
                widget.set_valign(mapping[vertical])
        elif k == ComponentKind.SEPARATOR:
            widget = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        elif k == ComponentKind.SPACER:
            widget = Gtk.Box(hexpand=True, vexpand=True)
        elif k == ComponentKind.LABEL:
            widget = Gtk.Label(label=text, wrap=True, xalign=0)
        elif k == ComponentKind.BUTTON:
            widget = Gtk.Button(label=text)
            widget.connect("clicked", lambda _button: self.clicked(node.id))
            if p.get("icon"):
                try:
                    texture = self.Gdk.Texture.new_from_bytes(
                        self.GLib.Bytes.new(self.read_asset(p["icon"]))
                    )
                    content = Gtk.Box(
                        orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.CENTER
                    )
                    image = Gtk.Image.new_from_paintable(texture)
                    image.set_pixel_size(16)
                    content.append(image)
                    widget._makebench_label = Gtk.Label(label=text)
                    content.append(widget._makebench_label)
                    widget.set_child(content)
                except (OSError, ValueError, self.GLib.Error):
                    pass
        elif k == ComponentKind.TEXT_INPUT:
            widget = Gtk.Entry(text=text, placeholder_text=p.get("placeholder", ""))
            widget.connect("changed", lambda _entry: self.user_changed(node.id))
        elif k == ComponentKind.CHECKBOX:
            widget = Gtk.CheckButton(label=text, active=p.get("checked", False))
            widget.connect("toggled", lambda _check: self.user_changed(node.id))
        elif k == ComponentKind.PROGRESS:
            widget = Gtk.ProgressBar(show_text=True, fraction=p.get("value", 0) / 100)
        elif k == ComponentKind.TABLE:
            widget = self.table(node.id, p.get("headers", []))
        elif k == ComponentKind.DATE:
            calendar = Gtk.Calendar()
            widget = Gtk.MenuButton(hexpand=True)
            popover = Gtk.Popover()
            popover.set_child(calendar)
            widget.set_popover(popover)
            widget._makebench_calendar = calendar
            self.widgets[node.id] = widget
            self.dates.add(node.id)
            self._set_text(node.id, text)
            calendar.connect("day-selected", lambda _calendar: self._date_picked(node.id))
        elif k == ComponentKind.CHOICE:
            widget = Gtk.DropDown.new_from_strings([])
            self.widgets[node.id] = widget
            self.choices.add(node.id)
            self.set_options(node.id, p.get("options", []), p.get("text", ""))
            widget.connect("notify::selected", lambda *_: self.user_changed(node.id))
        elif k in RANGE_KINDS:
            r = {**RANGE_DEFAULTS, **p}
            adjustment = Gtk.Adjustment(
                value=r["value"],
                lower=r["minimum"],
                upper=r["maximum"],
                step_increment=r["step"],
                page_increment=max(r["step"], (r["maximum"] - r["minimum"]) / 10),
            )
            if k == ComponentKind.NUMBER:
                widget = Gtk.SpinButton(adjustment=adjustment, digits=r["decimals"], numeric=True)
            else:
                widget = Gtk.Scale(
                    orientation=Gtk.Orientation.HORIZONTAL,
                    adjustment=adjustment,
                    draw_value=True,
                    digits=0,
                    hexpand=True,
                )
            self.ranges.add(node.id)
            widget.connect("value-changed", lambda _widget: self.user_changed(node.id))
        elif k == ComponentKind.TERMINAL:
            from makebench.terminal.gtk import create_terminal

            widget = create_terminal()
        elif k == ComponentKind.TEXT_AREA:
            control = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
            control.get_buffer().set_text(text)
            control.get_buffer().connect("changed", lambda _buffer: self.user_changed(node.id))
            widget = Gtk.ScrolledWindow(min_content_height=80)
            widget.set_child(control)
            self.widgets[node.id] = control
            self.areas.add(node.id)
        elif k == ComponentKind.OUTPUT:
            control = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            control.get_buffer().set_text(text)
            self.hints.add(node.id)
            widget = Gtk.ScrolledWindow(min_content_height=110)
            widget.set_child(control)
            self.widgets[node.id] = control
        elif k == ComponentKind.IMAGE:
            widget = Gtk.Picture()
            widget.set_can_shrink(True)
            widget.set_content_fit(Gtk.ContentFit.CONTAIN)
            if p.get("source"):
                try:
                    widget.set_paintable(
                        self.Gdk.Texture.new_from_bytes(
                            self.GLib.Bytes.new(self.read_asset(p["source"]))
                        )
                    )
                except (OSError, ValueError, self.GLib.Error):
                    widget.set_tooltip_text(
                        tr("Image unavailable: {source}").format(source=p["source"])
                    )
            widget.update_property([Gtk.AccessibleProperty.LABEL], [p.get("alt_text", tr("Image"))])
        else:
            raise ValueError(tr("Unrecognized GTK component: {kind}").format(kind=k))
        self.frames[node.id] = widget
        self.widgets.setdefault(node.id, widget)
        self.enabled[node.id] = p.get("enabled", True)
        widget.set_visible(p.get("visible", True))
        widget.set_sensitive(p.get("enabled", True))
        if p.get("tooltip"):
            widget.set_tooltip_text(p["tooltip"])
        modes = p.get("size_mode", {})
        widget.set_hexpand(modes.get("width") == "fill")
        widget.set_vexpand(modes.get("height") == "fill")
        widget.set_size_request(
            node.geometry["width"] if modes.get("width") == "fixed" else -1,
            node.geometry["height"] if modes.get("height") == "fixed" else -1,
        )
        return widget

    def spacer(self, node):
        """Expand only the main axis to distribute free space."""
        w = self.Gtk.Box()
        w.set_hexpand(node.layout == LayoutKind.HORIZONTAL)
        w.set_vexpand(node.layout != LayoutKind.HORIZONTAL)
        return w

    def user_changed(self, identifier):
        """Report an edit made by the user, never one made through the ctx API."""
        if self.changed and not self.programmatic:
            self.changed(identifier, "change")

    def set_text(self, identifier, value):
        """Update text using each GTK control's specific API."""
        self.programmatic = True
        try:
            self._set_text(identifier, value)
        finally:
            self.programmatic = False

    def table(self, identifier, columns):
        """A column view over a list store of rows; each row keeps its cells as texts."""
        Gtk, GObject = self.Gtk, self.GObject
        from gi.repository import Gio

        class Row(GObject.Object):
            def __init__(self, cells):
                super().__init__()
                self.cells = cells

        store = Gio.ListStore.new(Row)
        selection = Gtk.SingleSelection(model=store, autoselect=False, can_unselect=True)
        view = Gtk.ColumnView(model=selection, hexpand=True, vexpand=True)
        for index, title in enumerate(columns):
            factory = Gtk.SignalListItemFactory()
            factory.connect("setup", lambda _f, item: item.set_child(Gtk.Label(xalign=0)))
            factory.connect(
                "bind",
                lambda _f, item, index=index: item.get_child().set_label(
                    item.get_item().cells[index] if index < len(item.get_item().cells) else ""
                ),
            )
            view.append_column(Gtk.ColumnViewColumn(title=title, factory=factory, expand=True))
        selection.connect("selection-changed", lambda *_: self.user_changed(identifier))
        scroller = Gtk.ScrolledWindow(min_content_height=100)
        scroller.set_child(view)
        self.widgets[identifier] = scroller
        self.tables[identifier] = (store, selection, Row)
        return scroller

    def set_rows(self, identifier, rows):
        """Replace the rows of a table without reporting a change."""
        store, selection, Row = self.tables[identifier]
        self.programmatic = True
        try:
            store.remove_all()
            for row in rows:
                store.append(Row([str(cell) for cell in row]))
        finally:
            self.programmatic = False

    def add_row(self, identifier, row):
        store, selection, Row = self.tables[identifier]
        self.programmatic = True
        try:
            store.append(Row([str(cell) for cell in row]))
        finally:
            self.programmatic = False

    def selected_row(self, identifier):
        store, selection, Row = self.tables[identifier]
        item = selection.get_selected_item()
        return list(item.cells) if item else []

    def _date_picked(self, identifier):
        """The person chose a day: show it and report the change."""
        w = self.widgets[identifier]
        if self.programmatic:
            return
        w.set_label(w._makebench_calendar.get_date().format("%Y-%m-%d"))
        self.user_changed(identifier)

    def _set_text(self, identifier, value):
        w = self.widgets[identifier]
        Gtk = self.Gtk
        if identifier in self.dates:
            from makebench.core.project import valid_date

            if not valid_date(str(value)):
                raise ValueError(tr("A date must be written as YYYY-MM-DD."))
            year, month, day = (int(part) for part in str(value).split("-"))
            was, self.programmatic = self.programmatic, True
            try:
                w._makebench_calendar.select_day(
                    self.GLib.DateTime.new_local(year, month, day, 0, 0, 0)
                )
            finally:
                self.programmatic = was
            w.set_label(str(value))
        elif hasattr(w, "_makebench_label"):
            w._makebench_label.set_label(str(value))
        elif isinstance(w, Gtk.DropDown):
            options = [item.get_string() for item in w.get_model()]
            if str(value) not in options:
                raise ValueError(tr("This option is not in the list."))
            w.set_selected(options.index(str(value)))
        elif isinstance(w, Gtk.TextView):
            w.get_buffer().set_text(str(value))
            if identifier not in self.areas:
                self.hints.add(identifier)
        elif isinstance(w, (Gtk.Button, Gtk.CheckButton, Gtk.Label)):
            w.set_label(str(value))
        elif isinstance(w, Gtk.Entry):
            w.set_text(str(value))
        else:
            raise ValueError(tr("This component has no text."))

    def set_options(self, identifier, options, keep=None):
        """Replace the options of a choice list, selecting `keep` when it is among them."""
        widget = self.widgets[identifier]
        if keep is None:
            item = widget.get_selected_item()
            keep = item.get_string() if item else ""
        options = list(options)
        self.programmatic = True
        try:
            widget.set_model(self.Gtk.StringList.new(options))
            widget.set_selected(options.index(keep) if keep in options else 0)
        finally:
            self.programmatic = False

    def set_range(self, identifier, value):
        """Move a number or slider without telling the application the person did it."""
        widget = self.widgets[identifier]
        adjustment = widget.get_adjustment()
        if not adjustment.get_lower() <= value <= adjustment.get_upper():
            raise ValueError(tr("The value is outside the limits of the component."))
        self.programmatic = True
        try:
            widget.set_value(value)
        finally:
            self.programmatic = False

    def read(self, identifier, attribute):
        """Read the current controls, including changes made by the user."""
        w = self.widgets[identifier]
        Gtk = self.Gtk
        if attribute == "text":
            if hasattr(w, "_makebench_label"):
                return w._makebench_label.get_label()
            if isinstance(w, Gtk.TextView):
                b = w.get_buffer()
                return b.get_text(b.get_start_iter(), b.get_end_iter(), True)
            if isinstance(w, Gtk.DropDown):
                item = w.get_selected_item()
                return item.get_string() if item else ""
            if identifier in self.dates:
                return w.get_label()
            return w.get_text() if isinstance(w, Gtk.Entry) else w.get_label()
        if attribute == "selected":
            if identifier not in self.tables:
                raise ValueError(tr("Unknown property."))
            return self.selected_row(identifier)
        if attribute == "checked":
            return w.get_active()
        if attribute == "value":
            if isinstance(w, (Gtk.SpinButton, Gtk.Scale)):
                value = w.get_value()
                return value if w.get_digits() else int(round(value))
            return round(w.get_fraction() * 100)
            raise ValueError(tr("Unknown property."))

    def show_page(self, project, identifier):
        """Reveal the page and its ancestor tab sets."""
        node = project.find(identifier)
        if node is None or node.kind != ComponentKind.PAGE:
            raise ValueError(tr("The page does not exist."))
        parent = project.parent_of(identifier)
        while parent:
            if parent.kind == ComponentKind.PAGES:
                self.tabs[parent.id].set_current_page(parent.children.index(node))
            node, parent = parent, project.parent_of(parent.id)

    def busy(self, value, event_buttons):
        """Block concurrent events, keeping the enabled state set by the application."""
        for identifier in event_buttons & self.widgets.keys():
            self.widgets[identifier].set_sensitive(self.enabled[identifier] and not value)
