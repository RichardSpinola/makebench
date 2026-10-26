# SPDX-License-Identifier: MIT
"""Generate the "complete workshop" examples (blocks and nodes, Portuguese and English).

Run from the repository root: PYTHONPATH=src .venv/bin/python checks/build_full_examples.py
Both variants share one description of the behavior, compiled into blocks or into a node graph.
"""

import sys
import tempfile
from pathlib import Path

from makebench.core.assets import AssetStore
from makebench.core.logic import LOGIC_VERSION
from makebench.core.navigation import add_state, add_window
from makebench.core.project import ComponentKind as K
from makebench.core.project import LayoutKind, Project
from makebench.core.source import SourceBuffer, SourceText
from makebench.core.storage import save_workspace

ROOT = Path(__file__).resolve().parents[1]

LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 100" width="160" height="100">
<rect width="160" height="100" rx="12" fill="#3584e4"/>
<path d="M30 70 L60 30 L90 70 Z" fill="#fff"/><circle cx="115" cy="50" r="22" fill="#e5a50a"/>
</svg>"""

TOOLS = '''"""Own module of the workshop: pure Python helpers, imported by actions."""


def format_status(visits, name):
    """Text shown in the status line."""
    return "{} · {}".format(name or "{who}", visits)
'''

ACTIONS = '''"""Own functions of the workshop example."""

from makebench_user.tools import format_status


def register(ctx, visits):
    """Called from the logic: logs the status line text and returns it."""
    name = ctx.read("name_input", "text")
    text = format_status(visits, name)
    ctx.log(text)
    return text


def change_theme(ctx, mode):
    """Switch the look of the current window while the application runs."""
    ctx.set_theme(mode, "#26a269" if mode == "dark" else "")
    ctx.set_background("#101820" if mode == "dark" else "")
    return mode
'''

TEXT = {
    "pt": dict(
        name="Oficina completa",
        title="Oficina completa",
        subtitle="Um exemplo que usa cada recurso do Makebench.",
        about="Sobre",
        settings="Aparência",
        home="Início",
        tasks="Tarefas",
        terminal="Terminal",
        free="Livre",
        name_ph="Seu nome",
        loud="Cumprimentar em voz alta",
        greet="Cumprimentar",
        busy="Ficar ocupado",
        ready="Ficar pronto",
        count="Contar até 3",
        to_term="Ir ao terminal",
        info="Informações do sistema",
        script="Rodar um script",
        ask="Perguntar e confirmar",
        t_start="Iniciar",
        t_send="Enviar comando",
        t_stop="Parar",
        free_label="Posições livres",
        free_button="Botão solto",
        status_ready="Pronto.",
        status_busy="Ocupado…",
        about_title="Sobre a Oficina",
        about_text="Janela escura criada só com propriedades da janela.",
        close="Fechar",
        look_title="Aparência",
        look_text="Troque a aparência desta janela com uma função própria.",
        dark="Escuro",
        light="Claro",
        busy_state="Ocupado",
        hello="Olá, ",
        loud_msg="OLÁ EM VOZ ALTA!",
        quiet_msg="Olá em voz baixa.",
        ready_msg="Oficina pronta.",
        step="Passo ",
        arg_prompt="Que texto o script deve receber?",
        confirm_prompt="Continuar com o texto informado?",
        ok_msg="Confirmado.",
        arg_value="demo",
        script_src='printf "Argumento: %s\\n" "$1"',
        term_cmd="echo olá do terminal\n",
        guide="Roteiro",
        guide_title="Roteiro de testes",
        guide_steps=[
            "1. Escreva um nome, marque a caixa e clique em Cumprimentar (veja a barra e o progresso).",
            "2. Clique em Ficar ocupado: o estado Ocupado muda o texto e desliga o botão.",
            "3. Na aba Tarefas, rode as tarefas e veja a saída.",
            "4. Na aba Terminal, inicie, envie um comando e pare.",
            "5. Abra Aparência e troque entre Claro e Escuro; abra Sobre para ver a janela escura.",
            "6. No editor, use F9 para depurar: há um ponto de parada no primeiro bloco do Cumprimentar.",
        ],
        comment="A ordem vem dos fios, não da posição.",
    ),
    "en": dict(
        name="Complete workshop",
        title="Complete workshop",
        subtitle="An example that uses every Makebench feature.",
        about="About",
        settings="Look",
        home="Home",
        tasks="Tasks",
        terminal="Terminal",
        free="Free",
        name_ph="Your name",
        loud="Greet out loud",
        greet="Greet",
        busy="Get busy",
        ready="Get ready",
        count="Count to 3",
        to_term="Go to the terminal",
        info="System information",
        script="Run a script",
        ask="Ask and confirm",
        t_start="Start",
        t_send="Send command",
        t_stop="Stop",
        free_label="Free positions",
        free_button="Loose button",
        status_ready="Ready.",
        status_busy="Busy…",
        about_title="About the workshop",
        about_text="A dark window made only with window properties.",
        close="Close",
        look_title="Look",
        look_text="Change this window's look with an own function.",
        dark="Dark",
        light="Light",
        busy_state="Busy",
        hello="Hello, ",
        loud_msg="HELLO OUT LOUD!",
        quiet_msg="Hello, quietly.",
        ready_msg="Workshop ready.",
        step="Step ",
        arg_prompt="What text should the script receive?",
        confirm_prompt="Continue with the given text?",
        ok_msg="Confirmed.",
        arg_value="demo",
        script_src='printf "Argument: %s\\n" "$1"',
        term_cmd="echo hello from the terminal\n",
        guide="Guide",
        guide_title="Test guide",
        guide_steps=[
            "1. Type a name, tick the box and click Greet (watch the status line and progress).",
            "2. Click Get busy: the Busy state changes the text and disables the button.",
            "3. On the Tasks tab, run the tasks and read the output.",
            "4. On the Terminal tab, start it, send a command and stop it.",
            "5. Open Look and switch between Light and Dark; open About for the dark window.",
            "6. In the editor press F9 to debug: a breakpoint sits on the first block of Greet.",
        ],
        comment="Order comes from the wires, not from the position.",
    ),
}


# Expressions: ("lit", v) ("var", n) ("read", comp, attr) ("bin", op, l, r) ("join", l, r) ("list", [..])
def lit(v):
    return ("lit", v)


class Ids:
    def __init__(self):
        self.n = 0

    def __call__(self, prefix):
        self.n += 1
        return f"{prefix}_{self.n:03d}"


def block_expr(e, ids):
    kind = e[0]
    if kind == "lit":
        return {"id": ids("block"), "op": "literal", "value": e[1]}
    if kind == "var":
        return {"id": ids("block"), "op": "variable", "name": e[1], "scope": "project"}
    if kind == "read":
        return {"id": ids("block"), "op": "read", "component": e[1], "attribute": e[2]}
    if kind == "bin":
        return {
            "id": ids("block"),
            "op": "binary",
            "operator": e[1],
            "left": block_expr(e[2], ids),
            "right": block_expr(e[3], ids),
        }
    if kind == "join":
        return {
            "id": ids("block"),
            "op": "join",
            "left": block_expr(e[1], ids),
            "right": block_expr(e[2], ids),
        }
    return {"id": ids("block"), "op": "list", "items": [block_expr(x, ids) for x in e[1]]}


def block_stmt(s, ids):
    op = s[0]
    b = {"op": op}
    if op in {"log", "message"}:
        b["value"] = block_expr(s[1], ids)
    elif op in {"set_text", "set_enabled", "set_value"}:
        b.update(component=s[1], value=block_expr(s[2], ids))
    elif op == "assign":
        b.update(name=s[1], scope="project", value=block_expr(s[2], ids))
    elif op == "if":
        b.update(
            condition=block_expr(s[1], ids),
            then=[block_stmt(x, ids) for x in s[2]],
            **{"else": [block_stmt(x, ids) for x in s[3]]},
        )
    elif op == "repeat":
        b.update(count=block_expr(s[1], ids), body=[block_stmt(x, ids) for x in s[2]])
    elif op == "call":
        b.update(function=s[1], value=block_expr(s[2], ids))
    elif op in {"run", "script"}:
        b.update(admin=False, arguments=block_expr(s[2], ids))
        b["program" if op == "run" else "source"] = block_expr(s[1], ids)
    elif op == "terminal_start":
        b.update(component=s[1], program=block_expr(s[2], ids), arguments=block_expr(s[3], ids))
    elif op == "terminal_send":
        b.update(component=s[1], value=block_expr(s[2], ids))
    elif op in {"terminal_stop", "show_page"}:
        b["component"] = s[1]
    elif op == "go_state":
        b["state"] = s[1]
    elif op == "open_window":
        b.update(window=s[1], close_current=False)
    elif op == "ask":
        b.update(
            kind="text",
            name=s[1],
            scope="project",
            prompt=block_expr(s[2], ids),
            options=block_expr(("list", []), ids),
        )
    elif op == "confirm":
        b["prompt"] = block_expr(s[1], ids)
    b["id"] = ids("block")
    return b


class Graph:
    def __init__(self, ids):
        self.ids, self.nodes, self.edges, self.layout = ids, [], [], {}
        self.rows = {}

    def place(self, node_id, depth):
        row = self.rows.get(depth, 0)
        self.rows[depth] = row + 1
        self.layout[node_id] = [20 + depth * 310, 40 + row * 190]

    def expr(self, e, depth):
        """Return an input: a literal or a wire to a new value node."""
        kind = e[0]
        if kind == "lit":
            return {"value": e[1]}
        if kind == "list" and all(x[0] == "lit" for x in e[1]):
            return {"value": [x[1] for x in e[1]]}
        node = {"id": self.ids("node"), "inputs": {}, "parameters": {}}
        if kind == "var":
            node.update(op="variable", parameters={"name": e[1], "scope": "project"})
        elif kind == "read":
            node.update(op="read", parameters={"component": e[1], "attribute": e[2]})
        elif kind == "bin":
            node.update(op="binary", parameters={"operator": e[1]})
            node["inputs"] = {
                "left": self.expr(e[2], depth + 1),
                "right": self.expr(e[3], depth + 1),
            }
        elif kind == "join":
            node.update(op="join")
            node["inputs"] = {
                "left": self.expr(e[1], depth + 1),
                "right": self.expr(e[2], depth + 1),
            }
        self.nodes.append(node)
        self.place(node["id"], depth)
        return {"node": node["id"], "port": "value"}

    def stmts(self, steps, source, port, depth):
        """Chain statements after (source, port); return the last (node, port) to continue from."""
        for s in steps:
            node = self.stmt(s, depth)
            self.edges.append({"from": source, "out": port, "to": node["id"]})
            if s[0] == "if":
                return None
            source, port = node["id"], "done" if s[0] == "repeat" else "next"
            depth += 1
        return source, port

    def stmt(self, s, depth):
        op = s[0]
        node = {"id": self.ids("node"), "op": op, "parameters": {}, "inputs": {}}
        p, i = node["parameters"], node["inputs"]
        if op in {"log", "message"}:
            i["value"] = self.expr(s[1], depth)
        elif op in {"set_text", "set_enabled", "set_value"}:
            p["component"] = s[1]
            i["value"] = self.expr(s[2], depth)
        elif op == "assign":
            p.update(name=s[1], scope="project")
            i["value"] = self.expr(s[2], depth)
        elif op == "if":
            i["condition"] = self.expr(s[1], depth)
        elif op == "repeat":
            i["count"] = self.expr(s[1], depth)
        elif op == "call":
            p["function"] = s[1]
            i["value"] = self.expr(s[2], depth)
        elif op in {"run", "script"}:
            p["admin"] = False
            i["program" if op == "run" else "source"] = self.expr(s[1], depth)
            i["arguments"] = self.expr(s[2], depth)
        elif op == "terminal_start":
            p["component"] = s[1]
            i["program"] = self.expr(s[2], depth)
            i["arguments"] = self.expr(s[3], depth)
        elif op == "terminal_send":
            p["component"] = s[1]
            i["value"] = self.expr(s[2], depth)
        elif op in {"terminal_stop", "show_page"}:
            p["component"] = s[1]
        elif op == "go_state":
            p["state"] = s[1]
        elif op == "open_window":
            p.update(window=s[1], close_current=False)
        elif op == "ask":
            p.update(kind="text", name=s[1], scope="project")
            i["prompt"] = self.expr(s[2], depth)
            i["options"] = {"value": []}
        elif op == "confirm":
            i["prompt"] = self.expr(s[1], depth)
        self.nodes.append(node)
        self.place(node["id"], depth)
        if op == "if":
            self.stmts(s[2], node["id"], "true", depth + 1)
            self.stmts(s[3], node["id"], "false", depth + 1)
        elif op == "repeat":
            self.stmts(s[2], node["id"], "body", depth + 1)
        return node


def make_flow(name, event, steps, editor, comment=None):
    ids = Ids()
    flow = {"id": "flow_" + event["component"].split("_", 1)[-1][:10] + name[:0], "name": name}
    flow["event"] = event
    if editor == "blocks":
        flow["body"] = [block_stmt(s, ids) for s in steps]
        return flow
    entry = "event_" + event["component"]
    graph = Graph(ids)
    graph.nodes.append({"id": entry, "op": "event", "parameters": {}, "inputs": {}})
    graph.place(entry, 0)
    graph.stmts(steps, entry, "next", 1)
    flow.update(
        body=[],
        workspace={},
        editor="nodes",
        graph={
            "graph_version": 1,
            "entry": entry,
            "nodes": graph.nodes,
            "edges": graph.edges,
        },
        graph_layout=graph.layout,
    )
    if comment:
        flow["graph_comments"] = [{"id": "comment-main", "text": comment, "position": [20, -140]}]
    return flow


def build(language, editor, destination):
    t = TEXT[language]
    project = Project.empty(
        f"{t['name']} — {'Nós' if language == 'pt' else 'Nodes'}"
        if editor == "nodes"
        else f"{t['name']} — {'Blocos' if language == 'pt' else 'Blocks'}"
    )
    root = project.root
    root.properties.update(title=t["title"], width=720, height=560, padding=16, spacing=10)
    assets = AssetStore()
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "logo.svg").write_text(LOGO)
        logo = assets.import_image(Path(tmp) / "logo.svg")

    def add(parent, kind, code=None, **props):
        node = project.add(parent.id, kind)
        node.properties.update(props)
        if code:
            node.properties["code_name"] = code
        return node

    header = add(root, K.CONTAINER)
    header.layout = LayoutKind.HORIZONTAL
    title = add(header, K.LABEL, "title_label", text=t["title"])
    add(header, K.SPACER)
    about_button = add(header, K.BUTTON, "about_button", text=t["about"])
    look_button = add(header, K.BUTTON, "look_button", text=t["settings"])
    guide_button = add(header, K.BUTTON, "guide_button", text=t["guide"])
    subtitle = add(root, K.LABEL, "subtitle", text=t["subtitle"])
    add(root, K.SEPARATOR)
    pages = add(root, K.PAGES)
    pages.children[0].properties["title"] = t["home"]
    home = pages.children[0]
    home.layout = LayoutKind.GRID
    home.properties["columns"] = 2
    tasks = project.add(pages.id, K.PAGE)
    tasks.properties["title"] = t["tasks"]
    term_page = project.add(pages.id, K.PAGE)
    term_page.properties["title"] = t["terminal"]
    free_page = project.add(pages.id, K.PAGE)
    free_page.properties["title"] = t["free"]
    free_page.layout = LayoutKind.FREE

    add(home, K.LABEL, text=t["name_ph"])
    name_input = add(home, K.TEXT_INPUT, "name_input", placeholder=t["name_ph"])
    loud = add(home, K.CHECKBOX, "loud_box", text=t["loud"])
    greet = add(home, K.BUTTON, "greet_button", text=t["greet"])
    logo_image = add(home, K.IMAGE, "logo", source=logo, alt_text=t["title"])
    progress = add(home, K.PROGRESS, "progress")
    busy = add(home, K.BUTTON, "busy_button", text=t["busy"])
    ready = add(home, K.BUTTON, "ready_button", text=t["ready"])
    count = add(home, K.BUTTON, "count_button", text=t["count"])
    to_term = add(home, K.BUTTON, "terminal_page_button", text=t["to_term"])

    info = add(tasks, K.BUTTON, "info_button", text=t["info"])
    script = add(tasks, K.BUTTON, "script_button", text=t["script"])
    ask = add(tasks, K.BUTTON, "ask_button", text=t["ask"])
    log = add(tasks, K.OUTPUT, "log_output")

    term = add(term_page, K.TERMINAL, "terminal")
    buttons = add(term_page, K.CONTAINER)
    buttons.layout = LayoutKind.HORIZONTAL
    t_start = add(buttons, K.BUTTON, "terminal_start", text=t["t_start"])
    t_send = add(buttons, K.BUTTON, "terminal_send", text=t["t_send"])
    t_stop = add(buttons, K.BUTTON, "terminal_stop", text=t["t_stop"])

    free_label = add(free_page, K.LABEL, text=t["free_label"])
    free_label.geometry.update(x=24, y=24, width=200, height=32)
    loose = add(free_page, K.BUTTON, text=t["free_button"])
    loose.geometry.update(x=260, y=70, width=160, height=36)

    add(root, K.SPACER)
    status = add(root, K.LABEL, "status", text=t["status_ready"])

    about_root = add_window(project, t["about_title"])
    about_root.properties.update(
        title=t["about_title"], width=420, height=240, theme="dark", accent="#e5a50a"
    )
    about_text = project.add(about_root.id, K.LABEL)
    about_text.properties.update(text=t["about_text"])
    close_button = project.add(about_root.id, K.BUTTON)
    close_button.properties.update(text=t["close"], code_name="close_button")
    look_root = add_window(project, t["look_title"])
    look_root.properties.update(
        title=t["look_title"], width=420, height=240, background="#e8f0fe", accent="#26a269"
    )
    look_text = project.add(look_root.id, K.LABEL)
    look_text.properties.update(text=t["look_text"])
    dark_button = project.add(look_root.id, K.BUTTON)
    dark_button.properties.update(text=t["dark"], code_name="dark_button")
    light_button = project.add(look_root.id, K.BUTTON)
    light_button.properties.update(text=t["light"], code_name="light_button")

    guide_root = add_window(project, t["guide_title"])
    guide_root.properties.update(title=t["guide_title"], width=560, height=360)
    for line in t["guide_steps"]:
        step_label = project.add(guide_root.id, K.LABEL)
        step_label.properties.update(text=line)

    state = add_state(project, root.id, t["busy_state"])
    state_id = state["id"] if isinstance(state, dict) else project.states[root.id][-1]["id"]
    overrides = project.states[root.id][-1]["overrides"]
    overrides[status.id] = {"text": t["status_busy"]}
    overrides[greet.id] = {"enabled": False}

    c = lambda node, attr="text": ("read", node.id, attr)  # noqa: E731
    visits = ("var", "visits")
    steps = {
        (root.id, "start"): [
            ("assign", "visits", lit(0)),
            ("assign", "step", lit(0)),
            ("log", lit(t["ready_msg"])),
            ("set_text", status.id, lit(t["status_ready"])),
        ],
        (greet.id, "click"): [
            ("assign", "visits", ("bin", "+", visits, lit(1))),
            ("call", "register", visits),
            ("set_text", status.id, ("join", lit(t["hello"]), c(name_input))),
            ("set_value", progress.id, ("bin", "*", visits, lit(20))),
            (
                "if",
                c(loud, "checked"),
                [("message", lit(t["loud_msg"]))],
                [("log", lit(t["quiet_msg"]))],
            ),
        ],
        (busy.id, "click"): [("go_state", state_id)],
        (ready.id, "click"): [("go_state", "@default"), ("set_enabled", greet.id, lit(True))],
        (count.id, "click"): [
            (
                "repeat",
                lit(3),
                [
                    ("assign", "step", ("bin", "+", ("var", "step"), lit(1))),
                    ("log", ("join", lit(t["step"]), ("var", "step"))),
                ],
            ),
        ],
        (to_term.id, "click"): [("show_page", term_page.id)],
        (info.id, "click"): [("run", lit("uname"), ("list", [lit("-a")]))],
        (script.id, "click"): [
            ("ask", "argument", lit(t["arg_prompt"])),
            ("script", lit(t["script_src"]), ("list", [lit(t["arg_value"])])),
        ],
        (ask.id, "click"): [
            ("ask", "answer", lit(t["arg_prompt"])),
            ("confirm", lit(t["confirm_prompt"])),
            ("log", lit(t["ok_msg"])),
        ],
        (t_start.id, "click"): [("terminal_start", term.id, lit("/bin/sh"), ("list", []))],
        (t_send.id, "click"): [("terminal_send", term.id, lit(t["term_cmd"]))],
        (t_stop.id, "click"): [("terminal_stop", term.id)],
        (about_button.id, "click"): [("open_window", about_root.id)],
        (guide_button.id, "click"): [("open_window", guide_root.id)],
        (look_button.id, "click"): [("open_window", look_root.id)],
        (close_button.id, "click"): [("close_window",)],
        (dark_button.id, "click"): [("call", "change_theme", lit("dark"))],
        (light_button.id, "click"): [("call", "change_theme", lit("light"))],
    }
    project.workflows = []
    project.metadata["logic_version"] = LOGIC_VERSION
    names = {}
    owners = {
        n.id: n
        for n in (
            root,
            greet,
            busy,
            ready,
            count,
            to_term,
            info,
            script,
            ask,
            t_start,
            t_send,
            t_stop,
            about_button,
            look_button,
            guide_button,
            close_button,
            dark_button,
            light_button,
        )
    }
    for (owner_id, kind), body in steps.items():
        owner = owners[owner_id]
        label = (
            (
                f"Clique: {owner.properties.get('text', '')}"
                if language == "pt"
                else f"Click: {owner.properties.get('text', '')}"
            )
            if kind == "click"
            else ("Ao iniciar" if language == "pt" else "On start")
        )
        body = [s for s in body]
        flow = make_flow(
            label,
            {"kind": kind, "component": owner.id},
            body,
            editor,
            t["comment"] if kind == "start" else None,
        )
        flow["id"] = f"flow_{len(project.workflows):02d}_{kind}"
        project.workflows.append(flow)
        names[owner.id] = flow["id"]
    # The logic uses the Portuguese-free function names below.
    project.application.update(
        id="org.makebench.workshop" + (".nodes" if editor == "nodes" else ".blocks"),
        name=project.name,
        version="0.1.0",
        backend="qt",
        icon=logo,
        language="pt_BR" if language == "pt" else "en",
    )
    project.metadata["example"] = t["subtitle"]
    first = project.workflows[1]
    project.metadata["debug_breakpoints"] = [
        {
            "file": "block",
            "flow": first["id"],
            "block": (
                first["body"][0]["id"] if editor == "blocks" else first["graph"]["nodes"][1]["id"]
            ),
        }
    ]
    project.entry_window = root.id
    source = SourceBuffer()
    source.text = SourceText(
        ACTIONS.replace("{who}", "?"),
        {
            "makebench_user/__init__.py": "",
            "makebench_user/tools.py": TOOLS.replace("{who}", "?"),
        },
    )
    destination.mkdir(parents=True, exist_ok=True)
    save_workspace(project, source, assets, destination / "project.makebench.json")


if __name__ == "__main__":
    for language, base in (("pt", ROOT / "examples"), ("en", ROOT / "examples" / "en")):
        for editor, folder in (("nodes", "full-nodes"), ("blocks", "full-blocks")):
            build(language, editor, base / folder)
            print("wrote", base / folder, file=sys.stderr)
