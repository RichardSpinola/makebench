"""Funções do exemplo de boas-vindas. Execução será conectada em M4."""


def apresentar(ctx, valor):
    """Recebe o nome do campo e escreve uma saudação na saída do aplicativo."""
    nome = str(valor).strip() or "visitante"
    ctx.log(f"Olá, {nome}! Bem-vindo ao seu Linux.")
