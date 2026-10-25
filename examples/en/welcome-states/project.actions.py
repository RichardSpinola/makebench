"""Your project's own functions. Opening Makebench never runs this file.

Each function receives ctx (the application context) and value (the block input).
Press F5 to test these functions in the application process.
"""


def greet(ctx, value):
    """Example function that a block can call."""
    return f"Hello, {value or 'Linux'}!"
