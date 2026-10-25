"""QA-only routine: runs only after the built application starts."""

import json
import os
from pathlib import Path
import sys
import packaging


def validate_runtime(ctx, value):
    """Check the runtime, the extra package, the terminal and separate task runs."""
    from .calculations import normalize

    assert normalize(value) == 3
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
        "steps": value,
        "dependency": packaging.__version__,
        "python": sys.version,
        "executable": sys.executable,
        "prefix": sys.prefix,
        "host_visible": Path("/home/qa/makebench-host-sentinel").exists(),
        "worker_pid": os.getpid(),
        "gui_pid": os.getppid(),
        "terminal_pid": ctx.variables["terminal_pid"],
    }
    destination = os.environ.get("MAKEBENCH_QA_OUTPUT")
    if destination:
        Path(destination).write_text(json.dumps(result))
    ctx.log("QA_RESULT=" + json.dumps(result))
    ctx.run("/bin/sleep", ["2"])
    return value == 3
