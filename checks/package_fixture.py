# SPDX-License-Identifier: GPL-3.0-or-later
"""Disposable application to validate real installation and execution of the packages."""

from copy import deepcopy
from pathlib import Path
from makebench.core.storage import load_project
from makebench.core.logic import create_flow
from makebench.core.project import new_id


def fixture(backend):
    """Graph with a terminal, a declared dependency, tasks, two windows and its own closing."""
    root = Path(__file__).resolve().parents[1] / "examples/free-graph"
    project = load_project(root / (backend + ".makebench.json"))
    project.application.update(
        id="org.makebench.qa" + backend,
        name="Makebench QA " + backend.upper(),
        packages=["packaging==25.0"],
    )
    project.metadata.pop("debug_breakpoints", None)
    flow = project.workflows[0]
    flow["event"] = {"component": project.root.id, "kind": "start"}
    graph = flow["graph"]
    identifier = new_id("node")
    graph["nodes"].append(
        {
            "id": identifier,
            "op": "assign",
            "parameters": {"name": "terminal_pid"},
            "inputs": {"value": {"node": "terminal", "port": "value"}},
        }
    )
    for edge in graph["edges"]:
        if edge["from"] == "terminal" and edge["out"] == "next":
            edge["to"] = identifier
    graph["edges"].append({"from": identifier, "out": "next", "to": "repeat"})
    next(n for n in graph["nodes"] if n["id"] == "open")["parameters"]["close_current"] = True
    create_flow(project, project.windows[0].id)["body"] = [{"id": "close-qa", "op": "close_window"}]
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
    result = {'steps':valor,'dependency':packaging.__version__,'python':sys.version,'executable':sys.executable,'prefix':sys.prefix,'host_visible':Path('/home/qa/makebench-host-sentinel').exists(),'worker_pid':os.getpid(),'gui_pid':os.getppid(),'terminal_pid':ctx.variables['terminal_pid']}
    destination=os.environ.get('MAKEBENCH_QA_OUTPUT')
    if destination:Path(destination).write_text(json.dumps(result))
    ctx.log('QA_RESULT='+json.dumps(result))
    ctx.run('/bin/sleep',['2'])
    return valor == 3
'''
    return project, source, lambda name: (root / name).read_bytes()
