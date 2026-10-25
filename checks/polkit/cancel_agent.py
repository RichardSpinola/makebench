# SPDX-License-Identifier: GPL-3.0-or-later
"""Disposable agent that simulates the user closing the authentication."""

import os
import subprocess
from pathlib import Path

if (
    os.environ.get("MAKEBENCH_POLKIT_CONTAINER_TEST") != "1"
    or not Path("/run/.containerenv").exists()
):
    raise SystemExit("This agent is exclusive to the disposable container.")
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()


class Agent(dbus.service.Object):
    """Implements only the two calls of the Polkit agent protocol."""

    @dbus.service.method(
        "org.freedesktop.PolicyKit1.AuthenticationAgent",
        in_signature="sssa{ss}sa(sa{sv})",
        out_signature="",
    )
    def BeginAuthentication(self, action_id, message, icon_name, details, cookie, identities):
        """Close the request without providing credentials."""
        raise dbus.exceptions.DBusException(
            "Cancelado pelo teste.", name="org.freedesktop.PolicyKit1.Error.Cancelled"
        )

    @dbus.service.method(
        "org.freedesktop.PolicyKit1.AuthenticationAgent", in_signature="s", out_signature=""
    )
    def CancelAuthentication(self, cookie):
        """Accepts cancellation requested by the authority."""


agent = Agent(bus, "/org/makebench/TestAgent")
authority = dbus.Interface(
    bus.get_object("org.freedesktop.PolicyKit1", "/org/freedesktop/PolicyKit1/Authority"),
    "org.freedesktop.PolicyKit1.Authority",
)
parts = open(f"/proc/{os.getpid()}/stat").read().split()
subject = (
    "unix-process",
    {
        "pid": dbus.UInt32(os.getpid()),
        "start-time": dbus.UInt64(int(parts[21])),
        "uid": dbus.Int32(os.getuid()),
    },
)
authority.RegisterAuthenticationAgent(subject, "C", "/org/makebench/TestAgent")
loop = GLib.MainLoop()
process = subprocess.Popen(
    ["/usr/bin/pkexec", "--disable-internal-agent", "/usr/bin/id", "-u"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)


def finished():
    """End the loop when pkexec receives the agent's refusal."""
    if process.poll() is None:
        return True
    out, err = process.communicate()
    print(f"CANCEL_EXIT={process.returncode}", flush=True)
    print(out + err, flush=True)
    loop.quit()
    return False


GLib.timeout_add(50, finished)
loop.run()
raise SystemExit(0 if process.returncode == 126 else 1)
