# Makebench user guide

[Leia em português](user-guide.pt-BR.md)

This guide walks through the four areas of the workbench in the order an
application is usually built, then covers testing, debugging and exporting.
Press **F1** in the editor to open the short getting-started guide, and
**Help › Keyboard shortcuts** for the full list of shortcuts.

## Start screen

- **New project…** creates a project from a template, using Qt or GTK 4.
  New projects follow the interface language: their sample texts and
  function names are in English or Portuguese.
- **Open project…** opens an existing `.makebench.json` file.
- **Open example…** copies one of the bundled examples into your projects
  folder and opens the copy. The original examples are never changed.
- **Download from Git…** clones a project from any Git address into your projects
  folder and opens it. Nothing in it runs until you press **F5**.

Closing the start window leaves a **Show the start window** button on the empty
workspace.

## The workspace

The bar on the left switches between the areas; the strip under the toolbar
names the current area and project. Components, Layers and Properties are panels
you can detach, dock elsewhere or close; **View › Panels › Restore layout** puts
them back. The status bar shows whether the project is saved, its problems, the
toolkit, the zoom and a light/dark switch.

Makebench draws with its own colors by default. **Preferences › Appearance ›
Look** switches to the desktop's own colors, and **Plugins › Themes…** picks,
creates or imports `.mbtheme` color themes.

Opening a project never runs it. A project is a `.makebench.json` file with a
sibling `.actions.py` file for your own Python, an optional `makebench_user/`
package of modules and an `assets/` folder for images.

## 1 · Map

The Map shows every window and state of the application as cards, with lines
for the transitions between them.

- Create windows and states from the toolbar or the context menu.
- Drag from a card's port to another card to add a transition. The link is a
  real "show window" or "change state" action inside the logic, not a drawing.
- Select a line to see and change which event triggers it.
- Card thumbnails are rendered from the design without running anything.

![Map](images/map.png)

## 2 · Design

Design is where you build each window with native controls.

- Drag components from **Insert** onto the canvas or onto the component tree.
- Arrange them in rows, columns, grids, pages or free positioning. The
  selection can be moved, resized, duplicated and aligned; with several
  components selected, **Properties** shows what they have in common.
- Qt previews use your desktop style. GTK previews are drawn by GTK itself in a
  private process, so what you see is what GTK will render.
- Images are copied into the project's `assets/` folder when you add them.

![Design](images/design.png)

## 3 · Logic

Logic says what happens when a window starts or a button is clicked. Each
behavior can be written with **blocks** or with **nodes**.

- **Blocks** (Blockly) work like Scratch: snap statements, values and conditions
  together. Free text fields are always treated as text, never as Python.
- **Nodes** are a graph with execution and value ports, wires, loops and
  conditions. Node positions do not change what the graph does.
- You can switch a behavior between blocks and nodes; Makebench keeps a
  recoverable copy of the previous version.
- The generated Python is always shown next to the editor. Selecting a block
  highlights its line.

Available actions include showing windows and pages, reading and changing
components, messages and questions, logging, calling your own Python functions,
and running programs or Bash scripts as supervised tasks. A task can ask for
administrator rights; Makebench then uses Polkit and the system's own
authentication dialog. It never asks for or stores passwords.

![Logic](images/logic.png)

## 4 · Code

Code holds your own Python: the project's `.actions.py` file and any modules in
`makebench_user/`. A function is called from blocks as `function(ctx, value)`,
where `ctx` gives access to the application (read and change components, show
pages, log, ask questions, run tasks).

- Suggestions, **F12** to go to a definition, and diagnostics as you type.
  Analysis is static: your code is parsed, never imported or run.
- **Ctrl+Shift+F** searches every Python file of the project, using what is
  open in the editor rather than what is on disk.
- **Ctrl+Z** in a code tab undoes inside that file; elsewhere it undoes the
  last change to the project. The Edit menu shows what will be undone.

![Code](images/code-dark.png)

## Testing and debugging

- **F5** starts the application in a separate, supervised process. **Shift+F5**
  stops it, together with the tasks it started.
- The drawer at the bottom (**Ctrl+J**) shows output, problems, tasks with their
  stdout and stderr, an interactive terminal, and search results.
- When something fails, **Go to error** opens the block, node or line that caused it.
- **F9** starts debugging. Set breakpoints on blocks, nodes or Python lines
  (click the code margin or use a block's menu). While paused you can see the
  stack and a read-only copy of the variables, then continue, step over, step
  into or step out.

The test process keeps the editor responsive, but it is not a sandbox: the
project runs with your user's permissions. Review projects from others before
testing them.

## Exporting

**Project › Export application…** (**Ctrl+Shift+E**) opens the Export window.

- **Python source** produces a ZIP you can run with Python and the toolkit
  installed.
- **DEB**, **RPM** and **AppImage** include Python and the chosen toolkit, so
  the result runs without installing anything else. **Flatpak** uses the GNOME
  runtime for GTK and the KDE runtime for Qt, and keeps the Flatpak sandbox.
- **Build with** chooses between tools that Makebench prepares in rootless
  Podman containers (cached under `~/.cache/makebench/builders`), the tools
  installed on your system, or the automatic choice. Preparing tools is always
  an explicit step with visible output and a Cancel button.
- **Export only the recipe** produces the build files as a ZIP, without
  building a package.
- **Makebench editor (AppImage)** in the **Export** field builds the editor
  itself as an AppImage, with the examples included.

Building never runs your project. Edit the application's name, identifier,
version, icon and language with **Application…**.

## Version history, cloud and pieces

- **Version history** (Project › Version history): turn it on once and every save
  becomes a version kept with Git in the project folder. Open the window to see
  versions by day, name one, or restore it. Restoring never deletes anything: the
  current state is saved first and the old files come back as a new version.
- **In the cloud:** in the same window connect any Git address (GitHub, GitLab,
  Codeberg…) or create a private GitHub repository when `gh` is signed in.
  **Send** and **Fetch updates** only run when you click. Makebench never asks for
  or stores a password: it uses the login your computer already has (`gh`, SSH or
  the credential helper).
- **Reusable pieces:** right-click a component › *Save as reusable piece*. Your
  pieces appear under *My pieces* in Insert and can be inserted as independent
  copies, renamed, exported and imported.
- **Plugins:** see [plugins.md](plugins.md). They are off until you turn each one on.
- **Window look:** select a window and choose its theme (System, Light, Dark),
  accent colour and background colour. From the logic use `ctx.set_theme(...)` and
  `ctx.set_background(...)`.
- **Complete examples:** *Complete workshop — Nodes* and *— Blocks* use every
  component kind, several windows with different looks, a state, a task, a terminal,
  an own module and a breakpoint. Open the *Guide* window inside them for a short tour.

## Preferences

**View › Preferences…** (**Ctrl+,**) holds the editor settings: interface
language, theme, text size, code font, the folder for new projects and more.
The interface language applies the next time Makebench starts. The **About**
page has a button that opens this guide.

## Files and saving

- **Ctrl+S** saves the project, your Python files and images. Each file is
  written atomically, but the set of files is not saved as one transaction; if
  saving fails halfway, Makebench tells you which files were written.
- When the project format is upgraded, the previous file is kept as
  `.bak-vN` next to it.
- If your Python changed outside Makebench while it was open, Makebench offers
  **Reload file** or **Keep my version** instead of overwriting it silently.
