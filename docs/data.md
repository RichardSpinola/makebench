# Data and charts

Apps often need to remember things: notes, clients, sales. In Makebench you
declare **collections** and the app keeps their **records** in a local SQLite
database. No server, no SQL to write.

## Collections and fields

Open the **Data** panel (**View › Panels › Data**) and click **+ Collection**.
A collection has a name and a list of fields; click **+ Field** for each one.

| Type | Holds | Example |
|---|---|---|
| **Text** | any text | a title, a name |
| **Number** | whole or decimal numbers | a price, a stock |
| **Date** | a date as `YYYY-MM-DD` | `2026-10-29` |
| **Yes/No** | true or false | delivered |
| **Reference** | a link to a record of another collection (**Points to**) | the client of a sale |

The **first text field** names each record. A table shows that name in a
reference column, and a choice list shows it as the option.

Makebench protects what is in use: a collection or field that blocks still use
cannot be removed (change the blocks first), and a record that other records
point to cannot be deleted.

## Working with records

In blocks, the **Records** category has everything; in Python, `ctx.data` does
the same. Collections and fields are named the way you named them (their
internal ids also work).

| Task | Block | Python |
|---|---|---|
| Add a record | **add record to** | `ctx.data.add("Books", Title="Dune", Price=40)` |
| Change fields | **change record in** | `ctx.data.update("Books", book_id, Price=35)` |
| Delete | **delete record from** | `ctx.data.delete("Books", book_id)` |
| One record | **record of** | `ctx.data.get("Books", book_id)` |
| Search | **records of** | `ctx.data.find("Books", "Price", "<", 50, order="Title")` |
| Count | **count records of** | `ctx.data.count("Books", "Stock", ">", 0)` |
| Sum a number field | **total in** | `ctx.data.sum("Sales", "Total")` |
| Show in a table or choice list | **show records of** | `ctx.show_records("books_table", "Books")` |
| The record the person selected | **selected record of** | `ctx.read("books_table", "record")` |
| The id just added | **id of the last added record** | the value returned by `ctx.data.add` |

Searches compare with `=`, `!=`, `<`, `>`, `<=`, `>=` or `contains`. A record
comes back as a dictionary keyed by field name, plus its `id`. Loop over a
list of records with **for each** (Loops) or a Python `for`.

Every block and method is in the [block reference](reference/blocks.md) and
the [Python API](reference/ctx.md).

## An example: recording a sale

The **Bookshop** example (**File › Open example…**) has *Books* (Title, Price,
Stock), *Clients* (Name) and *Sales* (Client and Book as references, Quantity,
Total, Delivered). Its *Record sale* button does this, written here in Python:

```python
def on_sell_click(ctx):
    client = ctx.read("client_choice", "record")
    book = ctx.read("book_choice", "record")
    if client is None or book is None:
        ctx.set_text("status", "Choose a client and a book.")
        return
    amount = ctx.read("quantity", "value")
    stock = ctx.data.get("Books", book)["Stock"]
    if stock < amount:
        ctx.set_text("status", "Not enough stock.")
        return
    price = ctx.data.get("Books", book)["Price"]
    ctx.data.add("Sales", Client=client, Book=book, Quantity=amount,
                 Total=price * amount, Delivered=False)
    ctx.data.update("Books", book, Stock=stock - amount)
    ctx.show_records("sales_table", "Sales")
    ctx.set_text("cash", f"Cash: {ctx.data.sum('Sales', 'Total')}")
```

The example itself is made with blocks; open it and click **View Python** to
see the code Makebench generates.

## Charts

The **Chart** component draws bars, a line or a pie from two lists: labels and
numbers. Fill it with **set chart data** or `ctx.set_chart`:

```python
def on_report_start(ctx):
    books = ctx.data.find("Books", order="Title")
    ctx.set_chart(
        "stock_chart",
        [book["Title"] for book in books],
        [book["Stock"] for book in books],
    )
```

The **Complete workshop** example has a Data page with a chart.

## Files and CSV

| Task | Block | Python |
|---|---|---|
| Export records | **export records of** | `ctx.export_records_csv(path, "Books")` |
| Export what a table shows | **export table** | `ctx.export_table_csv(path, "books_table")` |
| Read a CSV file | **rows of CSV file** | `ctx.read_csv(path)` |
| Read a text file | **text of file** | `ctx.read_text(path)` |
| Write a text file | **write text** | `ctx.write_text(path, text)` |
| Ask for a file | **ask …** (file, folder or file to save) | `ctx.ask("save_file", "Save to")` |

In exported records, a reference shows the name of the record it points to.
Files are not sandboxed (except inside a Flatpak): the app reads and writes
whatever the person running it can.

## Where the data lives

| When | File |
|---|---|
| The exported app | `$XDG_DATA_HOME/<app id>/data.sqlite`, usually `~/.local/share/<app id>/data.sqlite` |
| A Flatpak app | the same path inside `~/.var/app/<app id>/data/` |
| Testing in the editor (++f5++) | a separate test database under `~/.local/share/makebench/test-data/` |

The app id is set in **Project › Application settings…**. **Delete test data…**
in the Data panel empties the test database; the data of exported apps is never
touched by the editor. The database file is only created when the app first
uses a collection.
