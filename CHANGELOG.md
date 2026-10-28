# Changelog

## 0.9.0 — 2026-10-28

- **Design at the real size:** the designed window has the width and height it
  opens with, a desktop title bar and a shadow, and resizes from its edges.
- **Web view windows:** a window can show one HTML page instead of components,
  with images as project assets. The official *Web view* plugin adds a template
  and a page editor with live preview.
- **Plugin API v2:** project templates, a command context with dialogs and
  images, and refusals with a message. Official plugins ship turned off.
- **Theme pack:** Catppuccin, Dracula, Gruvbox, Nord and Solarized, dark and
  light, checked for legible contrast.
- **Who is it for?:** publishing starts by asking who will use the application
  (any Linux, Ubuntu/Debian, Fedora/openSUSE, isolated, programmers) and picks
  the package, showing each file extension.
- **Logic in one bar:** event, block tools and Blocks/Nodes share one row;
  Versions, Duplicate and Remove wait in a menu.
- **Calmer screens:** every menu entry has a symbol, the start page is quieter,
  preference sections have symbols, dark check boxes are visible and map arrows
  go around the cards.
- **Fixed:** map thumbnails follow desktop palette changes, floating Design
  panels hide in other areas, and tests no longer touch your real settings.
- The README explains that AI helped build Makebench but is not inside it.

## 0.8.0 — 2026-10-26

- **Version history:** every save can become a Git version; browse by day, name,
  restore without losing anything, and send to GitHub/GitLab/Codeberg with the
  login your computer already has.
- **Reusable pieces:** save any component as a piece, insert copies, share as files.
- **Plugins (API v1):** folder-based, off by default, see `docs/plugins.md`.
- **Better Python help:** Jedi-powered suggestions, signatures, definitions and rename;
  `ctx` is fully described for completion.
- **Window look:** per-window theme, accent and background (Qt and GTK) and
  `ctx.set_theme` / `ctx.set_background`.
- **New interface:** Makebench now draws with its own light and dark colors
  (the desktop's colors stay one setting away), with an area bar on the left, a
  strip naming the current area, detachable panels with *Restore layout*, a richer
  status bar with a light/dark switch, and the project's icon in the corner.
- **Start window and page:** larger start window with recent projects, templates,
  tips and recovery; the empty workspace shows the emblem (gray in dark mode) and
  can reopen the start window. A retro emblem is hidden in Preferences.
- **Themes:** `.mbtheme` color theme files with strict validation, picked, created
  and imported in *Plugins › Themes…*.
- **Download from Git:** clone a project from any Git address and open it.
- **Clearer screens:** Properties as a table, grouped Components, document tabs and
  tinted headers in History, Publish and Preferences.
- **Fixed in running apps:** tabbed pages no longer draw over the current tab when
  the window starts, and an output's starting text is a hint instead of text the
  program's output is appended to.
- **New project dialog:** advanced options only on request.
- **Complete examples:** *Complete workshop* with nodes and with blocks, in English
  and Portuguese, with an in-app guide window.

## 0.7.0 — first public release

Makebench is a visual editor for native Linux applications (Qt or GTK 4). This is
an alpha: it is usable and tested, but project formats and APIs may still change.

### The editor
- Four areas: **Map** (windows and states), **Design** (native controls),
  **Logic** (Blockly blocks or a node graph) and **Code** (your own Python).
- Test with **F5**, debug with **F9** (breakpoints on blocks, nodes and Python
  lines; read-only stack and variables), interactive terminal and supervised tasks.
- Export Python source, DEB, RPM, AppImage and Flatpak; the editor itself can be
  built as an AppImage.

### New in this release
- **English by default**, with a Brazilian Portuguese translation you can choose in
  Preferences. New projects, templates and exported applications follow the
  chosen language. Examples come in English and Portuguese.
- **Getting started:** a short guide on first launch (**F1**), a keyboard shortcut
  list in the Help menu, **Open example…** on the start screen, and empty states
  that tell you what to do next.
- **Undo with names:** Undo and Redo say what they will change ("Undo: Move card").
- **Search in project** (**Ctrl+Shift+F**) across every Python file.
- **Clearer errors:** plain explanations for common problems (no permission, disk
  full, file moved) with technical details behind "Show details".
- **Accessibility:** every icon-only button has a name and tooltip.
- **Safer saving:** the editor and scripts share one save path, and a failed save
  says which files were written.
- Debug moved from F6 to **F9** (F6 cycles the focus regions).

### License
The editor is under the GPL-3.0-or-later. The runtime that goes into exported
applications, the templates and the examples are under the MIT license, so you
choose the license of your own applications.

### Known limitations
Linux x86_64 only; native packages target Ubuntu 24.04 and Fedora 44; code
assistance is static; saving is atomic per file, not for all files at once.
See the README for details.
