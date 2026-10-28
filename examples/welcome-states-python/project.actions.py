# Clique: Próximo
# Event: click on 'button_5ae736edec8c'
def on_proximo_click(ctx):
    variables = ctx.variables
    ctx.go_state("state_c29addc4d0f0")


# Clique: Próximo
# Event: click on 'button_5ae736edec8c'
def on_proximo_click_2(ctx):
    variables = ctx.variables
    ctx.go_state("state_df013261401d")


# Clique: Voltar
# Event: click on 'button_95ed1c9f4624'
def on_voltar_click(ctx):
    variables = ctx.variables
    ctx.go_state("@default")


# Clique: Próximo
# Event: click on 'button_5ae736edec8c'
def on_proximo_click_3(ctx):
    variables = ctx.variables
    ctx.open_window("window_7622f4b4ade8", close_current=True)


# Clique: Voltar
# Event: click on 'button_95ed1c9f4624'
def on_voltar_click_2(ctx):
    variables = ctx.variables
    ctx.go_state("state_c29addc4d0f0")
