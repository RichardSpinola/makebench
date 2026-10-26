# SPDX-License-Identifier: MIT
"""Portable SDK and dependencies; explicit online preparation and isolated offline assembly."""

from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import uuid
from .build_environment import (
    cache_root,
    run_tool,
    download,
    APPIMAGE_URL,
    APPIMAGE_SHA,
    RUNTIME_URL,
    RUNTIME_SHA,
)
from .project import ProjectError
from makebench.terminal.environment import external_environment
from makebench.i18n import tr

IMAGE = "localhost/makebench-portable:ubuntu24.04-v1"
# The effective digest and apt list are recorded in the image and the preparation receipt.
CONTAINERFILE = """FROM docker.io/library/ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3.12 python3.12-venv python3-pip python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 libgtk-4-bin librsvg2-common libxshmfence1 adwaita-icon-theme hicolor-icon-theme fonts-dejavu-core ca-certificates dpkg-dev rpm file binutils squashfs-tools libegl1 libgl1 libglib2.0-0t64 libdbus-1-3 libnss3 libnspr4 libx11-6 libx11-xcb1 libxext6 libxfixes3 libxi6 libxrender1 libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-shm0 libxcb-sync1 libxcb-xfixes0 libxcb-xkb1 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libfreetype6 libasound2t64 libatk1.0-0t64 libatk-bridge2.0-0t64 libatspi2.0-0t64 libcups2t64 libdrm2 libgbm1 libxcomposite1 libxdamage1 libxrandr2 libxtst6 && dpkg-query -W > /opt/makebench-sdk-packages.txt && rm -rf /var/lib/apt/lists/*
COPY appimagetool.AppImage /tmp/appimagetool.AppImage
RUN chmod +x /tmp/appimagetool.AppImage && cd /tmp && ./appimagetool.AppImage --appimage-extract && mv squashfs-root /opt/appimagetool && rm appimagetool.AppImage
COPY runtime-x86_64 /opt/appimage-runtime
RUN printf '#!/bin/sh\\nexec /opt/appimagetool/AppRun --runtime-file /opt/appimage-runtime "$@"\\n' > /usr/local/bin/appimagetool && chmod +x /usr/local/bin/appimagetool
COPY payload.py /opt/makebench-payload.py
LABEL io.makebench.portable=1
"""


def sha256_file(path):
    """SHA-256 of a file read in chunks, closing it even on error."""
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def requirements(project, editor=False):
    """Resolve only declared PyPI specifications; URLs and pip options are rejected."""
    from .build_environment import flatpak_requirements

    declared = flatpak_requirements(project)
    if editor:
        declared = [package for package in declared if not package.startswith("PySide6-Essentials")]
        declared.insert(0, "PySide6==6.11.2")
        declared.extend(["jedi==0.20.1", "parso==0.8.7"])
    return sorted(set(["pyte==0.8.2", *declared]))


def wheel_root(project, editor=False):
    """The cache identifies image, Python 3.12, backend and complete requirements."""
    key = hashlib.sha256(
        json.dumps(
            [IMAGE, project.application.get("backend", "qt"), editor, requirements(project, editor)]
        ).encode()
    ).hexdigest()[:24]
    return cache_root() / "portable" / key


def ready(project, editor=False):
    """Read receipts without starting processes when the Export window opens."""
    try:
        root = wheel_root(project, editor)
        receipt = json.loads((root / "receipt.json").read_text())
        sdk = json.loads((cache_root() / "portable-sdk.json").read_text())
        return (
            sdk.get("image") == IMAGE
            and sdk.get("recipe_sha256") == hashlib.sha256(CONTAINERFILE.encode()).hexdigest()
            and receipt.get("requirements") == requirements(project, editor)
            and bool(receipt.get("files"))
        )
    except (OSError, ValueError, ProjectError):
        return False


def syntax_compatibility(source, minor=12):
    """Check the target grammar without importing or running project functions."""
    from .compatibility import syntax_error

    return syntax_error(source, minor)


def command(arguments, root, network=False, image=IMAGE):
    """Mount only the staging folder; no home, no original project and no privileges."""
    podman = shutil.which("podman")
    if not podman:
        raise ProjectError(tr("Podman is required for the isolated distribution environment."))
    root = Path(root).resolve()
    (root / ".tmp").mkdir(exist_ok=True)
    translated = [str(a).replace(str(root), "/work") for a in arguments]
    return [
        podman,
        "run",
        "--rm",
        "--name",
        "makebench-portable-" + uuid.uuid4().hex,
        "--pull=never",
        "--network=" + ("slirp4netns" if network else "none"),
        "--read-only",
        "--cap-drop=all",
        "--security-opt=no-new-privileges",
        "--userns=keep-id",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "--env",
        "HOME=/tmp",
        "--env",
        "TMPDIR=/work/.tmp",
        "--env",
        "ARCH=x86_64",
        "--volume",
        str(root) + ":/work:rw,Z",
        "--workdir",
        "/work",
        image,
        *translated,
    ]


def prepare(project, progress=None, cancelled=None, editor=False):
    """Download SDK/wheels outside the host, without mounting any project file."""
    if platform.machine() not in {"x86_64", "amd64"}:
        raise ProjectError(tr("This release validates x86_64 builds."))
    podman = shutil.which("podman")
    if not podman:
        raise ProjectError(
            tr("Podman is required. No build package will be installed on the system.")
        )
    directory = cache_root()
    directory.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(3, tr("Prepare the portable Ubuntu 24.04 / Python 3.12 runtime"))
    existing = subprocess.run(
        [
            podman,
            "image",
            "inspect",
            "--format",
            '{{index .Config.Labels "io.makebench.recipe"}}',
            IMAGE,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        env=external_environment(podman),
    )
    if (
        existing.returncode
        or existing.stdout.strip() != hashlib.sha256(CONTAINERFILE.encode()).hexdigest()
    ):
        with tempfile.TemporaryDirectory(prefix="portable-sdk-", dir=directory) as temporary:
            context = Path(temporary)
            download(
                APPIMAGE_URL, context / "appimagetool.AppImage", APPIMAGE_SHA, progress, cancelled
            )
            download(RUNTIME_URL, context / "runtime-x86_64", RUNTIME_SHA, progress, cancelled)
            shutil.copy2(Path(__file__).parents[1] / "portable/payload.py", context / "payload.py")
            (context / "Containerfile").write_text(
                CONTAINERFILE
                + "\nLABEL io.makebench.recipe="
                + hashlib.sha256(CONTAINERFILE.encode()).hexdigest()
                + "\n"
            )
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
    image_id = subprocess.check_output(
        [podman, "image", "inspect", "--format", "{{.Id}}", IMAGE],
        text=True,
        env=external_environment(podman),
    ).strip()
    sdk_receipt = directory / ("portable-sdk-" + uuid.uuid4().hex + ".tmp")
    sdk_receipt.write_text(
        json.dumps(
            {
                "image": IMAGE,
                "image_id": image_id,
                "recipe_sha256": hashlib.sha256(CONTAINERFILE.encode()).hexdigest(),
            }
        )
    )
    sdk_receipt.replace(directory / "portable-sdk.json")
    root = wheel_root(project, editor)
    root.parent.mkdir(parents=True, exist_ok=True)
    requested = requirements(project, editor)
    if ready(project, editor):
        receipt = json.loads((root / "receipt.json").read_text())
        if all(
            (root / name).is_file() and sha256_file(root / name) == digest
            for name, digest in receipt["files"].items()
        ):
            if progress:
                progress(100, tr("Portable runtime and dependencies ready."))
            return {"status": tr("Portable runtime and dependencies ready."), "image": IMAGE}
    with tempfile.TemporaryDirectory(prefix="portable-wheels-", dir=root.parent) as temporary:
        target = Path(temporary)
        run_tool(
            command(
                [
                    "python3.12",
                    "-m",
                    "pip",
                    "--isolated",
                    "download",
                    "--only-binary=:all:",
                    "--no-cache-dir",
                    "--index-url",
                    "https://pypi.org/simple",
                    "--dest",
                    "/work",
                    *requested,
                ],
                target,
                True,
            ),
            target,
            progress,
            cancelled,
        )
        files = {p.name: sha256_file(p) for p in target.glob("*.whl")}
        if not files:
            raise ProjectError(tr("No Python wheel is available for the target."))
        (target / "receipt.json").write_text(
            json.dumps({"requirements": requested, "files": files, "image_id": image_id}, indent=2)
        )
        if root.exists():
            shutil.rmtree(root)
        target.rename(root)
    if progress:
        progress(100, tr("Portable runtime and dependencies ready."))
    return {"status": tr("Portable runtime and dependencies ready."), "image": IMAGE}


def assemble(project, appdir, progress=None, cancelled=None, editor=False):
    """Assemble the complete runtime offline; project code is only compiled, never imported."""
    if not ready(project, editor):
        raise ProjectError(tr("Prepare the portable runtime and dependencies before building."))
    appdir = Path(appdir)
    stage = appdir.parent
    wheels = stage / "wheels"
    wheels.mkdir(exist_ok=True)
    root = wheel_root(project, editor)
    receipt = json.loads((root / "receipt.json").read_text())
    for name, digest in receipt["files"].items():
        if Path(name).name != name or not name.endswith(".whl"):
            raise ProjectError(tr("Invalid wheel cache."))
        # Check the copy used in staging, not the cache, which could change later.
        target = wheels / name
        shutil.copy2(root / name, target)
        with target.open("rb") as handle:
            matches = hashlib.file_digest(handle, "sha256").hexdigest() == digest
        if not matches:
            target.unlink(missing_ok=True)
            raise ProjectError(tr("Dependency changed in the cache; prepare again."))
    helper = stage / "makebench-payload.py"
    shutil.copy2(Path(__file__).parents[1] / "portable/payload.py", helper)
    arguments = ["python3.12", str(helper), str(appdir), project.application.get("backend", "qt")]
    if editor:
        arguments.append("--editor")
    run_tool(command(arguments, stage), stage, progress, cancelled)
    package = Path(__file__).parents[1]
    shutil.copy2(package / "portable/bootstrap.py", appdir / "bootstrap.py")
    launch = """#!/bin/sh
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export MAKEBENCH_ORIGINAL_PYTHONHOME="${PYTHONHOME-}"
export MAKEBENCH_ORIGINAL_PYTHONPATH="${PYTHONPATH-}"
export MAKEBENCH_ORIGINAL_LD_LIBRARY_PATH="${LD_LIBRARY_PATH-}"
export MAKEBENCH_ORIGINAL_PATH="$PATH"
export PYTHONHOME="$HERE/usr"
export PYTHONPATH="$HERE/usr/lib/python3.12/site-packages"
export PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH="$HERE/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PATH="$HERE/usr/bin:$PATH"
exec "$HERE/usr/bin/python3.12" "$HERE/bootstrap.py" "$@"
"""
    (appdir / "AppRun").write_text(launch)
    (appdir / "AppRun").chmod(0o755)


def build_native(
    project, source, read_asset, destination, format, progress=None, cancelled=None, editor=False
):
    """Publish DEB/RPM/AppImage with the runtime included, never confusing build with installation."""
    from .packages import write_recipe
    from .exporter import BuildCancelled

    error = syntax_compatibility(source)
    if error:
        raise ProjectError(error)
    if not ready(project, editor):
        raise ProjectError(
            tr("Click Prepare tools to get the portable runtime for this application.")
        )
    destination = Path(destination).resolve()
    if destination.exists():
        raise ProjectError(tr("The destination already exists; choose another name."))

    def step(number, text):
        """Cancellation is checked before publishing the complete artifact."""
        if cancelled and cancelled():
            raise BuildCancelled(tr("Build cancelled."))
        if progress:
            progress(number, text)

    def run(arguments, root):
        """Every tool receives only the isolated staging folder, with no network."""
        return run_tool(command(arguments, root), root, progress, cancelled)

    with tempfile.TemporaryDirectory(
        prefix=".makebench-portable-", dir=destination.parent
    ) as directory:
        root = Path(directory) / "recipe"
        if editor:
            root.mkdir()
            appdir = root / "AppDir"
            app = appdir / "app"
            app.mkdir(parents=True)
            package = Path(__file__).parents[1]
            shutil.copytree(
                package, app / "makebench", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
            # The editor's "Open example" looks for examples next to the package.
            examples = package.parents[1] / "examples"
            if examples.is_dir():
                shutil.copytree(
                    examples, app / "examples", ignore=shutil.ignore_patterns("__pycache__")
                )
            (appdir / "editor-entry").touch()
            identifier = project.application["id"]
            icon = project.application["icon"]
            icon_name = identifier + Path(icon).suffix
            (root / (identifier + ".desktop")).write_text(
                "[Desktop Entry]\nType=Application\nName=Makebench\nExec=makebench\nIcon="
                + identifier
                + "\nTerminal=false\nCategories=Development;IDE;\n"
            )
            (root / icon_name).write_bytes(read_asset(icon))
            shutil.copy2(root / (identifier + ".desktop"), appdir / (identifier + ".desktop"))
            shutil.copy2(root / icon_name, appdir / icon_name)
        else:
            write_recipe(project, source, read_asset, format, root, progress, cancelled)
            appdir = root / "AppDir"
            if not appdir.exists():
                shutil.copytree(root / "app", appdir / "app")
        step(35, tr("Include Python 3.12, the backend and verified dependencies"))
        assemble(project, appdir, progress, cancelled, editor)
        identifier = project.application["id"]
        if format == "appimage":
            result = root / "application.AppImage"
            run(["appimagetool", "--no-appstream", str(appdir), str(result)], root)
            with result.open("rb") as binary:
                signature = binary.read(4)
            if signature != b"\x7fELF":
                raise ProjectError(tr("The AppImage is not a valid ELF executable."))
            result.chmod(0o755)
        else:
            location = root / "payload/opt" / identifier
            shutil.rmtree(location)
            shutil.copytree(appdir, location, symlinks=True)
            binary = root / "payload/usr/bin" / identifier
            binary.write_text(
                "#!/bin/sh\nexec "
                + __import__("shlex").quote("/opt/" + identifier + "/AppRun")
                + ' "$@"\n'
            )
            binary.chmod(0o755)
            if format == "deb":
                result = root / "application.deb"
                run(
                    [
                        "dpkg-deb",
                        "--build",
                        "--root-owner-group",
                        str(root / "payload"),
                        str(result),
                    ],
                    root,
                )
                run(["dpkg-deb", "--info", str(result)], root)
            else:
                for name in ("BUILD", "RPMS", "SOURCES", "SPECS", "SRPMS"):
                    (root / name).mkdir(exist_ok=True)
                shutil.copytree(root / "payload", root / "SOURCES/payload", symlinks=True)
                run(
                    [
                        "rpmbuild",
                        "--define",
                        "_topdir " + str(root),
                        "--define",
                        "_build_id_links none",
                        "--define",
                        "__os_install_post %{nil}",
                        "-bb",
                        str(root / "app.spec"),
                    ],
                    root,
                )
                results = list((root / "RPMS").rglob("*.rpm"))
                if len(results) != 1:
                    raise ProjectError(tr("The build did not produce exactly one RPM."))
                result = results[0]
        step(95, tr("Finish package with the runtime included"))
        os.link(result, destination)
    return {
        "path": str(destination),
        "size": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "format": format,
        "status": tr(
            "Built with the runtime included (installation on the target not validated yet)"
        ),
    }


def editor_project():
    """Metadata of the editor itself, used when building the editor AppImage."""
    from .project import Project

    project = Project.empty("Makebench")
    project.application = {
        "id": "org.makebench.editor",
        "name": "Makebench",
        "version": "0.7.0",
        "backend": "qt",
        "icon": "assets/editor.svg",
        "license": "GPL-3.0-or-later",
        "description": "Visual editor for Linux applications with Qt, GTK and Python",
    }
    return project


def build_editor_appimage(destination, progress=None, cancelled=None):
    """Build the editor itself with QtWebEngine and GTK included, without publishing a release."""
    project = editor_project()
    icon = (Path(__file__).resolve().parent.parent / "editor/makebench.svg").read_bytes()
    return build_native(
        project, "", lambda _: icon, destination, "appimage", progress, cancelled, editor=True
    )
