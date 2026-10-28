# Architecture

This is an overview for contributors. Package layout under `src/makebench/`:

| Package | Role |
|---|---|
| `core/` | Project model, logic model, code generation, storage, packaging. **Never imports Qt.** |
| `editor/` | The Qt workbench: Map, Design, Logic (blocks or Python), Export, preferences. |
| `ui/` | Rendering shared by the Design canvas and the Qt runtime; dialogs; theme. |
| `runtime/` | Running a project: worker process, supervised tasks, debugger, Qt window. |
| `gtk_runtime/` | The same runtime contract on GTK 4, plus the GTK design preview. No Qt. |
| `terminal/` | PTY sessions and the terminal component shared by Qt and GTK. |
| `web/` | The local Blockly page used by the Logic area. |
| `portable/`, `templates/`, `locale/`, `notices/` | Packaging helpers, new-project templates, translations, licenses. |

## Principles

- **Opening, editing, previewing, saving and building never run project code.**
  Python is parsed with `ast`, never imported, except in the test process
  started by F5/F9 and in exported applications.
- **The document is the authority.** Canvas, tree, map and Blockly are views.
  Each gesture is one history entry; Esc cancels a gesture in progress.
- **Native look.** Qt uses the desktop style and palette (no global QSS); GTK
  previews are rendered by GTK itself.
- **No network at run time.** Blockly and its media are bundled; the web page has
  a CSP that blocks connections.

## Document

`core/project.py` defines `Project`, `Component`, component types and layouts,
and the JSON format. The reader accepts formats 1–10, except projects that use
the node editor removed in 1.0. Format 9 adds `metadata.programming`: each
project is written in `blocks` or `python`. For older projects,
`infer_programming()` picks blocks when there are flows, Python when there are
modules or an edited functions file, and nothing for an empty project, so the
editor asks. Saving writes the lowest format that holds the
features in use (6 terminal, 8 Python modules, 9 programming choice, 10 the 1.0 components and events) and never lowers a newer format
already declared. When a save upgrades the format, the previous file is kept as
`.bak-vN`.

`core/storage.py` has a single save path, `save_workspace()`, used by both the
headless `Document` and the editor window. It validates, writes assets and
Python files, then the project JSON (each through a temporary file, `fsync` and
`os.replace`), then marks the sources saved. The set of files is not
transactional, and the error says which files were written.

Format 10 adds the number, slider, long text, choice, date and table components,
the `change`, `close`, `timer` and `menu` events, window `menus`, `frame`,
`centered` and `on_top`. A menu event is `menu:<item id>` (ids are made from the
item text by `core/menus.py` and kept when the text is edited), so flows still
match events by equality. A change made through `ctx` never fires `change`:
Qt blocks signals and GTK sets a `programmatic` flag. `close` does not cancel.

`core/history.py` keeps labelled snapshots of interface and logic (200 by
default). Python files use the text editor's own undo stack.

## Logic

`core/logic.py` validates the neutral logic model (`metadata.logic_version = 1`):
events (`start` on a window, `click` on a button), statements and expressions,
each with an id. A flow whose `body` is `null` is a draft and generates no code.
In Python projects a flow has `function` instead of `body`/`workspace`: the
handler calls `ctx.handle_event(name)`, and `codegen.convert_to_python()` turns
block flows into such functions.
Block functions live in `metadata.functions` as `{id, name, params, body,
workspace}`. Codegen emits them first as `def fn_<name>(ctx, *params)` with the
inputs copied into `local_variables`; `call_function` (statement or value) refers
to the function by id and passes `args` in order, and `return` is only valid
inside a function. Conversion to Python copies these definitions as they are.
Flows and functions may carry an optional `module` name (1–60 characters) that
only groups them in the sidebar.
Limits: 48 levels and 5000 nodes per flow.

- `web/logic.js` translates Blockly blocks to and from this model. On opening, it
  compiles the saved workspace and rebuilds the blocks from the model if they
  disagree. Free text fields are never treated as Python.
- `core/codegen.py` generates deterministic handlers against the `ctx` API.
  Values are escaped with `repr`, operators come from an allow list, and
  `GeneratedCode.lines` maps `(flow_id, block_id)` to a line for highlighting,
  error navigation and breakpoints.
- `core/navigation.py` derives the Map's windows, states and edges from real
  navigation actions, and edits those actions when you draw links.

### Blockly bridge

`editor/logic.py` loads WebEngine lazily. The page runs in a temporary profile,
can only navigate to the bundled entry page, and the request interceptor allows
only bundled resources. `LogicBridge` exchanges JSON, selection and status only:
no shell, file or import functions are exposed. Before saving, switching or
undoing, the editor flushes the workspace directly through JavaScript; messages
from an older context are ignored by token.

## Your Python

`core/source.py` reads the project's `.actions.py` file and the declared
`makebench_user` modules as UTF-8. `SourceText` carries a snapshot of every file,
so the worker imports the snapshot rather than the live folder. Invalid source
stays editable and savable. External changes are detected against the original
content. `core/code_index.py`, `editor/code_assist.py` and
`editor/code_workspace.py` provide static suggestions, definitions and diagnostics.

## Running and debugging

- `runtime/worker.py` runs handlers in a separate process. The control protocol
  is JSON on a duplicated stdout descriptor; fd 1 is redirected to stderr so
  ordinary prints cannot be mistaken for control messages.
- `runtime/session.py` supervises the worker with `QProcess` in its own session.
  Tasks run in separate `QProcess`es; a non-zero exit raises `TaskError`, and
  stderr alone is not a failure. Stop sends TERM, then KILL after 700 ms.
- `runtime/process.py` resolves programs without an implicit shell. Bash is used
  only by explicit script actions, with arguments passed as positional parameters.
- Administrative tasks use `pkexec --disable-internal-agent` and stay supervised
  even if the worker dies. Makebench never collects passwords.
- `runtime/debugger.py` provides breakpoints by block id or file/line and a
  bounded, read-only snapshot of the stack and variables.
- `gtk_runtime/` implements the same `ctx` operations for GTK 4;
  `runtime/gtk_bridge.py` supervises it from Qt.

The test process is **not a sandbox**: project code runs with the user's
permissions.

## Distribution

- `core/packages.py` and `core/exporter.py` build Python source, DEB, RPM,
  AppImage and Flatpak packages in an inert staging folder. Metadata is
  sanitised to one line so it cannot inject desktop entries or commands.
- `core/build_environment.py` prepares tools explicitly in rootless Podman
  containers, with pinned official downloads and hash-checked wheels, under
  `~/.cache/makebench/builders`.
- `core/portable.py` prepares the bundled Python runtime and builds the editor
  AppImage.
- `editor/publish.py` is the Export window; preparation and builds run on worker
  threads with visible output and cancellation.

## Interface language

`makebench/i18n.py` provides `tr()` and `ntr()`. English source strings are the
message ids; `locale/<code>/makebench.po` files are read directly (no `.mo`
step). The language is set before modules that build translated constants are
imported, and is passed to child processes through `MAKEBENCH_LANGUAGE`. The
Blockly page loads `index.html` (English) or `index.pt_BR.html`, and
`web/logic.js` keeps its own small dictionary. See
[building.md](building.md#translations) for the workflow.
