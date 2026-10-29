---
hide:
  - toc
---

# Makebench

<div class="mb-hero" markdown>

![](assets/logo.svg)

A visual workshop for small Linux desktop apps. Design the windows, program
them with **blocks** or **Python**, test them in the editor and export a
package that runs without Makebench.

[Install](install.md){ .md-button .md-button--primary }
[Build your first app](tutorial-blocks.md){ .md-button }

</div>

![The Design area](images/design.png)

## Start here

<div class="grid cards" markdown>

-   :material-download:{ .lg .middle } **Install**

    ---

    One AppImage, no account and no internet needed.

    [:octicons-arrow-right-24: Install](install.md)

-   :material-puzzle:{ .lg .middle } **Tutorial: blocks**

    ---

    Build a notes app with a saved list and CSV export, without typing code.

    [:octicons-arrow-right-24: Start](tutorial-blocks.md)

-   :material-language-python:{ .lg .middle } **Tutorial: Python**

    ---

    The same app, with the logic written in Python and the help of the editor.

    [:octicons-arrow-right-24: Start](tutorial-python.md)

-   :material-folder-open:{ .lg .middle } **Examples**

    ---

    Ready-made projects to open, test and change.

    [:octicons-arrow-right-24: Examples](examples.md)

</div>

## Guides

<div class="grid cards" markdown>

-   :material-book-open-variant:{ .lg .middle } **[User guide](user-guide.md)**

    ---

    The workspace, one area at a time: Map, Design, Logic, testing and
    debugging.

-   :material-database:{ .lg .middle } **[Data and charts](data.md)**

    ---

    Collections saved in SQLite, references, CSV and charts.

-   :material-palette:{ .lg .middle } **[Appearance and themes](appearance.md)**

    ---

    Editor themes, window looks, component styles and reusable pieces.

-   :material-package-variant-closed:{ .lg .middle } **[Exporting](export.md)**

    ---

    AppImage, DEB, RPM, Flatpak or Python source, in Qt or GTK.

</div>

## Reference

<div class="grid cards" markdown>

-   :material-widgets:{ .lg .middle } **[Components](reference/components.md)**

    ---

    Every component, its properties and its events.

-   :material-view-grid-plus:{ .lg .middle } **[Blocks](reference/blocks.md)**

    ---

    Every block, what it does and the Python it generates.

-   :material-code-braces:{ .lg .middle } **[Python API](reference/ctx.md)**

    ---

    The `ctx` object your functions receive.

-   :material-keyboard:{ .lg .middle } **[Keyboard shortcuts](shortcuts.md)**

    ---

    Editor and code editor shortcuts.

</div>

## Principles

- **Nothing runs by surprise.** Opening, editing, previewing, saving and
  building never run project code; only testing (++f5++) and debugging (++f9++)
  do.
- **Offline.** No account, no server and no AI at run time.
- **Your app is yours.** The editor is GPL-3.0-or-later; the small runtime that
  ships inside exported apps is MIT, so you choose your app's license.

Makebench also has [plugins](plugins.md), a [compatibility promise](compatibility.md)
and notes on [building](building.md) and its [architecture](architecture.md)
for contributors.
