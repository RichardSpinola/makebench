"""Own functions of the workshop example."""

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
