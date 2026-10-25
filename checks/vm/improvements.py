# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate the modules/Designer delivery on the already prepared disposable VMs."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from machine import Machine


def main():
    """One VM at a time; wait for the atomic publication of artifacts and shut down at the end."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=("ubuntu", "fedora"), required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--editor", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    machine = Machine(args.root)
    machine.resume()
    cases = []
    validate = Path(__file__).with_name("validate.py")

    def run(backend, format, artifact, project=None, quick=False):
        """Read only complete artifacts; keep logs and results of each installation."""
        deadline = time.monotonic() + 600
        if not artifact.exists():
            print("Waiting for build:", artifact.name, flush=True)
        while not artifact.exists():
            if time.monotonic() > deadline:
                raise RuntimeError("Artifact did not become ready: " + str(artifact))
            time.sleep(1)
        target = args.output / (args.system + "-" + backend + "-" + format)
        command = [
            sys.executable,
            str(validate),
            str(args.root),
            str(artifact),
            "--format",
            format,
            "--backend",
            backend,
            "--output",
            str(target),
        ]
        if project:
            command += ["--project-dir", str(project)]
        if quick:
            command += ["--quick-close"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.with_suffix(".log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
        data = json.loads((target / "results.json").read_text())
        cases.append(data)
        print("OK", args.system, backend, format, flush=True)

    try:
        for backend in ("qt", "gtk"):
            run(
                backend,
                "editor",
                args.editor,
                args.fixtures / ("vm-editor-modules-" + backend),
                quick=backend == "gtk",
            )
        native = "deb" if args.system == "ubuntu" else "rpm"
        for backend in ("qt", "gtk"):
            for format, suffix in [
                (native, native),
                ("appimage", "AppImage"),
                ("flatpak", "flatpak"),
            ]:
                run(backend, format, args.packages / (backend + "." + suffix))
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / (args.system + "-results.json")).write_text(
            json.dumps(cases, ensure_ascii=False, indent=2)
        )
    finally:
        machine.stop()


if __name__ == "__main__":
    main()
