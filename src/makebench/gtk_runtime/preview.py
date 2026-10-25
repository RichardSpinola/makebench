"""Renderização GTK isolada e inerte: recebe só componentes e imagens, nunca código."""

import base64
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def _walk(root):
    """Percorre apenas dados de componentes para declarar a versão mínima da prévia."""
    yield root
    for child in root.get("children", []):
        yield from _walk(child)


def render(input_path, output_path):
    """Produz PNG e retângulos GTK em Broadway privado, sem conectar eventos do projeto."""
    data = json.loads(Path(input_path).read_text())
    directory = Path(output_path).parent
    environment = dict(
        os.environ,
        XDG_RUNTIME_DIR=str(directory),
        GDK_BACKEND="broadway",
        BROADWAY_DISPLAY=":1",
        GSK_RENDERER="cairo",
    )
    os.environ.update(
        {
            key: environment[key]
            for key in ("XDG_RUNTIME_DIR", "GDK_BACKEND", "BROADWAY_DISPLAY", "GSK_RENDERER")
        }
    )
    server = subprocess.Popen(
        ["gtk4-broadwayd", "--unixsocket=" + str(directory / "http.socket"), ":1"],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    def interrupted(*_args):
        """Fecha o display filho também quando o editor cancela ou encerra."""
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, interrupted)
    try:
        deadline = time.monotonic() + 3
        while not any(directory.glob("broadway*.socket")):
            if server.poll() is not None:
                raise RuntimeError(server.stderr.read().decode(errors="replace"))
            if time.monotonic() > deadline:
                raise RuntimeError("O display privado GTK não ficou disponível.")
            time.sleep(0.02)
        import gi

        for name, version in [("Gtk", "4.0"), ("Graphene", "1.0")]:
            gi.require_version(name, version)
        from gi.repository import Gtk, Gdk, GLib, Graphene

        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise RuntimeError("GTK não abriu o display privado.")
        Adw = None
        try:
            gi.require_version("Adw", "1")
            from gi.repository import Adw

            Adw.init()
            if data.get("scheme") in ("dark", "light"):
                Adw.StyleManager.get_default().set_color_scheme(
                    Adw.ColorScheme.FORCE_DARK
                    if data["scheme"] == "dark"
                    else Adw.ColorScheme.FORCE_LIGHT
                )
        except (ValueError, ImportError):
            pass
        from makebench.core.project import Project
        from .renderer import GtkView

        document = Project.empty().to_dict()
        document["ui"] = data["root"]
        document["format_version"] = (
            6 if any(n.get("kind") == "terminal" for n in _walk(data["root"])) else 4
        )
        document["ui"]["properties"].pop("initial_state", None)
        project = Project.from_dict(document)
        assets = data.get("assets", {})
        view = GtkView(
            project.root, lambda key: base64.b64decode(assets[key]), lambda _identifier: None
        )
        for identifier, page_id in data.get("visible_pages", {}).items():
            node = project.find(identifier)
            if node and identifier in view.tabs:
                index = next(
                    (i for i, child in enumerate(node.children) if child.id == page_id), None
                )
                if index is not None:
                    view.tabs[identifier].set_current_page(index)
        window = Adw.Window() if Adw else Gtk.Window()
        if Adw:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.append(Adw.HeaderBar())
            box.append(view.widget)
            view.widget.set_vexpand(True)
            window.set_content(box)
        else:
            window.set_titlebar(Gtk.HeaderBar())
            window.set_child(view.widget)
        window.set_title(project.root.properties.get("title", "Aplicativo"))
        window.set_default_size(
            project.root.properties.get("width", 640), project.root.properties.get("height", 480)
        )
        window.set_resizable(project.root.properties.get("resizable", True))
        window.present()
        loop = GLib.MainLoop()
        errors = []

        def snapshot():
            """Usa o renderizador GTK real, incluindo controles, fontes e barra Adwaita."""
            try:
                width, height = window.get_width(), window.get_height()
                paintable = Gtk.WidgetPaintable.new(window)
                snapshot = Gtk.Snapshot.new()
                paintable.snapshot(snapshot, width, height)
                node = snapshot.to_node()
                if node is None:
                    raise RuntimeError("GTK ainda não produziu a imagem da janela.")
                texture = window.get_renderer().render_texture(
                    node, Graphene.Rect().init(0, 0, width, height)
                )
                image = Path(output_path).with_suffix(".png")
                if not texture.save_to_png(str(image)):
                    raise RuntimeError("GTK não gravou a imagem da prévia.")
                rectangles = {}
                for identifier, widget in view.frames.items():
                    if not widget.get_mapped():
                        continue
                    ok, rect = widget.compute_bounds(window)
                    if ok:
                        rectangles[identifier] = [
                            rect.get_x(),
                            rect.get_y(),
                            rect.get_width(),
                            rect.get_height(),
                        ]
                tabs = {}
                for notebook in view.tabs.values():
                    for index in range(notebook.get_n_pages()):
                        child = notebook.get_nth_page(index)
                        label = notebook.get_tab_label(child)
                        identifier = next(
                            (key for key, frame in view.frames.items() if frame is child), None
                        )
                        if identifier and label.get_mapped():
                            ok, rect = label.compute_bounds(window)
                            if ok:
                                tabs[identifier] = [
                                    rect.get_x(),
                                    rect.get_y(),
                                    rect.get_width(),
                                    rect.get_height(),
                                ]
                Path(output_path).write_text(
                    json.dumps(
                        {"width": width, "height": height, "rectangles": rectangles, "tabs": tabs}
                    )
                )
            except BaseException as exc:
                errors.append(exc)
            finally:
                window.destroy()
                loop.quit()
            return False

        GLib.timeout_add(180, snapshot)
        loop.run()
        if errors:
            raise errors[0]
    finally:
        server.terminate()
        try:
            server.wait(timeout=2)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
