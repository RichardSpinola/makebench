# SPDX-License-Identifier: MIT
"""Version history for a project folder, kept in Git, without any Qt.

Git is opt-in: nothing here creates a repository unless `init` is called. The
functions never run project code, never use a shell, never read or store
passwords (`GIT_TERMINAL_PROMPT=0`) and never touch the user's global Git
configuration. Restoring a version never discards anything: it writes the files
of that version and records a new version on top.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from makebench.i18n import tr
from makebench.terminal.environment import external_environment

IGNORE_LINES = [
    "# Created by Makebench: files that are rebuilt or only useful on this computer.",
    "*.bak-v*",
    "*.tmp",
    "*.swp",
    "__pycache__/",
    "*.pyc",
    ".makebench-recovery*",
    "build/",
    "dist/",
    ".venv/",
]
TAG_PREFIX = "makebench/"
FALLBACK_IDENTITY = ("Makebench", "makebench@localhost")
MAIN_TIMEOUT = 60
NETWORK_TIMEOUT = 300


class VcsError(Exception):
    """A Git operation failed; the message is written for the user."""


@dataclass
class Version:
    """One saved point of the history."""

    rev: str
    time: int
    subject: str
    names: list[str] = field(default_factory=list)

    @property
    def short(self) -> str:
        """Short identifier for display."""
        return self.rev[:7]


def available() -> bool:
    """True when the `git` program can be found."""
    return shutil.which("git") is not None


def _run(root, args, *, timeout=MAIN_TIMEOUT, identity=False, check=True, extra_env=None):
    """Run git in `root` with a fixed, non-interactive environment."""
    if not available():
        raise VcsError(tr("Git is not installed on this computer."))
    command = ["git", "-c", "core.quotepath=off"]
    if identity:
        if not _get(root, "user.name"):
            command += ["-c", f"user.name={FALLBACK_IDENTITY[0]}"]
        if not _get(root, "user.email"):
            command += ["-c", f"user.email={FALLBACK_IDENTITY[1]}"]
    command += list(args)
    environment = external_environment("git")
    environment.update({"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "GIT_PAGER": "cat"})
    environment.update(extra_env or {})
    try:
        result = subprocess.run(
            command,
            cwd=str(root),
            env=environment,
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise VcsError(tr("Git took too long and was stopped.")) from exc
    except OSError as exc:
        raise VcsError(str(exc)) from exc
    text = result.stdout.decode("utf-8", "replace")
    if check and result.returncode != 0:
        raise VcsError(_friendly(result.stderr.decode("utf-8", "replace") or text))
    return result.returncode, text


def _get(root, key) -> str:
    """Read a config value ('' when unset)."""
    if not available():
        return ""
    try:
        environment = external_environment("git")
        result = subprocess.run(
            ["git", "config", "--get", key],
            cwd=str(root),
            env=environment,
            capture_output=True,
            timeout=MAIN_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.decode("utf-8", "replace").strip() if result.returncode == 0 else ""


def _friendly(message: str) -> str:
    """Turn the usual Git failures into messages a person can act on."""
    text = message.strip()
    lowered = text.lower()
    if "could not read username" in lowered or "authentication failed" in lowered:
        return tr(
            "The service refused the login. Sign in with the system first (for example `gh auth login`, or add an SSH key), then try again."
        )
    if "permission denied (publickey)" in lowered:
        return tr(
            "The service did not accept your SSH key. Add the key to your account and try again."
        )
    if "could not resolve host" in lowered or "unable to access" in lowered:
        return tr("Could not reach the service. Check your connection and the address.")
    if "non-fast-forward" in lowered or "rejected" in lowered and "fetch first" in lowered:
        return tr("The online copy has newer versions. Fetch them first, then send again.")
    if "not possible to fast-forward" in lowered or "diverging" in lowered:
        return tr(
            "The online copy and this one both have new versions, so they cannot be joined automatically."
        )
    return text or tr("Git reported an error.")


def is_repo(root) -> bool:
    """True when `root` is itself the top of a Git repository."""
    root = Path(root)
    if not available() or not root.is_dir():
        return False
    try:
        code, out = _run(root, ["rev-parse", "--show-toplevel"], check=False)
    except VcsError:
        return False
    return code == 0 and Path(out.strip()).resolve() == root.resolve()


def has_commits(root) -> bool:
    """True when the repository has at least one version."""
    try:
        return _run(root, ["rev-parse", "--verify", "-q", "HEAD"], check=False)[0] == 0
    except VcsError:
        return False


def init(root) -> None:
    """Start the history of a project folder (explicit user action only)."""
    root = Path(root)
    if not is_repo(root):
        _run(root, ["init", "-q"])
    ensure_ignore(root)


def ensure_ignore(root) -> None:
    """Add Makebench's lines to `.gitignore` without touching the user's own lines."""
    path = Path(root) / ".gitignore"
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    have = set(current.splitlines())
    missing = [line for line in IGNORE_LINES if line not in have]
    if not missing:
        return
    if current and not current.endswith("\n"):
        current += "\n"
    path.write_text(current + "\n".join(missing) + "\n", encoding="utf-8")


def identity(root) -> tuple[str, str]:
    """The name and e-mail Git would use ('' when missing)."""
    return _get(root, "user.name"), _get(root, "user.email")


def set_identity(root, name: str, email: str, *, local: bool = True) -> None:
    """Set the identity for this project only (or, on request, for the user)."""
    if not name.strip() or "@" not in email:
        raise VcsError(tr("Enter a name and a valid e-mail."))
    scope = "--local" if local else "--global"
    _run(root, ["config", scope, "user.name", name.strip()])
    _run(root, ["config", scope, "user.email", email.strip()])


def commit_all(root, message: str) -> str | None:
    """Record the current files as a new version; None when nothing changed."""
    _run(root, ["add", "-A"])
    code, _ = _run(root, ["diff", "--cached", "--quiet"], check=False)
    if code == 0 and has_commits(root):
        return None
    _run(root, ["commit", "-q", "--allow-empty-message", "-m", message], identity=True)
    return head(root)


def head(root) -> str:
    """The identifier of the newest version."""
    return _run(root, ["rev-parse", "HEAD"])[1].strip()


def log(root, limit: int = 200) -> list[Version]:
    """The versions of the current branch, newest first, with their given names."""
    if not has_commits(root):
        return []
    _, out = _run(root, ["log", f"-{limit}", "--format=%H%x1f%ct%x1f%s"])
    names: dict[str, list[str]] = {}
    _, tags = _run(
        root,
        [
            "for-each-ref",
            f"refs/tags/{TAG_PREFIX}",
            "--format=%(objectname)%1f%(*objectname)%1f%(contents:subject)",
        ],
    )
    for line in tags.splitlines():
        direct, target, subject = (line.split("\x1f") + ["", "", ""])[:3]
        names.setdefault(target or direct, []).append(subject)
    versions = []
    for line in out.splitlines():
        rev, stamp, subject = (line.split("\x1f") + ["", "", ""])[:3]
        versions.append(Version(rev, int(stamp or 0), subject, names.get(rev, [])))
    return versions


def label(root, rev: str, name: str) -> None:
    """Give a version a name the person chose (an annotated tag)."""
    name = " ".join(name.split())
    if not name:
        raise VcsError(tr("Enter a name for this version."))
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "version"
    tag = f"{TAG_PREFIX}{slug}-{rev[:7]}"
    _run(root, ["tag", "-f", "-a", "-m", name, tag, rev], identity=True)


def read_file(root, rev: str, path: str) -> bytes | None:
    """The bytes a file had in a version, or None if it did not exist."""
    if not available():
        return None
    result = subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        cwd=str(root),
        env=external_environment("git"),
        capture_output=True,
        timeout=MAIN_TIMEOUT,
        stdin=subprocess.DEVNULL,
    )
    return result.stdout if result.returncode == 0 else None


def changed_files(root, rev: str) -> list[tuple[str, str]]:
    """(status, path) pairs that a version changed from its parent."""
    _, out = _run(root, ["show", "--format=", "--name-status", rev])
    pairs = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            pairs.append((parts[0][:1], parts[-1]))
    return pairs


def _count(component: dict) -> int:
    return 1 + sum(_count(child) for child in component.get("children", []))


def _measure(data: dict) -> dict:
    windows = [data.get("ui")] if data.get("ui") else []
    windows += data.get("windows", [])
    return {
        "windows": len(windows),
        "components": sum(_count(window) for window in windows if isinstance(window, dict)),
        "flows": len(data.get("workflows", [])),
    }


def describe(root, rev: str) -> str:
    """A short, readable line about what a version changed."""
    parts = []
    files = changed_files(root, rev)
    project_files = [p for _, p in files if p.endswith(".makebench.json")]
    for name in project_files:
        new = read_file(root, rev, name)
        old = read_file(root, f"{rev}~1", name)
        try:
            after = _measure(json.loads(new)) if new else None
            before = _measure(json.loads(old)) if old else None
        except ValueError:
            continue
        if after is None:
            continue
        if before is None:
            parts.append(tr("Project created"))
            continue
        for key, singular in (
            ("windows", tr("windows")),
            ("components", tr("components")),
            ("flows", tr("logic flows")),
        ):
            delta = after[key] - before[key]
            if delta:
                parts.append(f"{delta:+d} {singular}")
        if not parts:
            parts.append(tr("Project changed"))
    others = [p for _, p in files if not p.endswith(".makebench.json") and p != ".gitignore"]
    python = [p for p in others if p.endswith(".py")]
    if python:
        parts.append(", ".join(python[:3]) + ("…" if len(python) > 3 else ""))
    extra = len(others) - len(python)
    if extra > 0:
        parts.append(tr("{count} other files").format(count=extra))
    return "; ".join(parts) or tr("No visible changes")


def restore(root, rev: str) -> str | None:
    """Make the folder match a version, then record that as a new version.

    Files the version did not have are removed (they stay in older versions);
    nothing is reset or cleaned, so every earlier version remains reachable.
    """
    current = commit_all(root, tr("Before restoring"))
    del current
    _, out = _run(root, ["diff", "--name-status", "--no-renames", rev, "HEAD"])
    for line in out.splitlines():
        status, _, path = line.partition("\t")
        if status == "A":
            target = Path(root) / path
            if target.is_file():
                target.unlink()
    _run(root, ["checkout", rev, "--", "."])
    short = rev[:7]
    return commit_all(root, tr("Restored version {short}").format(short=short))


def remotes(root) -> dict[str, str]:
    """Configured remotes as {name: url}."""
    _, out = _run(root, ["remote", "-v"])
    found = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1] == "(push)":
            found[parts[0]] = parts[1]
    return found


def set_remote(root, url: str, name: str = "origin") -> None:
    """Point `name` to a repository address, replacing an old one."""
    url = url.strip()
    if not url or any(c.isspace() for c in url) or url.startswith("-"):
        raise VcsError(
            tr("Enter the repository address, for example https://github.com/you/app.git")
        )
    if name in remotes(root):
        _run(root, ["remote", "set-url", name, url])
    else:
        _run(root, ["remote", "add", name, url])


def branch(root) -> str:
    """The current branch name."""
    return _run(root, ["symbolic-ref", "--short", "HEAD"])[1].strip()


def ahead_behind(root, name: str = "origin") -> tuple[int, int] | None:
    """(versions not yet sent, versions not yet fetched), or None if unknown."""
    code, out = _run(
        root, ["rev-list", "--left-right", "--count", f"HEAD...{name}/{branch(root)}"], check=False
    )
    if code != 0:
        return None
    ahead, behind = out.split()
    return int(ahead), int(behind)


def push(root, name: str = "origin") -> None:
    """Send the history to the remote (only when the person asks)."""
    _run(root, ["push", "-u", name, "HEAD", "--tags"], timeout=NETWORK_TIMEOUT)


def fetch(root, name: str = "origin") -> None:
    """Download new versions without changing any file."""
    _run(root, ["fetch", "--tags", name], timeout=NETWORK_TIMEOUT)


def pull(root, name: str = "origin") -> None:
    """Bring in newer versions only when this can be done without a merge."""
    _run(root, ["pull", "--ff-only", name, branch(root)], timeout=NETWORK_TIMEOUT)


def account() -> str | None:
    """Who the computer is signed in as (via `gh`), or None. Never reads a token."""
    if shutil.which("gh") is None:
        return None
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            env=external_environment("gh"),
            capture_output=True,
            timeout=20,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    login = result.stdout.decode("utf-8", "replace").strip()
    return login if result.returncode == 0 and login else None


def create_github_repo(root, name: str, private: bool = True) -> str:
    """Create an online repository with `gh` and connect it. Returns its address."""
    if shutil.which("gh") is None or account() is None:
        raise VcsError(tr("Sign in with the GitHub command line first: `gh auth login`."))
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", name):
        raise VcsError(
            tr("Use letters, numbers, dots, dashes or underscores in the repository name.")
        )
    result = subprocess.run(
        [
            "gh",
            "repo",
            "create",
            name,
            "--private" if private else "--public",
            "--source",
            ".",
            "--remote",
            "origin",
        ],
        cwd=str(root),
        env=external_environment("gh"),
        capture_output=True,
        timeout=NETWORK_TIMEOUT,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise VcsError(_friendly(result.stderr.decode("utf-8", "replace")))
    return remotes(root).get("origin", "")
