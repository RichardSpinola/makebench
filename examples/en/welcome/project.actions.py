"""Functions of the welcome example. Test the application with F5."""


def introduce(ctx, value):
    """Receive the name from the field and write a greeting to the application output."""
    name = str(value).strip() or "visitor"
    ctx.log(f"Hello, {name}! Welcome to your Linux.")
