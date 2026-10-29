# SPDX-License-Identifier: GPL-3.0-or-later
"""Short task recipes for "Insert example"; ids in quotes are placeholders to replace."""

from makebench.i18n import tr


def examples():
    """(title, code) pairs; the code is a function body with no leading indentation."""
    return [
        (
            tr("Read a text field"),
            'name = ctx.read("name_field", "text")\nctx.set_text("greeting", f"Hello, {name}!")\n',
        ),
        (tr("Show a message"), 'ctx.message("Saved.")\n'),
        (
            tr("Ask before continuing"),
            'if ctx.confirm("Delete the selected item?"):\n    ctx.message("Deleted.")\n',
        ),
        (
            tr("Ask for a text"),
            'answer = ctx.ask("text", "What is your name?")\nctx.log(answer)\n',
        ),
        (
            tr("Fill a table"),
            'rows = [["Ana", 31], ["Bruno", 27]]\nctx.set_rows("people_table", rows)\n',
        ),
        (
            tr("Add a record and show the collection"),
            'ctx.data.add("books", title="Dom Casmurro", year=1899)\n'
            'ctx.show_records("books_table", "books")\n',
        ),
        (
            tr("Find records"),
            'recent = ctx.data.find("books", "year", ">", 2000, order="title")\n'
            "for book in recent:\n"
            '    ctx.log(book["title"])\n',
        ),
        (
            tr("Read the selected record"),
            'record_id = ctx.read("books_table", "record")\n'
            "if record_id is not None:\n"
            '    book = ctx.data.get("books", record_id)\n'
            '    ctx.set_text("details", book["title"])\n',
        ),
        (
            tr("Read and write a file"),
            'path = ctx.ask("file", "Choose a text file")\n'
            "text = ctx.read_text(path)\n"
            'ctx.write_text(path + ".bak", text)\n',
        ),
        (
            tr("Export a CSV file"),
            'path = ctx.ask("save_file", "Save as")\n'
            'ctx.export_csv(path, ["Name", "Age"], [["Ana", 31], ["Bruno", 27]])\n',
        ),
        (
            tr("Run a program"),
            'code = ctx.run("ls", ["-l"], check=False)\nctx.log(f"Finished with code {code}")\n',
        ),
        (
            tr("Show progress"),
            "for step in range(1, 11):\n"
            '    ctx.set_value("progress", step * 10)\n'
            '    ctx.log(f"Step {step} of 10")\n',
        ),
        (
            tr("Handle an error"),
            "try:\n"
            '    number = int(ctx.read("amount", "text"))\n'
            "except ValueError:\n"
            '    ctx.message("Type a whole number.")\n'
            "else:\n"
            '    ctx.set_text("result", number * 2)\n',
        ),
    ]
