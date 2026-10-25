import sys


def iniciar(ctx, valor):
    """Abre Python interativo somente ao clicar no botão da execução."""
    resultado = valor.upper()
    ctx.terminal_start("terminal", sys.executable, ["-u", "-i", "-q"])
    ctx.terminal_send("terminal", "print(" + repr(resultado) + ")\n")
    ctx.variables["resultado"] = resultado
    ctx.log(resultado)
