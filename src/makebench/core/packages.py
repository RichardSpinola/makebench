# SPDX-License-Identifier: GPL-3.0-or-later
"""Package recipes and builds in staging, never running project code."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from .exporter import export_source, verify, effects, BuildCancelled
from .project import ProjectError
from .environment import build_tools
from makebench.i18n import tr

FORMATS = {
    "source": (tr("Python source"), None, ".zip"),
    "deb": ("DEB", "dpkg-deb", ".deb"),
    "appimage": ("AppImage", "appimagetool", ".AppImage"),
    "flatpak": ("Flatpak", "flatpak-builder", ".flatpak"),
    "rpm": ("RPM", "rpmbuild", ".rpm"),
}


def one_line(value):
    """Metadata never injects control lines, commands or desktop entries."""
    return re.sub(r"[\r\n\x00-\x1f]", " ", str(value)).strip()


def preflight(project, source, read_asset, format):
    """Include explicit tools and restrictions per target, without running builds."""
    issues = verify(project, source, read_asset)
    programs, admin = effects(project)
    for issue in issues:
        if issue["level"] == "success":
            issue["message"] = tr("Project check completed.")
    tool = FORMATS[format][1]
    from .portable import ready

    managed = format in {"deb", "rpm", "appimage"} and ready(project)
    if format in {"deb", "rpm", "appimage"} and not managed:
        issues.append(
            {
                "level": "warning",
                "message": tr(
                    "Prepare the portable runtime and dependencies in an isolated environment before building."
                ),
                "field": "destinations",
            }
        )
    elif tool and not build_tools().get(tool) and not managed:
        issues.append(
            {
                "level": "warning",
                "message": tr("Prepare the build tools ({tool}) or export the recipe.").format(
                    tool=tool
                ),
                "field": "destinations",
            }
        )
    from .compatibility import syntax_error

    minor = 13 if format == "flatpak" else 12
    if format != "source":
        error = syntax_error(source, minor)
        if error:
            issues.append({"level": "error", "message": error, "field": "python"})
    if format == "flatpak" and admin:
        issues.append(
            {
                "level": "error",
                "message": tr("Administrative actions are not available in the isolated Flatpak."),
                "field": "permissions",
            }
        )
    if format == "flatpak" and programs:
        issues.append(
            {
                "level": "warning",
                "message": tr(
                    "Tasks and the terminal run only inside the Flatpak. Host programs are not available."
                ),
                "field": "dependencies",
            }
        )
    if project.application.get("packages"):
        issues.append(
            {
                "level": "warning",
                "message": tr(
                    "The declared Python dependencies will be resolved in the isolated environment during Prepare tools."
                ),
                "field": "packages",
            }
        )
    return issues


def policy_xml(project):
    """Declare that authentication is needed without granting automatic permission.

    Never binds a generic executable to an ID that would allow elevating any
    argument without confirmation. pkexec uses its default authentication policy.
    """
    app = project.application
    root = ET.Element("policyconfig")
    action = ET.SubElement(root, "action", id=app["id"] + ".admin")
    ET.SubElement(action, "description").text = tr("Administrative action of {name}").format(
        name=app["name"]
    )
    ET.SubElement(action, "message").text = tr(
        "Authorize the administrative action requested by the application."
    )
    defaults = ET.SubElement(action, "defaults")
    for tag, value in [
        ("allow_any", "no"),
        ("allow_inactive", "no"),
        ("allow_active", "auth_admin"),
    ]:
        ET.SubElement(defaults, tag).text = value
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def write_recipe(project, source, read_asset, format, root, progress=None, cancelled=None):
    """Generate complete entries; having a recipe never means a ready package."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    app = project.application
    identifier = app["id"]
    name = one_line(app["name"])
    version = app["version"]
    gtk = app.get("backend", "qt") == "gtk"
    programs, admin = effects(project)
    export_source(project, source, read_asset, root / "source.zip", progress, cancelled)
    with zipfile.ZipFile(root / "source.zip") as z:
        z.extractall(root / "app")
    icon_ext = Path(app["icon"]).suffix
    icon_name = identifier + icon_ext
    desktop = f"[Desktop Entry]\nType=Application\nName={name}\nComment={one_line(app.get('description', ''))}\nExec={identifier}\nIcon={identifier}\nTerminal=false\nCategories={one_line(app.get('category', 'Utility')).rstrip(';')};\n"
    icon_data = read_asset(app["icon"])
    if icon_ext.lower() == ".svg":
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        svg = ET.fromstring(icon_data)
        # AppStream needs the viewBox to rasterize SVG icons without distortion.
        if "viewBox" not in svg.attrib:
            dimensions = [
                re.fullmatch(r"([0-9.]+)(?:px)?", svg.get(axis, "")) for axis in ("width", "height")
            ]
            if all(dimensions):
                svg.set("viewBox", "0 0 " + " ".join(d.group(1) for d in dimensions))
                icon_data = ET.tostring(svg, encoding="utf-8")
    (root / (identifier + ".desktop")).write_text(desktop, encoding="utf-8")
    (root / icon_name).write_bytes(icon_data)
    if admin:
        (root / (identifier + ".policy")).write_text(policy_xml(project), encoding="utf-8")
    payload = root / "payload"
    location = payload / "opt" / identifier
    location.mkdir(parents=True)
    shutil.copytree(root / "app", location, dirs_exist_ok=True)
    binary = payload / "usr/bin" / identifier
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(
        '#!/bin/sh\necho "'
        + tr("Runtime not assembled yet. Use build-recipe.py.")
        + '" >&2\nexit 1\n'
    )
    binary.chmod(0o755)
    for target, origin in [
        (
            payload / "usr/share/applications" / (identifier + ".desktop"),
            root / (identifier + ".desktop"),
        ),
        (
            payload
            / "usr/share/icons/hicolor"
            / ("scalable" if icon_ext == ".svg" else "256x256")
            / "apps"
            / icon_name,
            root / icon_name,
        ),
    ]:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)
    if admin:
        target = payload / "usr/share/polkit-1/actions" / (identifier + ".policy")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / (identifier + ".policy"), target)
    if format == "deb":
        control = payload / "DEBIAN"
        control.mkdir()
        deps = "libc6 (>= 2.39), libgl1, libegl1"
        if admin:
            deps += ", policykit-1"
        text = f"Package: {identifier.replace('_', '-')}\nVersion: {version}\nSection: utils\nPriority: optional\nArchitecture: amd64\nMaintainer: {one_line(app.get('author') or tr('Author not specified'))}\nDepends: {deps}\nDescription: {one_line(app.get('description') or name)}\n"
        (control / "control").write_text(text, encoding="utf-8")
        # Python/backend and wheels are added to the payload by the isolated environment.
    elif format == "rpm":
        spec = f"Name: {identifier.replace('_', '-')}\nVersion: {version.split('-')[0].split('+')[0]}\nRelease: 1%{{?dist}}\nSummary: {one_line(app.get('description') or name)}\nLicense: {one_line(app.get('license') or 'LicenseRef-unspecified')}\nBuildArch: x86_64\nAutoReqProv: no\nRequires: glibc >= 2.39\nRequires: libGL.so.1()(64bit), libEGL.so.1()(64bit)\n"
        spec += "%global debug_package %{nil}\n"
        if admin:
            spec += "Requires: polkit\n"
        spec += (
            "\n%description\n"
            + one_line(app.get("description") or name)
            + "\n\n%install\nmkdir -p %{buildroot}\ncp -a %{_sourcedir}/payload/. %{buildroot}/\n\n%files\n/opt/"
            + identifier
            + "\n/usr/bin/"
            + identifier
            + "\n/usr/share/applications/"
            + identifier
            + ".desktop\n/usr/share/icons/hicolor/*/apps/"
            + icon_name
            + "\n"
        )
        if admin:
            spec += "/usr/share/polkit-1/actions/" + identifier + ".policy\n"
        # Template macros are controlled; free text cannot add macros.
        for raw in (
            one_line(app.get("description") or name),
            one_line(app.get("license") or "LicenseRef-unspecified"),
        ):
            if "%" in raw:
                raise ProjectError(
                    tr(
                        "Remove % from the metadata before generating an RPM; macros are not accepted in free text."
                    )
                )
        (root / "app.spec").write_text(spec, encoding="utf-8")
    elif format == "appimage":
        appdir = root / "AppDir"
        shutil.copytree(root / "app", appdir / "app")
        shutil.copy2(root / (identifier + ".desktop"), appdir / (identifier + ".desktop"))
        shutil.copy2(root / icon_name, appdir / icon_name)
        launcher = appdir / "AppRun"
        launcher.write_text(
            '#!/bin/sh\necho "'
            + tr("Runtime not assembled yet. Build this recipe with Makebench.")
            + '" >&2\nexit 1\n'
        )
        launcher.chmod(0o755)
        (root / "DEPENDENCIES.txt").write_text(
            tr(
                "The isolated build includes Python 3.12, the backend and the declared dependencies. Linux x86_64 with glibc 2.39+, X11/Wayland and the system drivers. FUSE or --appimage-extract-and-run. External programs used by the project remain explicit requirements.\n"
            ),
            encoding="utf-8",
        )
    elif format == "flatpak":
        runtime = "org.gnome.Platform" if gtk else "org.kde.Platform"
        sdk = "org.gnome.Sdk" if gtk else "org.kde.Sdk"
        manifest = {
            "app-id": identifier,
            "runtime": runtime,
            "runtime-version": "50" if gtk else "6.10",
            "sdk": sdk,
            "command": identifier,
            "finish-args": [
                "--socket=wayland",
                "--socket=fallback-x11",
                "--share=ipc",
                "--device=dri",
            ]
            + ([] if gtk else ["--env=QT_QPA_PLATFORM=wayland;xcb"]),
            "modules": [
                {
                    "name": "application",
                    "buildsystem": "simple",
                    "build-commands": [
                        "mkdir -p /app/share/" + identifier,
                        "cp -a app/. /app/share/" + identifier + "/",
                        "install -Dm755 flatpak-launcher /app/bin/" + identifier,
                        "install -Dm644 "
                        + identifier
                        + ".desktop /app/share/applications/"
                        + identifier
                        + ".desktop",
                        "install -Dm644 "
                        + icon_name
                        + " /app/share/icons/hicolor/"
                        + ("scalable" if icon_ext == ".svg" else "256x256")
                        + "/apps/"
                        + icon_name,
                        "install -Dm644 "
                        + identifier
                        + ".metainfo.xml /app/share/metainfo/"
                        + identifier
                        + ".metainfo.xml",
                    ],
                    "sources": [
                        {
                            "type": "dir",
                            "path": ".",
                            "skip": ["payload", "repo", "build-dir", "AppDir"],
                        }
                    ],
                }
            ],
        }
        (root / (identifier + ".json")).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (root / "flatpak-launcher").write_text(
            "#!/bin/sh\nexec python3 /app/share/" + identifier + '/run.py "$@"\n'
        )
        (root / "flatpak-launcher").chmod(0o755)
        metadata = ET.Element("component", type="desktop-application")
        for tag, value in [
            ("id", identifier),
            ("metadata_license", "CC0-1.0"),
            ("project_license", app.get("license") or "LicenseRef-unspecified"),
            ("name", name),
            ("summary", one_line(app.get("description") or name)[:100]),
        ]:
            ET.SubElement(metadata, tag).text = value
        ET.SubElement(metadata, "launchable", type="desktop-id").text = identifier + ".desktop"
        description = ET.SubElement(metadata, "description")
        ET.SubElement(description, "p").text = one_line(app.get("description") or name)
        (root / (identifier + ".metainfo.xml")).write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(metadata, encoding="unicode"),
            encoding="utf-8",
        )
    (root / "PACKAGE-README.txt").write_text(
        tr(
            "{format} recipe generated by Makebench. Generating does not mean building or validating installation.\nNative runtime included: Python 3.12, the backend and the declared Python dependencies. Targets: Ubuntu 24.04/Fedora 44 x86_64, glibc 2.39+.\nNo project source was run. Prepare tools resolves dependencies in an isolated environment; building uses a verified cache.\nThe Polkit policy grants no automatic access; pkexec keeps the system's default authentication.\n"
        ).format(format=FORMATS[format][0]),
        encoding="utf-8",
    )
    (root / "build-recipe.py").write_text(
        """#!/usr/bin/env python3
from pathlib import Path
import argparse
import sys
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'app'))
from makebench.core.storage import load_project
from makebench.core.source import SourceBuffer
from makebench.core.packages import build_package
from makebench.core.portable import prepare
from makebench.core.build_environment import prepare_flatpak
parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
project=load_project(root/'app/project.makebench.json');source=SourceBuffer.load(root/'app/project.makebench.json').text
format="""
        + repr(format)
        + """
if args.prepare:
    (prepare_flatpak if format=='flatpak' else prepare)(project,lambda n,t:print(t,flush=True))
print(build_package(project,source,lambda name:(root/'app'/name).read_bytes(),args.output,format,lambda n,t:print(t,flush=True)))
""",
        encoding="utf-8",
    )
    return root


def build_package(
    project,
    source,
    read_asset,
    destination,
    format,
    progress=None,
    cancelled=None,
    recipe_only=False,
    environment="system",
):
    """Build with available tools; publish exclusively after finishing and verifying."""
    if format in {"deb", "rpm", "appimage"} and not recipe_only:
        issues = preflight(project, source, read_asset, format)
        errors = [item["message"] for item in issues if item["level"] == "error"]
        if errors:
            raise ProjectError("\n".join(errors))
        from .portable import build_native

        return build_native(project, source, read_asset, destination, format, progress, cancelled)
    if format == "source":
        return dict(
            export_source(project, source, read_asset, destination, progress, cancelled),
            status=tr("Built and verified"),
            format=format,
        )
    issues = preflight(project, source, read_asset, format)
    errors = [i["message"] for i in issues if i["level"] == "error"]
    if errors:
        raise ProjectError("\n".join(errors))
    destination = Path(destination).resolve()
    if destination.exists():
        raise ProjectError(tr("The destination already exists. Choose another name."))
    tool = FORMATS[format][1]
    available = build_tools().get(tool)
    from .build_environment import run_tool

    if not available and not recipe_only:
        raise ProjectError(tr("Prepare the tools or choose Generate recipe only."))
    recipe = recipe_only

    def step(number, message):
        """Cancellation happens before publishing any artifact to the destination."""
        if cancelled and cancelled():
            raise BuildCancelled(tr("Build cancelled."))
        if progress:
            progress(number, message)

    def run(arguments, cwd):
        """Explicit tool, no shell; logs and cancellation of the build tree."""
        step(50, tr("Run {tool}").format(tool=Path(arguments[0]).name))
        return run_tool(arguments, cwd, progress, cancelled)

    with ExitStack() as stack:
        directory = stack.enter_context(
            tempfile.TemporaryDirectory(prefix=".makebench-package-", dir=destination.parent)
        )
        # AppStream uses limited IPC paths; keep the Flatpak build path short.
        build_directory = (
            stack.enter_context(tempfile.TemporaryDirectory(prefix="mb-flatpak-"))
            if format == "flatpak"
            else directory
        )
        root = write_recipe(
            project,
            source,
            read_asset,
            format,
            Path(build_directory) / "recipe",
            progress,
            cancelled,
        )
        step(35, tr("Recipe generated"))
        if recipe:
            result = Path(directory) / "recipe.zip"
            with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as z:
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        z.write(path, path.relative_to(root))
            status = tr("Generated, not built ({reason})").format(
                reason=tr("recipe requested")
                if available
                else tr("missing {tool}").format(tool=tool)
            )
        else:
            identifier = project.application["id"]
            from .build_environment import copy_flatpak_wheels, flatpak_requirements

            if flatpak_requirements(project):
                copy_flatpak_wheels(project, root / "wheels")
                manifest_path = root / (identifier + ".json")
                manifest = json.loads(manifest_path.read_text())
                manifest["modules"][0]["build-commands"].insert(
                    0,
                    "python3 -m pip install --no-index --no-deps --target=/app/lib/python/site-packages wheels/*.whl",
                )
                manifest["finish-args"].append("--env=PYTHONPATH=/app/lib/python/site-packages")
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
            if shutil.which("appstreamcli"):
                run(
                    [
                        shutil.which("appstreamcli"),
                        "validate",
                        "--no-net",
                        "--override=url-homepage-missing=info",
                        str(root / (identifier + ".metainfo.xml")),
                    ],
                    root,
                )
            repo = Path(build_directory) / "repo"
            builddir = Path(build_directory) / "build-dir"
            run(
                [
                    available,
                    "--user",
                    "--disable-download",
                    "--force-clean",
                    "--repo=" + str(repo),
                    str(builddir),
                    str(root / (identifier + ".json")),
                ],
                root,
            )
            flatpak = shutil.which("flatpak")
            if not flatpak:
                raise ProjectError(tr("flatpak is missing to generate the final bundle."))
            result = Path(directory) / "app.flatpak"
            run(
                [
                    flatpak,
                    "build-bundle",
                    "--runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo",
                    str(repo),
                    str(result),
                    identifier,
                ],
                root,
            )
            status = tr("Built and verified (installation on the target not tested yet)")
        step(95, tr("Publish complete result"))
        if format == "flatpak" and not recipe:
            staged = Path(directory) / "bundle.flatpak"
            shutil.copy2(result, staged)
            result = staged
        os.link(result, destination)
    return {
        "path": str(destination),
        "size": destination.stat().st_size,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "status": status,
        "format": format,
    }
