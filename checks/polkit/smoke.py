"""Real Polkit exclusively inside a disposable container, with no host mounts."""

import os
from pathlib import Path
import subprocess
import time

if (
    os.environ.get("MAKEBENCH_POLKIT_CONTAINER_TEST") != "1"
    or not Path("/run/.containerenv").exists()
):
    raise SystemExit("Run this test only through the disposable Containerfile.")

Path("/run/dbus").mkdir(parents=True, exist_ok=True)
subprocess.run(["dbus-uuidgen", "--ensure=/etc/machine-id"], check=True)
subprocess.run(["dbus-daemon", "--system", "--fork", "--nopidfile"], check=True)
daemon = subprocess.Popen(["/usr/lib/polkit-1/polkitd", "--no-debug"])
rule = Path("/etc/polkit-1/rules.d/00-makebench-test.rules")


def policy(result):
    """Restrict authorization to the container identity and the read-only id command."""
    rule.write_text(
        "polkit.addRule(function(action, subject) {\n"
        'if (subject.user == "tester" && action.id == "org.freedesktop.policykit.exec" && action.lookup("program") == "/usr/bin/id") '
        f"return polkit.Result.{result};\n" + "});\n"
    )
    time.sleep(1)


def run(arguments):
    """Switch only to the disposable user inside the rootless namespace."""
    wrapper = [
        "python3",
        "-c",
        "import subprocess,sys; raise SystemExit(subprocess.call(sys.argv[1:]))",
        *arguments,
    ]
    return subprocess.run(
        wrapper,
        user="tester",
        group="tester",
        extra_groups=[],
        capture_output=True,
        text=True,
        timeout=20,
    )


try:
    time.sleep(1)
    policy("YES")
    result = run(["/usr/bin/pkexec", "--disable-internal-agent", "/usr/bin/id", "-u"])
    assert result.returncode == 0 and result.stdout.strip() == "0", (
        result.returncode,
        result.stdout,
        result.stderr,
    )
    print("ADMIN_SUCCESS: code 0, uid 0 only in the container.", flush=True)
    policy("NO")
    result = run(["/usr/bin/pkexec", "--disable-internal-agent", "/usr/bin/id", "-u"])
    assert result.returncode == 127, (result.returncode, result.stdout, result.stderr)
    print("ADMIN_DENIED: code 127.", flush=True)
    policy("AUTH_SELF")
    result = run(["python3", "/opt/cancel_agent.py"])
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert "CANCEL_EXIT=126" in result.stdout, result.stdout
    print("ADMIN_CANCELLED: code 126, no password.", flush=True)
finally:
    daemon.terminate()
    daemon.wait(timeout=5)
