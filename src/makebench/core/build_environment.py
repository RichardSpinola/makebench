# SPDX-License-Identifier: GPL-3.0-or-later
"""Distribution tools prepared by the application, outside the main system."""

import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import tempfile
import urllib.request
import uuid
from .project import ProjectError
from .exporter import BuildCancelled
from makebench.terminal.environment import external_environment
from makebench.i18n import tr

IMAGE = "localhost/makebench-tools:1"
APPIMAGE_URL = (
    "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
)
APPIMAGE_SHA = "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
RUNTIME_URL = "https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64"
RUNTIME_SHA = "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"
CONTAINERFILE = """FROM registry.fedoraproject.org/fedora:44
RUN dnf -y install dpkg rpm-build python3 file binutils squashfs-tools && dnf clean all
COPY appimagetool.AppImage /tmp/appimagetool.AppImage
RUN chmod +x /tmp/appimagetool.AppImage && cd /tmp && ./appimagetool.AppImage --appimage-extract && mv squashfs-root /opt/appimagetool && rm appimagetool.AppImage
COPY runtime-x86_64 /opt/appimage-runtime
RUN printf '#!/bin/sh\\nexec /opt/appimagetool/AppRun --runtime-file /opt/appimage-runtime "$@"\\n' > /usr/local/bin/appimagetool && chmod +x /usr/local/bin/appimagetool
LABEL io.makebench.tools=1
"""


def cache_root():
    """Only Makebench's cache; no project is mounted during preparation."""
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "makebench" / "builders"


def prepared():
    """Read the local receipt without starting commands or blocking the interface."""
    try:
        return json.loads((cache_root() / "tools.json").read_text()).get("image") == IMAGE
    except (OSError, ValueError):
        return False


def run_tool(arguments, cwd=None, progress=None, cancelled=None):
    """Run a fixed argv with bounded logs, cancellation and process cleanup."""
    if cancelled and cancelled():
        raise BuildCancelled(tr("Operation cancelled."))
    process = subprocess.Popen(
        [str(a) for a in arguments],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=external_environment(str(arguments[0])),
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    tail = ""
    try:
        while process.poll() is None or selector.get_map():
            if cancelled and cancelled():
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise BuildCancelled(tr("Operation cancelled."))
            for key, _ in selector.select(0.1):
                data = os.read(key.fileobj.fileno(), 8192)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                text = data.decode(errors="replace")
                tail = (tail + text)[-12000:]
                if progress:
                    progress(55, text.rstrip())
        if process.returncode:
            raise ProjectError(tr("The tool did not complete the operation:") + "\n" + tail)
        return tail
    finally:
        selector.close()
        process.stdout.close()
        if Path(str(arguments[0])).name == "podman" and "--name" in arguments:
            name = arguments[arguments.index("--name") + 1]
            if name.startswith(("makebench-build-", "makebench-portable-")):
                try:
                    subprocess.run(
                        [arguments[0], "rm", "--force", name],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=15,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass


def download(url, destination, digest, progress=None, cancelled=None):
    """Fixed official versions and hashes; only publishes the complete, verified tool."""
    request = urllib.request.Request(url, headers={"User-Agent": "Makebench-tools/1"})
    hasher = hashlib.sha256()
    with (
        urllib.request.urlopen(request, timeout=30) as response,
        Path(destination).open("wb") as output,
    ):
        while data := response.read(262144):
            if cancelled and cancelled():
                raise BuildCancelled(tr("Download cancelled."))
            output.write(data)
            hasher.update(data)
    if hasher.hexdigest() != digest:
        raise ProjectError(
            tr("The hash of the downloaded tool does not match. Preparation stopped.")
        )
    if progress:
        progress(20, tr("Download verified: {name}").format(name=Path(destination).name))


def prepare_tools(progress=None, cancelled=None):
    """Prepare DEB/RPM/AppImage in rootless Podman, reusable across projects."""
    podman = shutil.which("podman")
    if not podman:
        raise ProjectError(
            tr(
                "Install Podman to prepare the tools in a separate environment, or choose the system tools."
            )
        )
    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="prepare-", dir=root) as directory:
        context = Path(directory)
        if progress:
            progress(5, tr("Preparing distribution tools. The first time requires a download."))
        existing = subprocess.run(
            [
                podman,
                "image",
                "inspect",
                "--format",
                '{{index .Config.Labels "io.makebench.tools"}}',
                IMAGE,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            env=external_environment(podman),
        )
        if existing.returncode == 0 and existing.stdout.strip() == "1":
            if progress:
                progress(80, tr("Reusing tools already prepared."))
        else:
            download(
                APPIMAGE_URL, context / "appimagetool.AppImage", APPIMAGE_SHA, progress, cancelled
            )
            download(RUNTIME_URL, context / "runtime-x86_64", RUNTIME_SHA, progress, cancelled)
            (context / "Containerfile").write_text(CONTAINERFILE)
            run_tool(
                [
                    podman,
                    "build",
                    "--pull=missing",
                    "--tag",
                    IMAGE,
                    "--file",
                    str(context / "Containerfile"),
                    str(context),
                ],
                context,
                progress,
                cancelled,
            )
        run_tool(
            [
                podman,
                "run",
                "--rm",
                "--pull=never",
                "--network=none",
                IMAGE,
                "dpkg-deb",
                "--version",
            ],
            progress=progress,
            cancelled=cancelled,
        )
        run_tool(
            [
                podman,
                "run",
                "--rm",
                "--pull=never",
                "--network=none",
                IMAGE,
                "rpmbuild",
                "--version",
            ],
            progress=progress,
            cancelled=cancelled,
        )
        temporary = root / "tools.json.tmp"
        temporary.write_text(
            json.dumps({"image": IMAGE, "appimagetool": "1.9.1", "runtime": "20251108"})
        )
        temporary.replace(root / "tools.json")
    if progress:
        progress(100, tr("DEB, RPM and AppImage tools ready."))
    return {"status": tr("DEB, RPM and AppImage tools ready."), "image": IMAGE}


def container_command(arguments, root):
    """Mount only the export staging, with no network, home folder or original projects."""
    podman = shutil.which("podman")
    if not podman or not prepared():
        raise ProjectError(tr("Click Prepare tools before building this package."))
    root = Path(root).resolve()
    translated = [str(a).replace(str(root), "/work") for a in arguments]
    return [
        podman,
        "run",
        "--rm",
        "--name",
        "makebench-build-" + uuid.uuid4().hex,
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=all",
        "--security-opt=no-new-privileges",
        "--userns=keep-id",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "--env",
        "HOME=/tmp",
        "--env",
        "ARCH=x86_64",
        "--volume",
        str(root) + ":/work:rw,Z",
        "--workdir",
        "/work",
        IMAGE,
        *translated,
    ]


def prepare_flatpak(project, progress=None, cancelled=None):
    """Install only the build SDK/runtime in the user's Flatpak scope."""
    flatpak = shutil.which("flatpak")
    if not flatpak or not shutil.which("flatpak-builder"):
        raise ProjectError(tr("Flatpak and flatpak-builder are required for this target."))
    gtk = project.application.get("backend", "qt") == "gtk"
    sdk = "org.gnome.Sdk//50" if gtk else "org.kde.Sdk//6.10"
    run_tool(
        [
            flatpak,
            "remote-add",
            "--user",
            "--if-not-exists",
            "flathub",
            "https://dl.flathub.org/repo/flathub.flatpakrepo",
        ],
        progress=progress,
        cancelled=cancelled,
    )
    run_tool(
        [flatpak, "install", "--user", "--noninteractive", "--assumeyes", "flathub", sdk],
        progress=progress,
        cancelled=cancelled,
    )
    requirements = flatpak_requirements(project)
    cached = False
    if requirements:
        root = flatpak_wheels(project)
        root.parent.mkdir(parents=True, exist_ok=True)
        try:
            receipt = json.loads((root / "receipt.json").read_text())
            files = receipt.get("files", {})
            cached = (
                receipt.get("requirements") == requirements
                and bool(files)
                and all(
                    Path(name).name == name
                    and name.endswith(".whl")
                    and hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
                    for name, digest in files.items()
                )
            )
        except (OSError, ValueError):
            pass
    if requirements and not cached:
        with tempfile.TemporaryDirectory(prefix="wheels-", dir=root.parent) as directory:
            run_tool(
                [
                    flatpak,
                    "run",
                    "--share=network",
                    "--filesystem=" + directory,
                    "--command=python3",
                    sdk,
                    "-m",
                    "pip",
                    "--isolated",
                    "download",
                    "--index-url",
                    "https://pypi.org/simple",
                    "--only-binary=:all:",
                    "--no-cache-dir",
                    "--dest",
                    directory,
                    *requirements,
                ],
                progress=progress,
                cancelled=cancelled,
            )
            downloaded = Path(directory)
            files = {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in downloaded.glob("*.whl")
            }
            if not files:
                raise ProjectError(tr("No Python wheel is available for this SDK."))
            (downloaded / "receipt.json").write_text(
                json.dumps({"requirements": requirements, "files": files})
            )
            if root.exists():
                shutil.rmtree(root)
            downloaded.rename(root)
    if cached and progress:
        progress(90, tr("Reusing verified Python dependencies from the cache."))
    if progress:
        progress(100, tr("Flatpak environment ready."))
    return {"status": tr("Flatpak environment ready."), "sdk": sdk}


def flatpak_requirements(project):
    """Only PyPI names/constraints; rejects URLs, paths and pip options."""
    import re

    packages = list(project.application.get("packages", []))
    for package in packages:
        if not isinstance(package, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:[<>=!~]=?[A-Za-z0-9.*+!_-]+(?:,[<>=!~]=?[A-Za-z0-9.*+!_-]+)*)?",
            package,
        ):
            raise ProjectError(tr("Invalid Python dependency: {name}").format(name=package))
    packages.insert(0, "pyte==0.8.2")
    if project.application.get("backend", "qt") == "qt":
        packages.insert(0, "PySide6-Essentials==6.11.2")
    return packages


def flatpak_wheels(project):
    """Cache location specific to backend, SDK and declared dependencies."""
    requirements = flatpak_requirements(project)
    gtk = project.application.get("backend", "qt") == "gtk"
    key = hashlib.sha256(
        json.dumps([gtk, "50" if gtk else "6.10", requirements]).encode()
    ).hexdigest()[:24]
    return cache_root() / "flatpak" / key


def copy_flatpak_wheels(project, destination):
    """Copy only verified wheels; building never downloads or runs Python packages."""
    if not flatpak_requirements(project):
        return
    root = flatpak_wheels(project)
    try:
        receipt = json.loads((root / "receipt.json").read_text())
    except (OSError, ValueError):
        raise ProjectError(
            tr("Prepare the Flatpak tools to download this application's Python dependencies.")
        )
    target = Path(destination)
    target.mkdir()
    for name, digest in receipt.get("files", {}).items():
        if Path(name).name != name or not name.endswith(".whl"):
            raise ProjectError(tr("Invalid dependency cache. Prepare again."))
        data = (root / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ProjectError(tr("Python dependency changed in the cache. Prepare again."))
        (target / name).write_bytes(data)
    if not list(target.glob("*.whl")):
        raise ProjectError(tr("Empty dependency cache. Prepare again."))
