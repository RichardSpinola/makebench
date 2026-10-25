def confirm(ctx, value):
    """Delegate to the project's own module."""
    from makebench_user.checks import validate_runtime

    return validate_runtime(ctx, value)
