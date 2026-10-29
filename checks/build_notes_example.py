# SPDX-License-Identifier: MIT
"""Generate the "My notes" example: a small app with a saved list of notes (blocks).

Run from the repository root: PYTHONPATH=src .venv/bin/python checks/build_notes_example.py
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
        name="Minhas notas",
        collection="Notas",
        subtitle="Escreva uma nota e ela fica salva no app, sem programar o banco de dados.",
        note_title="Título",
        note_text="Texto",
        title_ph="Título da nota",
        text_ph="Escreva aqui…",
        add="Adicionar nota",
        export="Exportar CSV",
        csv_prompt="Salvar as notas em",
        ready="Pronto.",
        saved="Nota salva.",
        empty="Escreva um título primeiro.",
        flow_start="Ao iniciar",
        flow_add="Clique: Adicionar nota",
        flow_export="Clique: Exportar CSV",
        count="Notas: ",
    ),
    "en": dict(
        name="My notes",
        collection="Notes",
        subtitle="Write a note and the app keeps it, with no database to program.",
        note_title="Title",
        note_text="Text",
        title_ph="Note title",
        text_ph="Write here…",
        add="Add note",
        export="Export CSV",
        csv_prompt="Save the notes to",
        ready="Ready.",
        saved="Note saved.",
        empty="Write a title first.",
        flow_start="On start",
        flow_add="Click: Add note",
        flow_export="Click: Export CSV",
        count="Notes: ",
    ),
}


def build(language, destination):
    t = TEXT[language]
    project = Project.empty(t["name"])
    root = project.root
    root.properties.update(title=t["name"], width=640, height=520, padding=16, spacing=10)

    def add(parent, kind, code=None, **props):
        node = project.add(parent.id, kind)
        node.properties.update(props)
        if code:
            node.properties["code_name"] = code
        return node

    add(root, K.LABEL, "heading", text=t["name"])
    add(root, K.LABEL, "subtitle", text=t["subtitle"])
    title = add(root, K.TEXT_INPUT, "title_input", placeholder=t["title_ph"])
    body = add(root, K.TEXT_AREA, "text_input", placeholder=t["text_ph"])
    buttons = add(root, K.CONTAINER)
    buttons.layout = LayoutKind.HORIZONTAL
    add_button = add(buttons, K.BUTTON, "add_button", text=t["add"])
    export_button = add(buttons, K.BUTTON, "export_button", text=t["export"])
    add(buttons, K.SPACER)
    table = add(root, K.TABLE, "notes_table")
    status = add(root, K.LABEL, "status", text=t["ready"])
    project.metadata["collections"] = [
        {
            "id": "notes",
            "name": t["collection"],
            "fields": [
                {"id": "title", "name": t["note_title"], "type": "text"},
                {"id": "text", "name": t["note_text"], "type": "text"},
            ],
        }
    ]
    steps = [
        (
            t["flow_start"],
            {"kind": "start", "component": root.id},
            [("show_records", table.id, "notes")],
        ),
        (
            t["flow_add"],
            {"kind": "click", "component": add_button.id},
            [
                (
                    "if",
                    ("bin", "==", ("read", title.id, "text"), lit("")),
                    [("set_text", status.id, lit(t["empty"]))],
                    [
                        (
                            "data_add",
                            "notes",
                            [
                                ("title", ("read", title.id, "text")),
                                ("text", ("read", body.id, "text")),
                            ],
                        ),
                        ("set_text", title.id, lit("")),
                        ("set_text", body.id, lit("")),
                        ("show_records", table.id, "notes"),
                        ("set_text", status.id, lit(t["saved"])),
                    ],
                ),
            ],
        ),
        (
            t["flow_export"],
            {"kind": "click", "component": export_button.id},
            [
                ("ask_file", "csv_path", lit(t["csv_prompt"])),
                ("export_table", table.id, ("var", "csv_path")),
            ],
        ),
    ]
    for index, (label, event, body_steps) in enumerate(steps):
        flow = make_flow(label, event, body_steps)
        flow["id"] = f"flow_{index:02d}_{event['kind']}"
        project.workflows.append(flow)
    project.application.update(
        id="org.makebench.notes",
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
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    for language, base in (("pt", ROOT / "examples"), ("en", ROOT / "examples" / "en")):
        build(language, base / "my-notes")
        print("wrote", base / "my-notes", file=sys.stderr)
