"""Regressões em Python3.12/3.13 isolados, usando somente rodas já preparadas."""

import argparse
from pathlib import Path
import shutil
import subprocess
from makebench.core.portable import command, editor_project, ready, wheel_root


def main():
    """Não instala no host: SDK privado, venv no staging e suíte integral copiada."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--minor", choices=(12, 13), type=int, required=True)
    args = parser.parse_args()
    project = editor_project()
    if not ready(project, True):
        raise RuntimeError("Prepare o runtime do editor em Exportar antes deste teste.")
    root = args.output.resolve()
    repo = Path(__file__).resolve().parents[1]
    if root.is_relative_to(repo):
        raise RuntimeError("Use uma pasta de QA fora da árvore do repositório.")
    root.mkdir(parents=True, exist_ok=True)
    wheels = root / "wheels"
    wheels.mkdir(exist_ok=True)
    for wheel in wheel_root(project, True).glob("*.whl"):
        shutil.copy2(wheel, wheels / wheel.name)
    shutil.copytree(
        repo,
        root / "repo",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".flatpak-builder"),
    )
    prefix = "/work" if args.minor == 12 else str(root)
    python = "python3.12" if args.minor == 12 else "python3"
    # shlex preserva espaços em caminhos do staging; nenhum argumento vem da fonte do projeto.
    import shlex

    q = shlex.quote
    venv = prefix + "/venv"
    target = venv + "/bin/python"
    script = (
        "set -eu\n"
        + python
        + " --version\n"
        + python
        + " -m venv --system-site-packages "
        + q(venv)
        + "\n"
        + q(target)
        + " -m pip --isolated install --no-index --find-links "
        + q(prefix + "/wheels")
        + " PySide6==6.11.2 pyte==0.8.2\ncd "
        + q(prefix + "/repo")
        + "\nPYTHONPATH="
        + q(prefix + "/repo/src")
        + " QT_QPA_PLATFORM=offscreen "
        + q(target)
        + " -m unittest discover -s tests -v\n"
    )
    (root / "test.sh").write_text(script)
    arguments = (
        command(["sh", "/work/test.sh"], root)
        if args.minor == 12
        else [
            "flatpak",
            "run",
            "--unshare=network",
            "--nofilesystem=host",
            "--filesystem=" + str(root),
            "--command=sh",
            "org.gnome.Sdk//50",
            str(root / "test.sh"),
        ]
    )
    with (root / "tests.log").open("w") as log:
        subprocess.run(arguments, stdout=log, stderr=subprocess.STDOUT, check=True)
    print("Regressões concluídas em Python3." + str(args.minor), flush=True)


if __name__ == "__main__":
    main()
