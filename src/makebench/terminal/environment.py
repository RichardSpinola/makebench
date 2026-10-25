# SPDX-License-Identifier: MIT
"""Environment for external processes of relocatable packages, shared by Qt/GTK."""

import json
import os
from pathlib import Path
import shutil


def external_environment(program, base=None):
    """Keep bundled libraries only for the package's own executables.

    System programs must not receive PYTHONHOME, Qt/GTK plugins or libraries from
    another distribution. PATH keeps the package helpers, including the Python 3
    launcher, which sets up its own environment when called.
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
    # The package's python3 is a launcher that sets up its runtime separately.
    environment["PATH"] = str(Path(root) / "usr/bin") + ":" + (original.get("PATH") or os.defpath)
    return environment
