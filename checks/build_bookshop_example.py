# SPDX-License-Identifier: MIT
"""Generate the "Bookshop" example: books, clients and sales that update the stock (blocks).

Run from the repository root: PYTHONPATH=src .venv/bin/python checks/build_bookshop_example.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_full_examples import lit, make_flow  # noqa: E402
from makebench.core.assets import AssetStore
from makebench.core.logic import LOGIC_VERSION
from makebench.core.project import ComponentKind as K
from makebench.core.project import LayoutKind, Project
from makebench.core.source import SourceBuffer, SourceText
from makebench.core.storage import save_workspace

ROOT = Path(__file__).resolve().parents[1]

TEXT = {
    "pt": dict(
        name="Livraria",
        subtitle="Cadastre livros e clientes, registre vendas: o estoque e o caixa se atualizam.",
        books="Livros",
        clients="Clientes",
        sales="Vendas",
        f_title="Título",
        f_price="Preço",
        f_stock="Estoque",
        f_name="Nome",
        f_client="Cliente",
        f_book="Livro",
        f_quantity="Quantidade",
        f_total="Total",
        f_delivered="Entregue",
        title_ph="Título do livro",
        name_ph="Nome do cliente",
        add_book="Adicionar livro",
        add_client="Adicionar cliente",
        sell="Registrar venda",
        deliver="Marcar entregue",
        price_label="Preço:",
        stock_label="Estoque:",
        quantity_label="Quantidade:",
        cash="Caixa: ",
        ready="Pronto.",
        need_title="Escreva o título do livro.",
        need_name="Escreva o nome do cliente.",
        need_choice="Escolha um cliente e um livro.",
        no_stock="Estoque insuficiente.",
        need_sale="Selecione uma venda na tabela.",
        book_saved="Livro salvo.",
        client_saved="Cliente salvo.",
        sold="Venda registrada.",
        delivered="Venda marcada como entregue.",
        flow_start="Ao iniciar",
        flow_book="Clique: Adicionar livro",
        flow_client="Clique: Adicionar cliente",
        flow_sell="Clique: Registrar venda",
        flow_deliver="Clique: Marcar entregue",
    ),
    "en": dict(
        name="Bookshop",
        subtitle="Add books and clients, record sales: the stock and the cash update themselves.",
        books="Books",
        clients="Clients",
        sales="Sales",
        f_title="Title",
        f_price="Price",
        f_stock="Stock",
        f_name="Name",
        f_client="Client",
        f_book="Book",
        f_quantity="Quantity",
        f_total="Total",
        f_delivered="Delivered",
        title_ph="Book title",
        name_ph="Client name",
        add_book="Add book",
        add_client="Add client",
        sell="Record sale",
        deliver="Mark delivered",
        price_label="Price:",
        stock_label="Stock:",
        quantity_label="Quantity:",
        cash="Cash: ",
        ready="Ready.",
        need_title="Write the book title.",
        need_name="Write the client name.",
        need_choice="Choose a client and a book.",
        no_stock="Not enough stock.",
        need_sale="Select a sale in the table.",
        book_saved="Book saved.",
        client_saved="Client saved.",
        sold="Sale recorded.",
        delivered="Sale marked as delivered.",
        flow_start="On start",
        flow_book="Click: Add book",
        flow_client="Click: Add client",
        flow_sell="Click: Record sale",
        flow_deliver="Click: Mark delivered",
    ),
}


def build(language, destination):
    t = TEXT[language]
    project = Project.empty(t["name"])
    root = project.root
    root.properties.update(title=t["name"], width=780, height=760, padding=16, spacing=8)

    def add(parent, kind, code=None, **props):
        node = project.add(parent.id, kind)
        node.properties.update(props)
        if code:
            node.properties["code_name"] = code
        return node

    def row(parent):
        node = add(parent, K.CONTAINER)
        node.layout = LayoutKind.HORIZONTAL
        return node

    add(root, K.LABEL, "heading", text=t["name"])
    add(root, K.LABEL, "subtitle", text=t["subtitle"])

    add(root, K.LABEL, "books_heading", text=t["books"])
    line = row(root)
    title = add(line, K.TEXT_INPUT, "title_input", placeholder=t["title_ph"])
    add(line, K.LABEL, text=t["price_label"])
    price = add(line, K.NUMBER, "price_input", decimals=2, maximum=100000, step=1)
    add(line, K.LABEL, text=t["stock_label"])
    stock = add(line, K.NUMBER, "stock_input", maximum=100000)
    add_book = add(line, K.BUTTON, "add_book_button", text=t["add_book"])
    books_table = add(root, K.TABLE, "books_table")

    add(root, K.LABEL, "clients_heading", text=t["clients"])
    line = row(root)
    name = add(line, K.TEXT_INPUT, "name_input", placeholder=t["name_ph"])
    add_client = add(line, K.BUTTON, "add_client_button", text=t["add_client"])

    add(root, K.LABEL, "sales_heading", text=t["sales"])
    line = row(root)
    client_choice = add(line, K.CHOICE, "client_choice", options=[])
    book_choice = add(line, K.CHOICE, "book_choice", options=[])
    add(line, K.LABEL, text=t["quantity_label"])
    quantity = add(line, K.NUMBER, "quantity_input", value=1, minimum=1, maximum=1000)
    sell = add(line, K.BUTTON, "sell_button", text=t["sell"])
    sales_table = add(root, K.TABLE, "sales_table")
    line = row(root)
    deliver = add(line, K.BUTTON, "deliver_button", text=t["deliver"])
    add(line, K.SPACER)
    cash = add(line, K.LABEL, "cash_label", text=t["cash"])
    status = add(root, K.LABEL, "status", text=t["ready"])

    project.metadata["collections"] = [
        {
            "id": "books",
            "name": t["books"],
            "fields": [
                {"id": "title", "name": t["f_title"], "type": "text"},
                {"id": "price", "name": t["f_price"], "type": "number"},
                {"id": "stock", "name": t["f_stock"], "type": "number"},
            ],
        },
        {
            "id": "clients",
            "name": t["clients"],
            "fields": [{"id": "name", "name": t["f_name"], "type": "text"}],
        },
        {
            "id": "sales",
            "name": t["sales"],
            "fields": [
                {"id": "client", "name": t["f_client"], "type": "ref", "target": "clients"},
                {"id": "book", "name": t["f_book"], "type": "ref", "target": "books"},
                {"id": "quantity", "name": t["f_quantity"], "type": "number"},
                {"id": "total", "name": t["f_total"], "type": "number"},
                {"id": "delivered", "name": t["f_delivered"], "type": "bool"},
            ],
        },
    ]
    chosen_book = ("read", book_choice.id, "record")
    book = ("get", "books", chosen_book)
    amount = ("read", quantity.id, "value")
    show_cash = ("set_text", cash.id, ("join", lit(t["cash"]), ("sum", "sales", "total")))
    steps = [
        (
            t["flow_start"],
            {"kind": "start", "component": root.id},
            [
                ("show_records", books_table.id, "books"),
                ("show_records", book_choice.id, "books"),
                ("show_records", client_choice.id, "clients"),
                ("show_records", sales_table.id, "sales"),
                show_cash,
            ],
        ),
        (
            t["flow_book"],
            {"kind": "click", "component": add_book.id},
            [
                (
                    "if",
                    ("bin", "==", ("read", title.id, "text"), lit("")),
                    [("set_text", status.id, lit(t["need_title"]))],
                    [
                        (
                            "data_add",
                            "books",
                            [
                                ("title", ("read", title.id, "text")),
                                ("price", ("read", price.id, "value")),
                                ("stock", ("read", stock.id, "value")),
                            ],
                        ),
                        ("set_text", title.id, lit("")),
                        ("show_records", books_table.id, "books"),
                        ("show_records", book_choice.id, "books"),
                        ("set_text", status.id, lit(t["book_saved"])),
                    ],
                ),
            ],
        ),
        (
            t["flow_client"],
            {"kind": "click", "component": add_client.id},
            [
                (
                    "if",
                    ("bin", "==", ("read", name.id, "text"), lit("")),
                    [("set_text", status.id, lit(t["need_name"]))],
                    [
                        ("data_add", "clients", [("name", ("read", name.id, "text"))]),
                        ("set_text", name.id, lit("")),
                        ("show_records", client_choice.id, "clients"),
                        ("set_text", status.id, lit(t["client_saved"])),
                    ],
                ),
            ],
        ),
        (
            t["flow_sell"],
            {"kind": "click", "component": sell.id},
            [
                (
                    "if",
                    (
                        "bin",
                        "or",
                        ("bin", "==", ("read", client_choice.id, "text"), lit("")),
                        ("bin", "==", ("read", book_choice.id, "text"), lit("")),
                    ),
                    [("set_text", status.id, lit(t["need_choice"]))],
                    [
                        (
                            "if",
                            ("bin", "<", ("record_field", "books", "stock", book), amount),
                            [("set_text", status.id, lit(t["no_stock"]))],
                            [
                                (
                                    "data_add",
                                    "sales",
                                    [
                                        ("client", ("read", client_choice.id, "record")),
                                        ("book", chosen_book),
                                        ("quantity", amount),
                                        (
                                            "total",
                                            (
                                                "bin",
                                                "*",
                                                ("record_field", "books", "price", book),
                                                amount,
                                            ),
                                        ),
                                        ("delivered", lit(False)),
                                    ],
                                ),
                                (
                                    "data_update",
                                    "books",
                                    [
                                        (
                                            "stock",
                                            (
                                                "bin",
                                                "-",
                                                ("record_field", "books", "stock", book),
                                                amount,
                                            ),
                                        )
                                    ],
                                    chosen_book,
                                ),
                                ("show_records", books_table.id, "books"),
                                ("show_records", sales_table.id, "sales"),
                                show_cash,
                                ("set_text", status.id, lit(t["sold"])),
                            ],
                        ),
                    ],
                ),
            ],
        ),
        (
            t["flow_deliver"],
            {"kind": "click", "component": deliver.id},
            [
                (
                    "if",
                    ("bin", "==", ("read", sales_table.id, "selected"), ("list", [])),
                    [("set_text", status.id, lit(t["need_sale"]))],
                    [
                        (
                            "data_update",
                            "sales",
                            [("delivered", lit(True))],
                            ("read", sales_table.id, "record"),
                        ),
                        ("show_records", sales_table.id, "sales"),
                        ("set_text", status.id, lit(t["delivered"])),
                    ],
                ),
            ],
        ),
    ]
    for index, (label, event, body_steps) in enumerate(steps):
        flow = make_flow(label, event, body_steps)
        flow["id"] = f"flow_{index:02d}_{event['kind']}"
        project.workflows.append(flow)
    project.application.update(
        id="org.makebench.bookshop",
        name=project.name,
        version="0.1.0",
        backend="qt",
        language="pt_BR" if language == "pt" else "en",
    )
    project.metadata["logic_version"] = LOGIC_VERSION
    project.metadata["example"] = t["subtitle"]
    project.entry_window = root.id
    source = SourceBuffer()
    source.text = SourceText("")
    destination.mkdir(parents=True, exist_ok=True)
    save_workspace(project, source, AssetStore(), destination / "project.makebench.json")


if __name__ == "__main__":
    for language, base in (("pt", ROOT / "examples"), ("en", ROOT / "examples" / "en")):
        build(language, base / "bookshop")
        print("wrote", base / "bookshop", file=sys.stderr)
