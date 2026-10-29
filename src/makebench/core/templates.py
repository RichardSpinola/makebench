# SPDX-License-Identifier: MIT
"""Structure templates: pure data, never loading or running user functions."""

from .project import Project, ComponentKind, LayoutKind, new_id
from .navigation import welcome_template, add_window
from .logic import create_flow
from makebench.i18n import tr

MODELS = [
    ("simple", tr("Simple application"), tr("One window with text, a field and a button.")),
    ("welcome", tr("Wizard"), tr("Three steps with Back, Next and Finish.")),
    ("tasks", tr("Task center / utility"), tr("Scripts, progress and output.")),
    ("multi", tr("Multi-window application"), tr("Sidebar and a preferences window.")),
    ("blank", tr("Blank"), tr("One window to start your own way.")),
    (
        "html",
        tr("Light HTML app"),
        tr("One HTML page on GTK: it uses the system's web engine, so the package has no Qt."),
    ),
]


def light_page(title):
    """Starting page of the light HTML app: plain HTML, CSS and a little JavaScript."""
    from html import escape

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; --accent: #3584e4; }}
  body {{ margin: 0; font-family: system-ui, sans-serif; display: grid;
         place-items: center; min-height: 100vh; }}
  main {{ max-width: 34rem; padding: 2rem; text-align: center; }}
  h1 {{ color: var(--accent); }}
  button {{ font: inherit; padding: .5rem 1.5rem; border: 0; border-radius: .5rem;
           background: var(--accent); color: white; cursor: pointer; }}
</style>
</head>
<body>
<main>
  <h1>{escape(title)}</h1>
  <p>{escape(tr("This window is a web page. Edit it with Plugins › Edit Web view page…"))}</p>
  <button id="count">{escape(tr("Clicked"))} <span>0</span></button>
</main>
<script>
  const button = document.getElementById("count");
  let clicks = 0;
  button.addEventListener("click", () => {{
    button.querySelector("span").textContent = ++clicks;
  }});
</script>
</body>
</html>
"""


def make_template(key, name):
    """Create independent templates; tasks uses the example shipped with the editor."""
    if key == "welcome":
        p = welcome_template(name)
        p.root.properties.update(width=520, height=430, padding=24, spacing=18)
        return p
    p = Project.empty(name)
    p.root.properties.update(width=720, height=480, padding=24, spacing=18)
    if key == "blank":
        return p
    if key == "html":
        # GTK shows the page with the system's WebKitGTK; Qt would need Qt WebEngine.
        p.application["backend"] = "gtk"
        p.root.properties.update(width=760, height=520, web_page=light_page(name))
        return p
    if key == "simple":
        text = p.add(p.root.id, ComponentKind.LABEL)
        text.properties["text"] = tr("Your application starts here")
        entry = p.add(p.root.id, ComponentKind.TEXT_INPUT)
        entry.properties["placeholder"] = tr("Type your name")
        button = p.add(p.root.id, ComponentKind.BUTTON)
        button.properties["text"] = tr("Continue")
        create_flow(p, button.id)["body"] = [
            {
                "id": new_id("block"),
                "op": "message",
                "value": {"id": new_id("value"), "op": "literal", "value": tr("Ready to create!")},
            }
        ]
    elif key == "multi":
        p.root.layout = LayoutKind.HORIZONTAL
        sidebar = p.add(p.root.id, ComponentKind.CONTAINER)
        sidebar.properties.update(
            padding=12, spacing=12, size_mode={"width": "fixed", "height": "fill"}
        )
        sidebar.geometry["width"] = 190
        title = p.add(sidebar.id, ComponentKind.LABEL)
        title.properties["text"] = tr("My application")
        preferences = p.add(sidebar.id, ComponentKind.BUTTON)
        preferences.properties["text"] = tr("Preferences")
        content = p.add(p.root.id, ComponentKind.CONTAINER)
        content.properties.update(
            padding=24, spacing=18, size_mode={"width": "fill", "height": "fill"}
        )
        heading = p.add(content.id, ComponentKind.LABEL)
        heading.properties["text"] = tr("Workspace")
        output = p.add(content.id, ComponentKind.OUTPUT)
        output.properties["text"] = tr("Organize your tools in this area.")
        window = add_window(p, tr("Preferences"))
        window.properties.update(width=480, height=360, padding=24, spacing=18)
        option = p.add(window.id, ComponentKind.CHECKBOX)
        option.properties["text"] = tr("Enable notifications")
        close = p.add(window.id, ComponentKind.BUTTON)
        close.properties["text"] = tr("Finish")
        create_flow(p, preferences.id)["body"] = [
            {
                "id": new_id("block"),
                "op": "open_window",
                "window": window.id,
                "close_current": False,
            }
        ]
        create_flow(p, close.id)["body"] = [{"id": new_id("block"), "op": "close_window"}]
    return p
