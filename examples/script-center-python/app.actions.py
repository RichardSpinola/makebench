# Function: simular_instalacao
def fn_simular_instalacao(ctx, pacote):
    variables = ctx.variables
    local_variables = {"pacote": pacote}
    ctx.log((str("Simulando instalação: ") + str(local_variables.get("pacote"))))
    ctx.set_value("progress_task", 0)
    ctx.run_script("sleep 0.15", [], admin=False)
    ctx.set_value("progress_task", 20)
    ctx.log("Progresso: 20%")
    ctx.run_script("sleep 0.15", [], admin=False)
    ctx.set_value("progress_task", 40)
    ctx.log("Progresso: 40%")
    ctx.run_script("sleep 0.15", [], admin=False)
    ctx.set_value("progress_task", 60)
    ctx.log("Progresso: 60%")
    ctx.run_script("sleep 0.15", [], admin=False)
    ctx.set_value("progress_task", 80)
    ctx.log("Progresso: 80%")
    ctx.run_script("sleep 0.15", [], admin=False)
    ctx.set_value("progress_task", 100)
    ctx.log("Progresso: 100%")
    ctx.run_script(
        'printf "Aviso de exemplo; a tarefa termina com sucesso.\\n" >&2', [], admin=False
    )
    ctx.log("Simulação concluída. Nenhum aplicativo foi instalado.")


# Function: tarefa_longa
def fn_tarefa_longa(ctx, valor):
    variables = ctx.variables
    local_variables = {"valor": valor}
    ctx.run_script('for i in $(seq 1 60); do echo "Etapa $i/60"; sleep 1; done', [], admin=False)


# Ao iniciar
# Event: start on 'window_main'
def on_central_de_tarefas_makebench_start(ctx):
    variables = ctx.variables
    ctx.log("Central pronta. Escolha uma tarefa.")


# Clique: Informações do sistema
# Event: click on 'button_check'
def on_informacoes_do_sistema_click(ctx):
    variables = ctx.variables
    ctx.run("uname", ["-a"], admin=False)


# Clique: Testar argumento de script
# Event: click on 'button_install'
def on_testar_argumento_de_script_click(ctx):
    variables = ctx.variables
    variables["argumento"] = ctx.ask("text", "Que texto o script deve receber?", [])
    ctx.run_script(
        'set -eu\nprintf "Argumento recebido literalmente: %s\\n" "$1"\nprintf "Fim do script.\\n"',
        [variables.get("argumento")],
        admin=False,
    )


# Clique: Perguntar e simular instalação
# Event: click on 'button_setup'
def on_perguntar_e_simular_instalacao_click(ctx):
    variables = ctx.variables
    variables["pacote"] = ctx.ask(
        "choice", "Qual aplicativo você quer simular?", ["Editor de texto", "Reprodutor de música"]
    )
    ctx.confirm("Iniciar a simulação? Nenhum pacote será instalado.")
    fn_simular_instalacao(ctx, variables.get("pacote"))


# Clique: Exemplo de erro
# Event: click on 'button_error'
def on_exemplo_de_erro_click(ctx):
    variables = ctx.variables
    ctx.run_script(
        'printf "Iniciando exemplo de erro\\n"\nprintf "Falha simulada: código 7\\n" >&2\nexit 7',
        [],
        admin=False,
    )
    ctx.log("Esta mensagem não deve aparecer após a falha.")


# Clique: Tarefa longa para cancelar
# Event: click on 'button_long'
def on_tarefa_longa_para_cancelar_click(ctx):
    variables = ctx.variables
    fn_tarefa_longa(ctx, "")


# Clique: Escolher arquivo
# Event: click on 'button_file'
def on_escolher_arquivo_click(ctx):
    variables = ctx.variables
    variables["arquivo"] = ctx.ask("file", "Escolha um arquivo para mostrar seu caminho", [])
    ctx.log(variables.get("arquivo"))


# Clique: Verificar autorização administrativa
# Event: click on 'button_admin'
def on_verificar_autorizacao_administrativa_click(ctx):
    variables = ctx.variables
    ctx.run("/usr/bin/id", ["-u"], admin=True)
    ctx.log("A tarefa administrativa terminou.")
