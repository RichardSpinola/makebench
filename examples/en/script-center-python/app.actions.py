# Function: simulate_installation
def fn_simulate_installation(ctx, package):
    variables = ctx.variables
    local_variables = {"package": package}
    ctx.log((str("Simulating installation: ") + str(local_variables.get("package"))))
    ctx.set_value("progress_task", 0)
    ctx.run_script("sleep 0.15", [], admin=False)
    ctx.set_value("progress_task", 20)
    ctx.log("Progress: 20%")
    ctx.run_script("sleep 0.15", [], admin=False)
    ctx.set_value("progress_task", 40)
    ctx.log("Progress: 40%")
    ctx.run_script("sleep 0.15", [], admin=False)
    ctx.set_value("progress_task", 60)
    ctx.log("Progress: 60%")
    ctx.run_script("sleep 0.15", [], admin=False)
    ctx.set_value("progress_task", 80)
    ctx.log("Progress: 80%")
    ctx.run_script("sleep 0.15", [], admin=False)
    ctx.set_value("progress_task", 100)
    ctx.log("Progress: 100%")
    ctx.run_script('printf "Example warning; the task still succeeds.\\n" >&2', [], admin=False)
    ctx.log("Simulation complete. No application was installed.")


# Function: long_task
def fn_long_task(ctx, value):
    variables = ctx.variables
    local_variables = {"value": value}
    ctx.run_script('for i in $(seq 1 60); do echo "Step $i/60"; sleep 1; done', [], admin=False)


# On start
# Event: start on 'window_main'
def on_task_center_makebench_start(ctx):
    variables = ctx.variables
    ctx.log("Task center ready. Choose a task.")


# Click: System information
# Event: click on 'button_check'
def on_system_information_click(ctx):
    variables = ctx.variables
    ctx.run("uname", ["-a"], admin=False)


# Click: Test script argument
# Event: click on 'button_install'
def on_test_script_argument_click(ctx):
    variables = ctx.variables
    variables["argument"] = ctx.ask("text", "What text should the script receive?", [])
    ctx.run_script(
        'set -eu\nprintf "Argument received literally: %s\\n" "$1"\nprintf "End of script.\\n"',
        [variables.get("argument")],
        admin=False,
    )


# Click: Ask and simulate installation
# Event: click on 'button_setup'
def on_ask_and_simulate_installation_click(ctx):
    variables = ctx.variables
    variables["package"] = ctx.ask(
        "choice", "Which application do you want to simulate?", ["Text editor", "Music player"]
    )
    ctx.confirm("Start the simulation? No package will be installed.")
    fn_simulate_installation(ctx, variables.get("package"))


# Click: Error example
# Event: click on 'button_error'
def on_error_example_click(ctx):
    variables = ctx.variables
    ctx.run_script(
        'printf "Starting error example\\n"\nprintf "Simulated failure: code 7\\n" >&2\nexit 7',
        [],
        admin=False,
    )
    ctx.log("This message must not appear after the failure.")


# Click: Long task to cancel
# Event: click on 'button_long'
def on_long_task_to_cancel_click(ctx):
    variables = ctx.variables
    fn_long_task(ctx, "")


# Click: Choose file
# Event: click on 'button_file'
def on_choose_file_click(ctx):
    variables = ctx.variables
    variables["file_path"] = ctx.ask("file", "Choose a file to show its path", [])
    ctx.log(variables.get("file_path"))


# Click: Check administrative authorization
# Event: click on 'button_admin'
def on_check_administrative_authorization_click(ctx):
    variables = ctx.variables
    ctx.run("/usr/bin/id", ["-u"], admin=True)
    ctx.log("The administrative task finished.")
