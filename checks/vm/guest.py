"""Install, open, run, capture and remove an artifact inside the disposable VM."""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import tempfile


def run(arguments, **kwargs):
    """Install/test failures are recorded, never turned into success."""
    print("+", *arguments, flush=True)
    return subprocess.run(arguments, check=True, **kwargs)


def main():
    """This routine belongs to the guest; it must not be called on the user's desktop."""
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--format", choices=("deb", "rpm", "appimage", "flatpak", "editor"), required=True
    )
    parser.add_argument("--backend", choices=("qt", "gtk"), default="qt")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--quick-close", action="store_true")
    args = parser.parse_args()
    if not Path("/etc/hostname").read_text().strip().startswith("makebench-"):
        raise RuntimeError("Run only in the registered disposable VM.")
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return run(["dbus-run-session", "--", sys.executable, __file__, *sys.argv[1:]]).returncode
    artifact = args.artifact.resolve()
    output = args.output.resolve()
    if (
        output.name != "evidence"
        or output.parent != artifact.parent
        or not output.parent.name.startswith("case-")
    ):
        raise RuntimeError("Evidence folder outside the isolated case.")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    identifier = "org.makebench.qa" + args.backend
    format = args.format
    home = Path.home()
    os.environ["DISPLAY"] = ":91"
    environment = dict(
        os.environ,
        QT_QPA_PLATFORM="xcb",
        GDK_BACKEND="x11",
        GSK_RENDERER="cairo",
        LIBGL_ALWAYS_SOFTWARE="1",
    )
    # The normal Chromium sandbox is required in the editor test.
    environment.pop("QTWEBENGINE_DISABLE_SANDBOX", None)
    environment.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
    sentinel = home / "makebench-host-sentinel"
    sentinel.write_text("Guest host file, not shared with the Flatpak.")
    marker = (
        home / ".var/app" / identifier / "data/qa-result.json"
        if format == "flatpak"
        else output / "application-result.json"
    )
    if marker.exists():
        marker.unlink()
    environment["MAKEBENCH_QA_OUTPUT"] = str(marker)
    records = {
        "format": format,
        "backend": args.backend,
        "os_release": Path("/etc/os-release").read_text(),
        "architecture": os.uname().machine,
        "artifact": artifact.name,
        "steps": [],
    }
    installed = False
    process = None
    with (output / "xvfb.log").open("w") as serverlog:
        server = subprocess.Popen(
            ["Xvfb", ":91", "-screen", "0", "1280x900x24", "-nolisten", "tcp", "-ac"],
            stdout=serverlog,
            stderr=subprocess.STDOUT,
        )
    try:
        for _ in range(100):
            if Path("/tmp/.X11-unix/X91").exists():
                break
            if server.poll() is not None:
                raise RuntimeError("Xvfb did not start.")
            time.sleep(0.05)
        os.environ.update(environment)
        if format == "deb":
            run(
                [
                    "sudo",
                    "env",
                    "DEBIAN_FRONTEND=noninteractive",
                    "apt-get",
                    "install",
                    "-y",
                    str(artifact),
                ],
                timeout=600,
            )
            installed = True
            command = ["/usr/bin/" + identifier]
            run(["dpkg-query", "-W", identifier])
            records["steps"].append("Real DEB installation")
        elif format == "rpm":
            run(["sudo", "dnf", "-y", "install", str(artifact)], timeout=600)
            installed = True
            command = ["/usr/bin/" + identifier]
            run(["rpm", "-q", identifier])
            records["steps"].append("Real RPM installation")
        elif format == "flatpak":
            run(
                [
                    "flatpak",
                    "remote-add",
                    "--user",
                    "--if-not-exists",
                    "flathub",
                    "https://dl.flathub.org/repo/flathub.flatpakrepo",
                ]
            )
            run(
                ["flatpak", "install", "--user", "--noninteractive", "--assumeyes", str(artifact)],
                timeout=1200,
            )
            installed = True
            command = ["flatpak", "run", "--env=MAKEBENCH_QA_OUTPUT=" + str(marker), identifier]
            records["steps"].append("Flatpak installation and automatic runtime resolution")
        else:
            artifact.chmod(0o755)
            command = [str(artifact)]
            if format == "editor":
                with tempfile.TemporaryDirectory(
                    prefix="makebench-editor-probe-", dir=home
                ) as extracted:
                    run(
                        [str(artifact), "--appimage-extract"],
                        cwd=extracted,
                        stdout=subprocess.DEVNULL,
                        timeout=120,
                    )
                    appdir = Path(extracted) / "squashfs-root"
                    # Only the disposable copy swaps the entry point for a trusted probe;
                    # the original AppImage is opened unchanged in the graphical test below.
                    (appdir / "app/makebench/__main__.py").write_text(
                        "import runpy\ndef main():return runpy.run_path('/home/qa/editor-tools.py')['probe']()\n"
                    )
                    tools = subprocess.check_output(
                        [str(appdir / "AppRun")], env=environment, text=True, timeout=30
                    )
                    records["runtime_tools"] = json.loads(tools)
                    records["steps"].append(
                        "Host tools without private libraries and the target TLS certificates"
                    )
                if args.project:
                    command.append(str(args.project.resolve()))
            records["steps"].append(
                "Runnable AppImage, with no Python/backend installed in the guest"
            )
        with (output / "application.log").open("w") as log:
            process = subprocess.Popen(
                command,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        deadline = time.monotonic() + (35 if format == "editor" else 60)
        result = None
        visible = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    "Application exited before the check: "
                    + (output / "application.log").read_text()
                )
            windows = subprocess.run(
                [
                    "xdotool",
                    "search",
                    "--onlyvisible",
                    "--name",
                    "Makebench" if format == "editor" else "Fluxo com fios",
                ],
                capture_output=True,
                text=True,
            )
            visible = visible or windows.returncode == 0
            if format == "editor" and visible:
                time.sleep(0.1 if args.quick_close else 5)
                break
            if marker.exists():
                try:
                    result = json.loads(marker.read_text())
                    break
                except ValueError:
                    pass
            time.sleep(0.05)
        if not visible:
            raise RuntimeError("No application window became visible.")
        run(["import", "-window", "root", str(output / "window.png")])
        records["steps"].append("Janela real aberta e captura PNG")
        if format == "editor":
            assert not (home / "should-not-execute").exists(), "Opening the editor ran project code"
            records["steps"].append(
                "Qt/WebEngine editor opens a project without running own Python"
            )
            windows = subprocess.check_output(
                ["xdotool", "search", "--onlyvisible", "--name", "Makebench"], text=True
            ).split()
            for window in windows:
                run(["xdotool", "windowfocus", window])
                run(["xdotool", "key", "ctrl+q"])
            process.wait(timeout=15)
            records["steps"].append("Editor fechado pelo atalho Ctrl+Q")
        else:
            if result is None:
                raise RuntimeError(
                    "Flow produced no result: " + (output / "application.log").read_text()
                )
            assert result["steps"] == 3 and result["dependency"] == "25.0", result
            if format == "flatpak":
                assert result["host_visible"] is False, (
                    "The sandbox accessed a private file of the guest host"
                )
            else:
                assert result["host_visible"] is True, result
                assert result["prefix"] != "/usr" and "python3.12" in result["executable"], result
            process.wait(timeout=25)
            assert process.returncode == 0, (
                process.returncode,
                (output / "application.log").read_text(),
            )
            if format != "flatpak":
                deadline = time.monotonic() + 3
                pid = result["terminal_pid"]
                while Path(f"/proc/{pid}/stat").exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                assert not Path(f"/proc/{pid}/stat").exists(), (
                    "The terminal left a process after closing the window"
                )
            records["application"] = result
            records["steps"].extend(
                [
                    "Graph, repeat/condition, additional Python dependency and two windows",
                    "Terminal e tarefas executados",
                    "Aplicativo encerra e recolhe processos",
                ]
            )
        if installed:
            if format == "deb":
                run(["sudo", "apt-get", "remove", "-y", identifier])
                assert not Path("/opt", identifier).exists()
                assert not Path("/usr/bin", identifier).exists()
            elif format == "rpm":
                run(["sudo", "dnf", "-y", "remove", identifier])
                assert not Path("/opt", identifier).exists()
                assert not Path("/usr/bin", identifier).exists()
            else:
                run(
                    [
                        "flatpak",
                        "uninstall",
                        "--user",
                        "--noninteractive",
                        "--assumeyes",
                        identifier,
                    ]
                )
                assert (
                    subprocess.run(
                        ["flatpak", "info", "--user", identifier], capture_output=True
                    ).returncode
                    != 0
                )
            installed = False
            records["steps"].append("Real removal; neither program nor installation remains")
        else:
            artifact.unlink()
            assert not artifact.exists()
            records["steps"].append("AppImage removed after shutdown")
        records["ok"] = True
        (output / "results.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print(json.dumps(records, ensure_ascii=False), flush=True)
        return 0
    finally:
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
