# Changelog

## 0.8.0 (unreleased)

- **Version history:** every save can become a Git version; browse by day, name,
  restore without losing anything, and send to GitHub/GitLab/Codeberg with the
  login your computer already has.
- **Reusable pieces:** save any component as a piece, insert copies, share as files.
- **Plugins (API v1):** folder-based, off by default, see `docs/plugins.md`.
- **Better Python help:** Jedi-powered suggestions, signatures, definitions and rename;
  `ctx` is fully described for completion.
- **Window look:** per-window theme, accent and background (Qt and GTK) and
  `ctx.set_theme` / `ctx.set_background`.
- **Themes and downloads (in progress):** `.mbtheme` color theme files with strict
  validation, and downloading a project from a Git address.
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
