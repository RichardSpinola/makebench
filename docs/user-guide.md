# Makebench user guide

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
- The list on the left shows each window's events and, under each event, the
  block functions it calls. Double-click one to open it in Logic.

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

- Beside text, buttons and images there are a **number** and a **slider**
  (minimum, maximum, step), a **long text** box, a **choice** list (one option per
  line), a **date** (`YYYY-MM-DD`) and a **table** with the columns you name.
- A window can have **menus** (one title per line, items indented, a shortcut after
  `|`), a **frame** (normal, without buttons, without frame), **full screen** (F11
  toggles it with Qt), **centered** and **always on top**. GTK 4 on Wayland ignores the last two; the export check warns.
- The window look can add a **background image**, which covers the window behind
  the controls (it is copied into `assets/`).
- Each component has a **Style** section: text color, fill color, font size, bold,
  italic and rounded corners. **Edit → Copy style** and **Paste style**
  (Ctrl+Alt+C / Ctrl+Alt+V) copy it to the selected components in one undo step.
- In Logic, **Change window theme** and **Change window background** switch the
  theme, accent or background color while the app runs.

![Design](images/design.png)

## 3 · Logic

Logic says what happens when a window starts or a button is clicked. Each
project is programmed either with **blocks** or with **Python**; you choose when
you create it, and Logic opens the right editor. The sidebar lists the project's
**Events**, **Functions** and **Modules**.

- **Blocks** (Blockly) work like Scratch: snap statements, values and conditions
  together. Free text fields are always treated as text, never as Python.
- **View Python** shows the code generated from the blocks, read-only.
  Selecting a block highlights its line.

Available actions include showing windows and pages, reading and changing
components, messages and questions, logging, calling functions, and running
programs or Bash scripts as supervised tasks. A task can ask for
administrator rights; Makebench then uses Polkit and the system's own
authentication dialog. It never asks for or stores passwords.

Besides *start* and *click*, an event can fire when a control **changes**, when a
window is about to **close**, every few seconds (**timer**, set on the window) or
when a **menu item** is chosen. A change made by your own blocks never fires
*change*; only the person does. The close flow runs first and the window closes
when it ends.

**Functions** group blocks you use in more than one place. Choose **Your
functions › New function…** in the palette (or the ⋯ menu), give it a Python
name and, if you want, inputs separated by commas. Inside the function the
inputs are local variables ("this flow"), and **return** sends a value back.
Use **call** as a statement or **result of** as a value. A function that is
still called cannot be removed, and the number of its inputs only changes after
you remove its calls.

**Modules** only organize: choose **⋯ › Move to module…** and type a name to
group the open event or function with others in the sidebar. Leave the name
empty to take it out. Right-click a block to add a comment or collapse it.

![Logic](images/logic.png)

### Python projects

A Python project keeps its code in the project's `.actions.py` file and any
modules in `makebench_user/`. Each event is bound to a function by name:
double-click a button (or the window) in Design and Makebench adds
`def on_save_click(ctx):` to the actions file and opens it. The **Events** list
shows every binding; `ctx` gives access to the application (read and change
components, show pages, log, ask questions, run tasks). If the function is
missing, Problems says so.

**Project › Convert to Python…** turns a blocks project into a Python one: each
event's blocks become a function with the same behavior. The previous project
and actions file are kept next to it with a `.bak-blocks` suffix.

- Suggestions, **F12** to go to a definition, and diagnostics as you type.
  Analysis is static: your code is parsed, never imported or run.
- Every problem is underlined, red for errors and yellow for warnings, and
  listed in **Problems**: all syntax errors with a short explanation of how to
  fix them, names that are not defined, `ctx` methods that do not exist and
  component ids that are not in the project, with a “Did you mean…?” hint.
  Hover the underline to read it; click it in Problems to jump to the line.
- **What can I use** (right of the code) lists the `ctx` and `ctx.data`
  methods with their documentation, the project's components and its
  collections and fields. Type to filter; double-click to insert at the cursor.
- **Insert example** (in the same panel and in the code's right-click menu)
  adds a short recipe — read a field, show a message, fill a table, find
  records, export CSV, run a program… — indented to the cursor. Ids in quotes
  are placeholders: replace them with your own.
- **Open in external editor** (next to the module buttons) saves the project
  and opens the current file in the command set in Preferences (for example
  `code`) or the default app for `.py` files. When you save there, Makebench
  reloads the file unless it has unsaved edits of its own; then it asks.
- **Ctrl+Shift+F** searches every Python file of the project, using what is
  open in the editor rather than what is on disk.
- **Ctrl+Z** in a code file undoes inside that file; elsewhere it undoes the
  last change to the project. The Edit menu shows what will be undone.

![Python](images/code-dark.png)

## Data and files

Open **Data** in the sidebar to create *collections*, which are like tables:
a name and fields of type text, number, date, yes/no or *reference* (a link to a
record of another collection). A reference shows the first text field of the
record it points to. A field or collection used by blocks cannot be removed.

Blocks in the **Records** category add, change and delete records, search and
count them, sum a number field and loop over a list with *for each*. *Show
records* fills a table or choice list; *selected record* gives back its id.
The **Chart** component (bars, line or pie) takes labels and values from two
lists. Python projects use `ctx.data`, `ctx.show_records` and `ctx.set_chart`.

Records live in a SQLite file in the application's data folder
(`$XDG_DATA_HOME/<app id>/`); while testing in the editor they go to a separate
test folder, which **Delete test data…** empties. Other blocks read and write text
files, read CSV and export a table or records to CSV; *Ask* can also choose a
file to save. Files are not sandboxed: the app reads and writes whatever the
person running it can.

The *Complete workshop* example has a Data page with authors, books, a table, a
chart and CSV export.

## Testing and debugging

- **F5** starts the application in a separate, supervised process. **Shift+F5**
  stops it, together with the tasks it started.
- The drawer at the bottom (**Ctrl+J**) shows output, problems, tasks with their
  stdout and stderr, an interactive terminal, and search results.
- When something fails, **Go to error** opens the block or line that caused it.
- **F9** starts debugging. Set breakpoints on blocks or Python lines
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

### Qt, GTK or a light HTML app

- **Qt** looks the same on every desktop and its packages carry their own Qt
  (PySide6 Essentials). On the Oficina example it opens in about 0.6 s and uses
  about 125 MB with its worker.
- **GTK 4** follows the GNOME look and uses the system's GTK, so packages carry
  less; on the same example it took about 2 s and 185 MB.
- **Light HTML app** (a template under **New project…**) is a GTK window that
  shows one HTML page with the system's WebKitGTK, so nothing like a browser
  goes into the package. Edit the page with the official **Web view** plugin
  (**Plugins › Edit Web view page…**).
- A **Web view** window on **Qt** adds Qt WebEngine, which makes the package
  much larger; **Verify** warns about it. Use GTK for HTML pages when size
  matters.

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
- **Basic examples:** the welcome wizard, task center and terminal examples each
  come in a blocks version and a Python version made by *Convert to Python*.
- **Complete examples:** *Complete workshop* uses every
  component kind, several windows with different looks, a state, a task, a terminal,
  block functions, block modules and a breakpoint. Open the *Guide* window inside them for a short tour.

## Preferences

**View › Preferences…** (**Ctrl+,**) holds the editor settings: interface
language, theme, text size, code font, the folder for new projects and more.
**Clean up Python on save** (off by default) removes trailing spaces, turns
indentation tabs into four spaces, keeps at most two blank lines in a row and
ends each file with a newline; text inside multi-line strings is left alone.
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
