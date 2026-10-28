# Writing Makebench plugins

Plugins add menu commands, project templates, reusable pieces and code snippets to
the editor. They are plain Python, so a plugin runs **with your user's permissions**:
Makebench ships with every plugin turned off, and asks before turning one on. Only
install plugins from people you trust.

## Where plugins live

```
~/.local/share/makebench/plugins/<id>/
    plugin.json
    plugin.py
```

Use **Plugins › Manage plugins…** to install a folder, open the plugins folder and
turn each plugin on or off. Nothing from a plugin is imported until you turn it on.

## plugin.json

```json
{
  "id": "word-count",
  "name": "Word count",
  "version": "1.0.0",
  "api": 1,
  "description": "What it does, in a sentence.",
  "author": "Your name"
}
```

`id` must match the folder name (lowercase letters, digits, `-` and `_`). `api`
is `1` or `2`; any other value is shown as incompatible and never loaded.

## plugin.py

```python
def register(api):
    def shout(project):            # `project` is a copy you may change
        project.root.properties["title"] = project.root.properties["title"].upper()

    api.add_command("Shout the title", shout)
    api.add_snippet("greet", 'ctx.message("Hello")\n')
    api.add_piece(piece_dict)      # same JSON as a saved reusable piece
```

- `api.add_command(name, function)` adds the command to the **Plugins** menu. The
  function receives a copy of the project; when it returns, the result replaces
  the project as **one undoable change**.
- `api.add_snippet(name, code)` offers `code` in the Code area's suggestions
  (Ctrl+Space) when you type the start of `name`.
- `api.add_piece(piece)` adds a ready-made piece to **Edit › Insert piece**.

## API v2

Plugins that declare `"api": 2` can also use:

- `api.add_template(name, description, build)` adds a model to **New project** and to
  the start screen. `build(name)` returns a new `Project`.
- Commands that take two parameters, `function(project, context)`, receive a
  `context` with `window` (the id of the window open in Design), `parent` (a widget
  to open dialogs on), `read_asset(name)` and `import_image(path)`, which copies an
  image into the project and returns its `assets/...` name.
- `raise api.Refusal("message")` stops a command with a message for the person,
  without turning the plugin off. Return without changes (a cancelled dialog) and
  nothing is added to the history.

## Official plugins

Some plugins ship with Makebench. They are listed as **Official** in
**Manage plugins…**, start turned off like any other, and live in
`src/makebench/pluginpack/`. A plugin you install cannot reuse their ids.

**Web view** (`pluginpack/webview`) is the reference for API v2. It adds a Web view
template and commands to turn a window into a Web view, back into a normal window,
and to edit its page with a live preview. A Web view window shows one HTML page,
edge to edge, and holds no components; links to websites open in the browser.
Makebench itself shows, saves and exports these windows, so projects made with the
plugin keep working with it turned off. The exported Qt app needs Qt WebEngine, and
the GTK runtime needs WebKitGTK 6.

## Safety and failures

If `register` or a command raises an error, only that plugin is turned off, and
the message is shown in **Manage plugins…**. The editor keeps running and your
project is not changed by a failed command.

A full example is in `examples/plugins/word-count`.
