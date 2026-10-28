# Function: iniciar
def fn_iniciar(ctx, valor):
    variables = ctx.variables
    local_variables = {"valor": valor}
    ctx.terminal_start("terminal_7b1f01c015ec", "python3", ["-u", "-i", "-q"])
    ctx.terminal_send(
        "terminal_7b1f01c015ec",
        (str((str("print('") + str(local_variables.get("valor")))) + str("'.upper())\n")),
    )
    ctx.log(local_variables.get("valor"))


# Clique: Iniciar Python
# Event: click on 'button_bd81d72521ed'
def on_iniciar_python_click(ctx):
    variables = ctx.variables
    fn_iniciar(ctx, "Terminal pronto")
