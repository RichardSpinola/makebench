"""Funções da central. Executam apenas ao testar o aplicativo com F5."""
import sys


def simular_instalacao(ctx, valor):
    """Demonstra progresso e stderr sem instalar nem modificar pacotes."""
    ctx.log(f"Simulando instalação: {valor}")
    ctx.set_value("progress_task", 0)
    for progresso in (20, 40, 60, 80, 100):
        ctx.run(sys.executable, ["-c", "import time; time.sleep(0.15)"])
        ctx.set_value("progress_task", progresso)
        ctx.log(f"Progresso: {progresso}%")
    ctx.run_script('printf "Aviso de exemplo; a tarefa termina com sucesso.\\n" >&2')
    ctx.log("Simulação concluída. Nenhum aplicativo foi instalado.")


def tarefa_longa(ctx, valor):
    """Produz saída durante um minuto; Parar execução cancela esta tarefa comum."""
    ctx.run(sys.executable, ["-u", "-c", "import time\nfor i in range(60):\n print(f'Etapa {i+1}/60', flush=True)\n time.sleep(1)"])
