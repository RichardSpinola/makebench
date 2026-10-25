# SPDX-License-Identifier: GPL-3.0-or-later
"""Regressions on isolated Python 3.12/3.13, using only already prepared wheels."""

import argparse
from pathlib import Path
import shutil
import subprocess
from makebench.core.portable import command, editor_project, ready, wheel_root


def main():
    """Installs nothing on the host: private SDK, venv in staging and the full suite copied."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--minor", choices=(12, 13), type=int, required=True)
    args = parser.parse_args()
    project = editor_project()
    if not ready(project, True):
        raise RuntimeError("Prepare the editor runtime in Export before this test.")
    root = args.output.resolve()
    repo = Path(__file__).resolve().parents[1]
    if root.is_relative_to(repo):
        raise RuntimeError("Use a QA folder outside the repository tree.")
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
    # shlex keeps spaces in staging paths; no argument comes from the project source.
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
    print("Regressions finished on Python 3." + str(args.minor), flush=True)


if __name__ == "__main__":
    main()
