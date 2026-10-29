# Compatibility promises

What stays stable, what may change, and how Makebench tells you.

## Project files

- A project file records a **format version**. Makebench writes the **lowest** version
  that can hold the features the project uses, so a plain project stays readable by
  older Makebench releases.
- Every older format is read by newer releases. Formats 1 to 3 are saved as format 4.
- Saving a project in a newer format than the file had keeps a backup next to it
  (`name.makebench.json.bak-v<old>`), so you can go back.
- A file from a **newer** Makebench is never opened half-way: the error asks you to use
  a compatible version.
- `tests/test_compatibility_policy.py` checks these promises, including that the shipped
  examples open and save without changes.

## Plugins

- A plugin declares the plugin API it was written for (`"api": N` in `plugin.json`).
- A release lists the APIs it understands. A plugin that names any other API is shown
  as incompatible and its code is **never imported**.
- Older APIs stay supported for at least one minor release after a new one appears;
  the changelog says when one is retired.
- Plugins run with your user's permissions and are off until you turn them on.

## Themes

A theme (`.mbtheme`) is data only: colors and sizes. It cannot run code.

## Exported apps

An exported app carries the small MIT-licensed runtime it needs and does not depend on
the editor, so updating Makebench never changes an app you already exported.
