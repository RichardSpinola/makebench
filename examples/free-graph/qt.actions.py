"""Exemplo de função própria utilizada por um grafo livre."""


def confirmar(ctx, valor):
    """Confere o resultado e oferece valores para inspeção somente leitura."""
    resultado = valor == 3
    ctx.variables['confirmado'] = resultado
    ctx.log('PASSOS=' + str(valor))
    return resultado
