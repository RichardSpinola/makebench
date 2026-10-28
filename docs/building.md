# Building and testing

Everything here runs from a source checkout inside a virtual environment.
Nothing needs to be installed system-wide; build tools for packages run in
rootless Podman containers.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install ruff==0.17.2
```

Run the editor with `./run-makebench`, or `./run-makebench path/to/project.makebench.json`
to open a project. `./run-makebench --run project.makebench.json` runs a project
in a test window without the editor. Set `MAKEBENCH_LANGUAGE=pt_BR` to try the
Portuguese interface without changing your preferences.

## Tests

The suite runs offscreen and does not touch your editor preferences:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

Additional checks, all run by CI:

```bash
.venv/bin/ruff format --check src tests checks examples
.venv/bin/python checks/i18n.py
QT_QPA_PLATFORM=offscreen .venv/bin/python checks/blockly_smoke.py
```

`checks/blockly_smoke.py` drives the real Blockly page in WebEngine, with GPU
acceleration disabled.

Longer acceptance checks live in `checks/` and write their evidence to a folder
you pass as the first argument. Keep that folder outside the repository. Among
them:

| Check | What it covers |
|---|---|
| `capture_ui.py OUT` | Screenshots of every area at several sizes (used for the README images). |
| `gtk_runtime_smoke.py` | The GTK 4 runtime: dialogs, `ctx` API, tasks, errors, exported source. Needs PyGObject and GTK 4. |
| `terminal_debug_acceptance.py`, `workspace_acceptance.py` | Terminal, debugger and code workspace end to end. |
| `python_compatibility.py OUT --minor 12\|13` | The full suite on Python 3.12 or 3.13 inside a container, using already prepared wheels. |
| `build_portable_examples.py OUT --backend qt\|gtk [--prepare] [--editor]` | Builds the examples (or the editor) in every package format. `--prepare` downloads and verifies the tools first. |
| `polkit/` | Real Polkit authorisation in a disposable container; see its README. |
| `vm/` | Installs and launches packages in QEMU virtual machines. |

## Packages

The same builders are used by the Export window and by
`checks/build_portable_examples.py`:

- **Source** (ZIP): no tools needed.
- **DEB, RPM, AppImage**: a bundled Python runtime and the chosen toolkit,
  prepared in rootless Podman containers based on Ubuntu 24.04. Packages need
  glibc 2.39 or newer.
- **Flatpak**: `flatpak-builder` with the GNOME (GTK) or KDE (Qt) runtime.

Prepared tools and wheels are cached in `~/.cache/makebench/builders`
(`$XDG_CACHE_HOME` is honoured). Downloads are pinned and checked by hash. A
build only assembles a staging folder; it never runs the project.

To build the **editor itself as an AppImage**, open the Export window and choose
**Makebench editor (AppImage)** in the **Export** field, or run:

```bash
.venv/bin/python checks/build_portable_examples.py ~/makebench-builds --backend qt --editor --prepare
```

## Translations

English strings in the source are the message ids. Each language has one
gettext catalog, `src/makebench/locale/<code>/makebench.po`, read directly at
run time (no compiled `.mo` files).

1. Wrap user-visible text in `tr("...")`, or `ntr("singular", "plural", count)`
   for counts. Use named placeholders: `tr("Saved {name}").format(name=...)`.
2. Run `python checks/i18n.py --update` to append new ids to every catalog with
   an empty translation.
3. Fill in the `msgstr` values. Placeholders must match the English text.
4. `python checks/i18n.py` reports missing or mismatched entries and fails if any
   are missing. Untranslated text falls back to English at run time.

The Blockly page has its own small dictionary in `src/makebench/web/logic.js`,
and Blockly's own messages come from its bundled `en.js` and `pt-br.js`.

To add a language, add its code and name to `LANGUAGES` in
`src/makebench/i18n.py`, create its `.po` file, and add a Blockly page like
`web/index.pt_BR.html` if Blockly ships that language.

## Bundled Blockly

Blockly 13.4.0 comes from the official `blockly` npm package, with its SHA-512
integrity checked, and is vendored under `src/makebench/web/vendor/blockly/`.
`vendor-lock.json` there records the URL, integrity, Apache-2.0 license and the
copied files: the core and blocks bundles, the `en` and `pt-br` messages, and
images and cursors. Sounds are disabled and not distributed. The original
`LICENSE` and `package.json` are kept. There is no CDN, no download at run time and
no Node.js needed to open the editor.

The page (`index.html`, `index.pt_BR.html`, `logic.js`, `style.css`) exchanges only
data with Python over Qt WebChannel; no bridge function runs Python or system commands.

Updating Blockly requires reviewing the serialization API, the license and the
tests in `checks/blockly_smoke.py`. Test block comments and the explicitly
registered `WorkspaceCommentSerializer` for free comments in particular. Keep
the neutral logic model, and migrate saved versions before changing the protocol.
