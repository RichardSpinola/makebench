# Tutorial: the same app in Python

This tutorial builds the **My notes** app of the
[blocks tutorial](tutorial-blocks.md), but writes its logic in Python. The
window and the data are made the same way; only step 4 onwards changes.

## 1. Create a Python project

**File › New project** (++ctrl+n++), template **Blank**, **Program with:
Python**, name `My notes`.

Your code goes into the project's `.actions.py` file, next to the
`.makebench.json` file. Makebench reads it to help you (suggestions, errors as
you type, **F12** to jump to a definition) but never imports or runs it until
you press ++f5++.

## 2. Draw the window and name the components

Add the same components as in the blocks tutorial. This time the names matter,
because your code refers to them. Select each one and, under **Advanced**, set
**Name in code**:

| Component | Text or field hint | Name in code |
|---|---|---|
| Text field | `Note title` | `title_input` |
| Long text | `Write here…` | `text_input` |
| Button | `Add note` | `add_button` |
| Button | `Export CSV` | `export_button` |
| Table | | `notes_table` |
| Text | `Ready.` | `status` |

## 3. Create the collection

In the **Data** panel, **+ Collection** named `Notes` with two **Text** fields,
`Title` and `Text`. Your code uses these names: `ctx.data` accepts collection
and field names (or their internal ids).

## 4. Connect the events

1. Select the window and click **+ On start** in Properties. Makebench adds an
   empty function such as `def on_my_notes_start(ctx):` to the actions file and
   opens it.
2. Select **Add note** and click **+ On click**: `def on_add_button_click(ctx):`.
3. Select **Export CSV** and click **+ On click**: `def on_export_button_click(ctx):`.

The **Events** list in Logic shows which function each event calls. If you
rename a function by hand, Problems tells you that the event lost it.

## 5. Write the code

Fill in the three functions:

```python
def on_my_notes_start(ctx):
    ctx.show_records("notes_table", "Notes")


def on_add_button_click(ctx):
    title = ctx.read("title_input", "text")
    if title == "":
        ctx.set_text("status", "Write a title first.")
        return
    ctx.data.add("Notes", Title=title, Text=ctx.read("text_input", "text"))
    ctx.set_text("title_input", "")
    ctx.set_text("text_input", "")
    ctx.show_records("notes_table", "Notes")
    ctx.set_text("status", "Note saved.")


def on_export_button_click(ctx):
    path = ctx.ask("save_file", "Save the notes to")
    ctx.export_table_csv(path, "notes_table")
```

What each call does:

- `ctx.read(component, "text")` gives what the person typed.
- `ctx.set_text(component, value)` changes a text in the running window.
- `ctx.data.add(collection, **fields)` saves a record and returns its id.
- `ctx.show_records(component, collection)` fills the table with the records.
- `ctx.ask("save_file", prompt)` opens a save dialog; **Cancel** ends the
  function there, so `path` is always a real path.
- `ctx.export_table_csv(path, component)` writes what the table shows.

The **What can I use** panel at the right of the code lists every `ctx`
method, your components and your collections; double-click one to insert it.
**Insert example** adds short recipes at the cursor. The full list is in the
[Python API reference](reference/ctx.md).

## 6. Test and debug

Press ++f5++ to test. Errors in your code are underlined while you type and
listed in **Problems**; errors while the app runs show in the drawer
(++ctrl+j++) with **Go to error**.

To stop on a line, click the margin of the code to set a breakpoint and press
++f9++. While paused, ++f10++ steps over, ++f11++ steps into a function,
++shift+f11++ steps out and ++f8++ continues.

## Going further

- Split your code into modules: they live in the project's `makebench_user/`
  folder, and you import them with `from makebench_user.checks import validate`.
- A blocks project can become a Python one with **Project › Convert to
  Python…**; each flow becomes a function that does the same. The previous
  files are kept with a `.bak-blocks` suffix.
- The **Python modules** example shows a project with several files.
