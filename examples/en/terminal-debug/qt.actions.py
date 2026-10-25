"""Functions of the terminal and debugging example."""

import sys


def start_python(ctx, value):
    """Open interactive Python only when the run's button is clicked."""
    result = value.upper()
    ctx.terminal_start("terminal", sys.executable, ["-u", "-i", "-q"])
    ctx.terminal_send("terminal", "print(" + repr(result) + ")\n")
    ctx.variables["result"] = result
    ctx.log(result)
