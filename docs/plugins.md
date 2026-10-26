# Writing Makebench plugins

Plugins add menu commands, reusable pieces and code snippets to the editor. They
are plain Python, so a plugin runs **with your user's permissions**: Makebench
ships with every plugin turned off, and asks before turning one on. Only install
plugins from people you trust.

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
must be `1`; any other value is shown as incompatible and never loaded.

## plugin.py (API v1)

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

## Safety and failures

If `register` or a command raises an error, only that plugin is turned off, and
the message is shown in **Manage plugins…**. The editor keeps running and your
project is not changed by a failed command.

A full example is in `examples/plugins/word-count`.
