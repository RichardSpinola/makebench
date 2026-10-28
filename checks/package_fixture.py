# SPDX-License-Identifier: GPL-3.0-or-later
"""Disposable application to validate real installation and execution of the packages."""

from pathlib import Path
from makebench.core.storage import load_project
from makebench.core.logic import create_flow
from makebench.core.navigation import add_window
from makebench.core.project import ComponentKind, new_id


def fixture(backend):
    """Blocks with a terminal, a declared dependency, tasks, two windows and its own closing."""
    root = Path(__file__).resolve().parents[1] / "examples/terminal-debug"
    project = load_project(root / (backend + ".makebench.json"))
    project.application.update(
        id="org.makebench.qa" + backend,
        name="Makebench QA " + backend.upper(),
        packages=["packaging==25.0"],
    )
    project.metadata.pop("debug_breakpoints", None)
    terminal = next(n for n in project.walk() if n.kind == ComponentKind.TERMINAL)
    done = add_window(project, "Done")
    project.workflows.clear()

    def value(item):
        return {"id": new_id("value"), "op": "literal", "value": item}

    def steps():
        return {"id": new_id("value"), "op": "variable", "name": "passos", "scope": "project"}

    create_flow(project, project.root.id)["body"] = [
        {
            "id": new_id("block"),
            "op": "assign",
            "name": "passos",
            "scope": "project",
            "value": value(0),
        },
        {
            "id": new_id("block"),
            "op": "terminal_start",
            "component": terminal.id,
            "program": value("/bin/sh"),
            "arguments": {"id": new_id("value"), "op": "list", "items": []},
        },
        {
            "id": new_id("block"),
            "op": "repeat",
            "count": value(3),
            "body": [
                {
                    "id": new_id("block"),
                    "op": "terminal_send",
                    "component": terminal.id,
                    "value": value("printf 'PASSO\\n'\n"),
                },
                {
                    "id": new_id("block"),
                    "op": "assign",
                    "name": "passos",
                    "scope": "project",
                    "value": {
                        "id": new_id("value"),
                        "op": "binary",
                        "operator": "+",
                        "left": steps(),
                        "right": value(1),
                    },
                },
            ],
        },
        {"id": new_id("block"), "op": "call", "function": "confirmar", "value": steps()},
        {"id": new_id("block"), "op": "open_window", "window": done.id, "close_current": True},
    ]
    create_flow(project, done.id)["body"] = [{"id": "close-qa", "op": "close_window"}]
    source = '''"""QA-only routine: runs only after the built application starts."""
import json
import os
from pathlib import Path
import sys
import packaging


def confirmar(ctx, valor):
    """Check the runtime, the extra package, the terminal and separate task runs."""
    assert packaging.__version__ == '25.0'
    ctx.run('/usr/bin/python3', ['-c', "import os,sys; assert not os.environ.get('PYTHONHOME'); print('PROCESS_PYTHON='+sys.version.split()[0])"])
    ctx.run('python3', ['-c', "import packaging; assert packaging.__version__=='25.0'; print('DEPENDENCIA_OK')"])
    result = {'steps':valor,'dependency':packaging.__version__,'python':sys.version,'executable':sys.executable,'prefix':sys.prefix,'host_visible':Path('/home/qa/makebench-host-sentinel').exists(),'worker_pid':os.getpid(),'gui_pid':os.getppid(),'terminal_pid':None}
    destination=os.environ.get('MAKEBENCH_QA_OUTPUT')
    if destination:Path(destination).write_text(json.dumps(result))
    ctx.log('QA_RESULT='+json.dumps(result))
    ctx.run('/bin/sleep',['2'])
    return valor == 3
'''
    return project, source, lambda name: (root / name).read_bytes()
