"""Example of your own function used by a free graph."""


def confirm(ctx, value):
    """Check the result and offer values for read-only inspection."""
    result = value == 3
    ctx.variables["confirmed"] = result
    ctx.log("STEPS=" + str(value))
    return result
