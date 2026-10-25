# SPDX-License-Identifier: MIT
"""Minimal PTY helper, started by subprocess with no callbacks after fork."""

import fcntl
import os
from pathlib import Path
import runpy
import sys
import termios


def main():
    """Take the PTY as the new session's controlling terminal and replace the helper."""
    try:
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        os.tcsetpgrp(0, os.getpgrp())
        helper = runpy.run_path(str(Path(__file__).with_name("environment.py")))
        environment = helper["external_environment"](sys.argv[1])
        os.execvpe(sys.argv[1], sys.argv[1:], environment)
    except BaseException as exc:
        os.write(2, (str(exc) + "\r\n").encode("utf-8", "replace"))
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
