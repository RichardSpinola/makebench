"""Rotina exclusiva de QA: só executa após iniciar o aplicativo construído."""

import json
import os
from pathlib import Path
import sys
import packaging


def validate_runtime(ctx, valor):
    """Confere runtime, pacote adicional, terminal e execução de tarefas separadas."""
    from .calculations import normalize

    assert normalize(valor) == 3
    assert packaging.__version__ == "25.0"
    ctx.run(
        "/usr/bin/python3",
        [
            "-c",
            "import os,sys; assert not os.environ.get('PYTHONHOME'); print('PROCESS_PYTHON='+sys.version.split()[0])",
        ],
    )
    ctx.run(
        "python3",
        ["-c", "import packaging; assert packaging.__version__=='25.0'; print('DEPENDENCIA_OK')"],
    )
    result = {
        "steps": valor,
        "dependency": packaging.__version__,
        "python": sys.version,
        "executable": sys.executable,
        "prefix": sys.prefix,
        "host_visible": Path("/home/qa/makebench-host-sentinel").exists(),
        "worker_pid": os.getpid(),
        "gui_pid": os.getppid(),
        "terminal_pid": ctx.variables.get("terminal_pid"),
    }
    destination = os.environ.get("MAKEBENCH_QA_OUTPUT")
    if destination:
        Path(destination).write_text(json.dumps(result))
    ctx.log("QA_RESULT=" + json.dumps(result))
    ctx.run("/bin/sleep", ["2"])
    return valor == 3
