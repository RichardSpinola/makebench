# SPDX-License-Identifier: MIT
"""Translation of the neutral model into real GTK4 controls."""

from makebench.core.project import ComponentKind, LayoutKind
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

    def __init__(self, root, read_asset, clicked):
        """Build widgets; never imports functions or starts document events."""
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk, Gdk, GLib

        self.Gtk, self.Gdk, self.GLib = Gtk, Gdk, GLib
        self.root = root
        self.read_asset = read_asset
        self.clicked = clicked
        self.widgets = {}
        self.frames = {}
        self.tabs = {}
        self.enabled = {}
        self.hints = set()  # outputs still showing their starting text
        self.widget = self.render(root)
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
        elif k == ComponentKind.CHECKBOX:
            widget = Gtk.CheckButton(label=text, active=p.get("checked", False))
        elif k == ComponentKind.PROGRESS:
            widget = Gtk.ProgressBar(show_text=True, fraction=p.get("value", 0) / 100)
        elif k == ComponentKind.TERMINAL:
            from makebench.terminal.gtk import create_terminal

            widget = create_terminal()
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

    def set_text(self, identifier, value):
        """Update text using each GTK control's specific API."""
        w = self.widgets[identifier]
        Gtk = self.Gtk
        if hasattr(w, "_makebench_label"):
            w._makebench_label.set_label(str(value))
        elif isinstance(w, Gtk.TextView):
            w.get_buffer().set_text(str(value))
            self.hints.add(identifier)
        elif isinstance(w, (Gtk.Button, Gtk.CheckButton, Gtk.Label)):
            w.set_label(str(value))
        elif isinstance(w, Gtk.Entry):
            w.set_text(str(value))
        else:
            raise ValueError(tr("This component has no text."))

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
            return w.get_text() if isinstance(w, Gtk.Entry) else w.get_label()
        if attribute == "checked":
            return w.get_active()
        if attribute == "value":
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
