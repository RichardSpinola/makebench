"""Ambiente de processos externos de pacotes relocáveis, compartilhado por Qt/GTK."""

import json
import os
from pathlib import Path
import shutil


def external_environment(program, base=None):
    """Preserva bibliotecas empacotadas só para executáveis do próprio pacote.

    Programas do sistema não devem receber PYTHONHOME, plugins Qt/GTK ou bibliotecas
    de outra distribuição. PATH conserva os auxiliares do pacote, incluindo o
    lançador de Python3, que estabelece seu próprio ambiente ao ser chamado.
    """
    environment = dict(os.environ if base is None else base)
    root = environment.get("MAKEBENCH_PORTABLE_ROOT")
    if not root:
        return environment
    executable = (
        shutil.which(program, path=environment.get("PATH")) if "/" not in program else program
    )
    if executable and Path(executable).resolve().is_relative_to(Path(root).resolve()):
        return environment
    try:
        original = json.loads(environment.get("MAKEBENCH_ORIGINAL_ENV", "{}"))
    except ValueError:
        original = {}
    for key, value in original.items():
        if value is None or value == "":
            environment.pop(key, None)
        else:
            environment[key] = value
    # O Python3 do pacote é um lançador que configura seu runtime separadamente.
    environment["PATH"] = str(Path(root) / "usr/bin") + ":" + (original.get("PATH") or os.defpath)
    return environment
