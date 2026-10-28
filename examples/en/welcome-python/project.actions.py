# Function: introduce
def fn_introduce(ctx, value):
    variables = ctx.variables
    local_variables = {"value": value}
    if local_variables.get("value") == "":
        ctx.log((str((str("Hello, ") + str("visitor"))) + str("! Welcome to your Linux.")))
    else:
        ctx.log(
            (
                str((str("Hello, ") + str(local_variables.get("value"))))
                + str("! Welcome to your Linux.")
            )
        )


# Click: Let's start
# Event: click on 'button_start'
def on_let_s_start_click(ctx):
    variables = ctx.variables
    # On click, open the preferences page.
    ctx.show_page("page_options")


# Click: Finish setup
# Event: click on 'button_finish'
def on_finish_setup_click(ctx):
    variables = ctx.variables
    # This step builds the flow; it does not write preferences to the system.
    if ctx.read("check_updates", "checked"):
        ctx.log("Update reminders selected.")
    else:
        ctx.log("Reminders not selected.")
    # The introduce function is a block function; see Logic › Functions.
    fn_introduce(ctx, ctx.read("field_name", "text"))
    ctx.message("Your welcome application is taking shape!")


# On start
# Event: start on 'window_welcome'
def on_welcome_to_your_linux_start(ctx):
    variables = ctx.variables
    ctx.log("Application started.")
