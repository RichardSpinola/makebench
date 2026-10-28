# Makebench

[![Checks](https://github.com/RichardSpinola/makebench/actions/workflows/checks.yml/badge.svg)](https://github.com/RichardSpinola/makebench/actions/workflows/checks.yml)
[![License: GPL-3.0-or-later + MIT](https://img.shields.io/badge/license-GPL--3.0--or--later%20%2B%20MIT-blue.svg)](#license)

**Build Linux desktop applications visually — and keep the code.**

Makebench is a visual editor for native Linux applications. You design windows
with real Qt or GTK 4 controls, describe what happens with blocks, write
your own Python where you want it, and export a runnable application or a
DEB, RPM, AppImage or Flatpak package. Everything runs locally: no account, no
server and no AI at run time.

[Leia em português](README.pt-BR.md) ·
[User guide](docs/user-guide.md) ·
[Architecture](docs/architecture.md) ·
[Building and testing](docs/building.md) ·
[Contributing](CONTRIBUTING.md)

![The Design area with a native Qt preview, component tree and properties](docs/images/design.png)

> **Status: alpha (0.9.0).** The editor is usable and covered by an
> automated test suite, but the project format and APIs may still change.
> Download the AppImage from the
> [releases page](https://github.com/RichardSpinola/makebench/releases), or run it from source (below).

## What you can do

- **Map** every window and state of your application and connect them by
  dragging between ports. Each link is a real navigation action in the logic.
- **Design** windows with native controls: rows, columns, grids and free
  layouts, pages, images, terminals and more. Qt previews use your desktop
  style; GTK previews are rendered by GTK itself.
- **Program behavior** with Scratch-like blocks (Blockly) or with your own
  Python, chosen per project. Block projects can show the generated Python;
  Python projects get suggestions, go-to-definition (F12), diagnostics and
  project-wide search.
- **Test and debug** with F5 and F9: a separate supervised process, live output,
  tasks with stdout/stderr, an interactive terminal, breakpoints on blocks
  or lines, and a read-only view of the stack and variables.
- **Export** Python source, or build DEB, RPM, AppImage and Flatpak packages
  that include Python and the chosen toolkit. The editor itself can also be
  built as an AppImage.

| Map | Logic (blocks) | Logic (Python) |
|---|---|---|
| ![Map](docs/images/map.png) | ![Logic](docs/images/logic.png) | ![Python](docs/images/code-dark.png) |

## Quick start (from source)

Requirements: Linux, Python 3.12–3.14 and the system libraries Qt needs for
WebEngine (on Ubuntu: `libegl1 libgl1 libxkbcommon0 libnss3 libdbus-1-3 libasound2t64`).
For GTK applications you also need PyGObject and GTK 4 from your distribution.

```bash
git clone https://github.com/RichardSpinola/makebench.git
cd makebench
python3 -m venv .venv
.venv/bin/python -m pip install -e .
./run-makebench
```

Choose **Open example…** on the start screen to open a copy of an example, then
press **F5** to test it. Examples also live in [`examples/en`](examples/en):

```bash
./run-makebench examples/en/welcome-states/project.makebench.json
```

The interface is in English by default. Brazilian Portuguese is available in
**View › Preferences › Appearance › Interface language** (it applies on the next
start). See the [user guide](docs/user-guide.md) for a tour of each area.

## Safety model

Opening, editing, previewing, saving and building a project **never run its code**.
Your Python and scripts run only when you press F5/F9 or start an exported
application, with your user's permissions. The separate test process keeps the
editor responsive; it is **not a sandbox** for untrusted projects, so review code
from others before testing it. Administrative tasks use Polkit (`pkexec`) and the
system's own authentication dialog; Makebench never asks for passwords. See
[SECURITY.md](SECURITY.md).

## Known limitations

- Linux x86_64 only. Native packages target Ubuntu 24.04 (DEB) and Fedora 44
  (RPM) and need glibc 2.39 or newer; other distributions are untested.
- Code assistance is static (no language server, no type inference).
- Saving writes each file atomically, but not all files as one transaction.
- Flatpak packages are sandboxed: host programs and administrative actions are
  unavailable inside them.
- Visual QA used software rendering and a private compositor; not every GPU and
  compositor has been qualified.

## How it was made

Makebench was written with the help of AI coding assistants, reviewed and tested by
its author. There is **no AI inside the program**: the editor and the applications
it exports never call an AI service. The idea is the opposite — simple programs
built by people, with blocks and a little Python, that anyone can read and change.

## License

- The **editor** is free software under the [GNU GPL, version 3 or later](LICENSE).
- The **runtime** that goes into the applications you export (`core`, `runtime`,
  `gtk_runtime`, `ui`, `terminal`, `portable`, `i18n.py` and the translations),
  plus the templates, examples and official plugins, is under the [MIT license](LICENSE-MIT). So
  **you choose the license of your own applications**. Third-party components (Blockly, PySide6/Qt, pyte,
wcwidth) keep their licenses; see
[`src/makebench/notices/THIRD_PARTY.md`](src/makebench/notices/THIRD_PARTY.md).
