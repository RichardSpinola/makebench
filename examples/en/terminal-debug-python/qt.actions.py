# Function: start_python
def fn_start_python(ctx, value):
    variables = ctx.variables
    local_variables = {"value": value}
    ctx.terminal_start("terminal_7b1f01c015ec", "python3", ["-u", "-i", "-q"])
    ctx.terminal_send(
        "terminal_7b1f01c015ec",
        (str((str("print('") + str(local_variables.get("value")))) + str("'.upper())\n")),
    )
    ctx.log(local_variables.get("value"))


# Click: Start Python
# Event: click on 'button_bd81d72521ed'
def on_start_python_click(ctx):
    variables = ctx.variables
    fn_start_python(ctx, "Terminal ready")
