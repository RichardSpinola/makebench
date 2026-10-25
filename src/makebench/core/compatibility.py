"""Compatibilidade sintática de Python sem importar arquivos do projeto."""

import ast

SUPPORTED_MINORS = (12, 13, 14)


def syntax_error(source, minor):
    """Retorna diagnóstico para a gramática do destino; não avalia imports ou chamadas."""
    from .source import source_files

    for name, text in source_files(source).items():
        try:
            ast.parse(text, feature_version=(3, minor))
        except (SyntaxError, ValueError) as exc:
            return f"{name}: Python próprio incompatível com Python 3.{minor} do destino: {exc}"
    return None


def minimum_minor(source):
    """Infere a menor gramática suportada, sem prometer validar APIs dinâmicas."""
    return next((minor for minor in SUPPORTED_MINORS if syntax_error(source, minor) is None), None)
