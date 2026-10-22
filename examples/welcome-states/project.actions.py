"""Funções próprias do projeto. Abrir o Makebench não executa este arquivo.

Cada função recebe ctx (contexto do aplicativo) e valor (entrada do bloco).
Use F5 para testar estas funções no processo do aplicativo.
"""


def saudacao(ctx, valor):
    """Exemplo de função que pode ser chamada por um bloco."""
    return f"Olá, {valor or 'Linux'}!"
