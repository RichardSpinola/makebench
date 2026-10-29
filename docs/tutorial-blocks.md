# Tutorial: your first app with blocks

In about fifteen minutes you will build **My notes**: a window where you type a
title and a text, save the note, see every note in a table and export them to a
CSV file. The finished project is in **File › Open example… › My notes**, if
you want to compare.

You will use the three areas of the editor: **Design** for the window,
the **Data** panel for the saved notes and **Logic** for what the buttons do.

## 1. Create the project

1. Choose **File › New project** (++ctrl+n++).
2. In **Template**, pick **Blank** ("One window to start your own way").
3. In **Program with**, pick **Blocks**.
4. In **Application look**, keep **Qt — desktop controls** (or pick GTK if you
   have GTK 4 installed).
5. Name it `My notes` and confirm.

Makebench opens the **Design** area with one empty window.

## 2. Draw the window

Find each component in the **Components** panel (type in its search box) and
drag it onto the window, from top to bottom:

| Component | What to set in **Properties** |
|---|---|
| **Text** | **Text**: `My notes` |
| **Text field** | **Field hint**: `Note title` |
| **Long text** | **Field hint**: `Write here…` |
| **Button** | **Text**: `Add note` |
| **Button** | **Text**: `Export CSV` |
| **Table** | nothing for now |
| **Text** | **Text**: `Ready.` |

!!! tip "Give them names"
    Under **Advanced**, **Name in code** gives a component a readable name, such
    as `title_input` or `status`. Blocks do not need it, but View Python and
    Python projects become easier to read.

Want the two buttons side by side? Drop a **Container** first, choose **Row**
in its **Layout** section and put both buttons inside it.

## 3. Create a collection for the notes

A *collection* is like a table of a database: it keeps records after the app
closes.

1. Open the **Data** panel (**View › Panels › Data**) and click **+ Collection**.
2. **Name**: `Notes`.
3. Click **+ Field** twice and fill in the fields:
    - `Title`, type **Text**;
    - `Text`, type **Text**.
4. Save. The first text field (`Title`) is the one that names each record.

## 4. Show the notes when the app starts

1. Click an empty part of the window to select it. In **Properties**, click
   **+ On start**. Logic opens with an empty *On start* flow.
2. From the **Records** category, drag **show records of** into the flow.
   Choose the table and the `Notes` collection.

## 5. Save a note

Go back to **Design** (++ctrl+2++), select the **Add note** button and click
**+ On click** in Properties. Then build this flow:

1. **if … then … else …** (Conditions).
2. As the condition, an **… = …** comparison (Operations; pick `=` in its menu)
   between **text of** the title field (Interface) and an empty **"text"** block
   (Text).
3. In *then*: **change text of** the status text to `Write a title first.`
4. In *else*:
    1. **add record to** `Notes`, with **text of** the title field for `Title`
       and **text of** the long text for `Text`;
    2. two **change text of** blocks that set the title field and the long text
       to an empty text;
    3. **show records of** the table and `Notes` again;
    4. **change text of** the status text to `Note saved.`

Click **View Python** in the Logic toolbar to see the code these blocks
produce. It is read-only, and selecting a block highlights its line.

## 6. Export the notes

Select the **Export CSV** button, click **+ On click**, and add:

1. **ask … store in …** (Tasks): pick *file to save*, attach a **"text"** block
   with `Save the notes to`, and type `csv_path` after *store in*.
2. **export table … to CSV file** (Records): pick the table and attach
   **value of …** (Variables and data) with `csv_path`.

If the person cancels the dialog, the flow simply stops.

## 7. Test it

Press ++f5++ (**Run › Test application**). Type a title and a text, click
**Add note**, and the note appears in the table. Close the app and press ++f5++
again: the notes are still there.

While testing, records go to a separate test folder. **Delete test data…** in
the Data panel empties it.

When something goes wrong, open the drawer with ++ctrl+j++: **Go to error**
jumps to the block that failed. ++f9++ starts the debugger, which stops on
breakpoints you set from a block's menu.

## 8. Export it

Choose **Project › Export application…** (++ctrl+shift+e++), pick who it is for
(for example **Anyone on Linux** for an AppImage) and click **Build…**. See
[Exporting](export.md) for every format.

## Next

- Do the same with Python in the [Python tutorial](tutorial-python.md).
- Learn more about [data and charts](data.md).
- See every block in the [block reference](reference/blocks.md).
