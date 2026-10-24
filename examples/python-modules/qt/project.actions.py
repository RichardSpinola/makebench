def confirmar(ctx, valor):
    """Delega ao módulo próprio do projeto."""
    from makebench_user.checks import validate_runtime
    return validate_runtime(ctx, valor)
