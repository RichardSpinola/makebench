"""Polkit real exclusivamente dentro de contêiner descartável, sem mounts do host."""

import os
from pathlib import Path
import subprocess
import time

if (
    os.environ.get("MAKEBENCH_POLKIT_CONTAINER_TEST") != "1"
    or not Path("/run/.containerenv").exists()
):
    raise SystemExit("Execute este teste somente pelo Containerfile descartável.")

Path("/run/dbus").mkdir(parents=True, exist_ok=True)
subprocess.run(["dbus-uuidgen", "--ensure=/etc/machine-id"], check=True)
subprocess.run(["dbus-daemon", "--system", "--fork", "--nopidfile"], check=True)
daemon = subprocess.Popen(["/usr/lib/polkit-1/polkitd", "--no-debug"])
rule = Path("/etc/polkit-1/rules.d/00-makebench-test.rules")


def policy(result):
    """Restringe a autorização à identidade do contêiner e ao comando de leitura id."""
    rule.write_text(
        "polkit.addRule(function(action, subject) {\n"
        'if (subject.user == "tester" && action.id == "org.freedesktop.policykit.exec" && action.lookup("program") == "/usr/bin/id") '
        f"return polkit.Result.{result};\n" + "});\n"
    )
    time.sleep(1)


def run(arguments):
    """Troca somente para o usuário descartável dentro do namespace rootless."""
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
    print("ADMIN_SUCCESS: código 0, uid 0 somente no contêiner.", flush=True)
    policy("NO")
    result = run(["/usr/bin/pkexec", "--disable-internal-agent", "/usr/bin/id", "-u"])
    assert result.returncode == 127, (result.returncode, result.stdout, result.stderr)
    print("ADMIN_DENIED: código 127.", flush=True)
    policy("AUTH_SELF")
    result = run(["python3", "/opt/cancel_agent.py"])
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert "CANCEL_EXIT=126" in result.stdout, result.stdout
    print("ADMIN_CANCELLED: código 126, sem senha.", flush=True)
finally:
    daemon.terminate()
    daemon.wait(timeout=5)
