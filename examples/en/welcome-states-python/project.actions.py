# Click: Next
# Event: click on 'button_5ae736edec8c'
def on_next_click(ctx):
    variables = ctx.variables
    ctx.go_state("state_c29addc4d0f0")


# Click: Next
# Event: click on 'button_5ae736edec8c'
def on_next_click_2(ctx):
    variables = ctx.variables
    ctx.go_state("state_df013261401d")


# Click: Back
# Event: click on 'button_95ed1c9f4624'
def on_back_click(ctx):
    variables = ctx.variables
    ctx.go_state("@default")


# Click: Next
# Event: click on 'button_5ae736edec8c'
def on_next_click_3(ctx):
    variables = ctx.variables
    ctx.open_window("window_7622f4b4ade8", close_current=True)


# Click: Back
# Event: click on 'button_95ed1c9f4624'
def on_back_click_2(ctx):
    variables = ctx.variables
    ctx.go_state("state_c29addc4d0f0")
