# Function: apresentar
def fn_apresentar(ctx, valor):
    variables = ctx.variables
    local_variables = {"valor": valor}
    if local_variables.get("valor") == "":
        ctx.log((str((str("Olá, ") + str("visitante"))) + str("! Bem-vindo ao seu Linux.")))
    else:
        ctx.log(
            (
                str((str("Olá, ") + str(local_variables.get("valor"))))
                + str("! Bem-vindo ao seu Linux.")
            )
        )


# Clique: Vamos começar
# Event: click on 'button_start'
def on_vamos_comecar_click(ctx):
    variables = ctx.variables
    # Ao clicar, abrir a página de preferências.
    ctx.show_page("page_options")


# Clique: Concluir configuração
# Event: click on 'button_finish'
def on_concluir_configuracao_click(ctx):
    variables = ctx.variables
    # Esta etapa monta o fluxo; ainda não grava preferências no sistema.
    if ctx.read("check_updates", "checked"):
        ctx.log("Lembretes de atualização selecionados.")
    else:
        ctx.log("Lembretes não selecionados.")
    # A função apresentar é uma função de blocos; veja Lógica › Funções.
    fn_apresentar(ctx, ctx.read("field_name", "text"))
    ctx.message("Seu aplicativo de boas-vindas está tomando forma!")


# Ao iniciar
# Event: start on 'window_welcome'
def on_bem_vindo_ao_seu_linux_start(ctx):
    variables = ctx.variables
    ctx.log("Aplicativo iniciado.")
