# SPDX-License-Identifier: GPL-3.0-or-later
"""Disposable KVM VM with an overlay disk and SSH restricted to the host loopback."""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time


class Machine:
    """Control only the VM registered in this folder, never the owner's disks or networks."""

    def __init__(self, root):
        """Read the local receipt; building the controller starts no machine."""
        self.root = Path(root).resolve()
        self.receipt = (
            json.loads((self.root / "machine.json").read_text())
            if (self.root / "machine.json").exists()
            else None
        )

    def start(self, image, target, port):
        """Cria overlay, chave exclusiva e seed cloud-init; inicia QEMU sem compartilhar home."""
        self.root.mkdir(parents=True, exist_ok=True)
        if self.receipt:
            raise RuntimeError(
                "This folder already contains a VM. Shut it down or use another folder."
            )
        key = self.root / "qa-key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        public = key.with_suffix(".pub").read_text().strip()
        group = "sudo" if target == "ubuntu24.04" else "wheel"
        (self.root / "user-data").write_text(
            "#cloud-config\nusers:\n  - name: qa\n    groups: ["
            + group
            + "]\n    sudo: ALL=(ALL) NOPASSWD:ALL\n    shell: /bin/bash\n    lock_passwd: true\n    ssh_authorized_keys:\n      - "
            + public
            + "\nssh_pwauth: false\ndisable_root: true\n"
        )
        (self.root / "meta-data").write_text(
            "instance-id: makebench-" + target + "\nlocal-hostname: makebench-" + target + "\n"
        )
        subprocess.run(
            [
                "mkisofs",
                "-quiet",
                "-output",
                str(self.root / "seed.iso"),
                "-volid",
                "cidata",
                "-joliet",
                "-rock",
                str(self.root / "user-data"),
                str(self.root / "meta-data"),
            ],
            check=True,
        )
        subprocess.run(
            [
                "qemu-img",
                "create",
                "-f",
                "qcow2",
                "-F",
                "qcow2",
                "-b",
                str(Path(image).resolve()),
                str(self.root / "disk.qcow2"),
            ],
            check=True,
        )
        subprocess.run(["qemu-img", "resize", str(self.root / "disk.qcow2"), "32G"], check=True)
        arguments = [
            "qemu-system-x86_64",
            "-enable-kvm",
            "-machine",
            "q35",
            "-cpu",
            "host",
            "-smp",
            "2",
            "-m",
            "1536",
            "-display",
            "none",
            "-monitor",
            "none",
            "-serial",
            "file:" + str(self.root / "serial.log"),
            "-drive",
            "file=" + str(self.root / "disk.qcow2") + ",if=virtio,format=qcow2",
            "-drive",
            "file=" + str(self.root / "seed.iso") + ",media=cdrom,readonly=on",
            "-netdev",
            f"user,id=net0,hostfwd=tcp:127.0.0.1:{port}-:22",
            "-device",
            "virtio-net-pci,netdev=net0",
        ]
        with (self.root / "qemu.log").open("w") as log:
            process = subprocess.Popen(
                arguments, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
        self.receipt = {
            "pid": process.pid,
            "target": target,
            "port": port,
            "image": str(Path(image).resolve()),
            "started": time.time(),
            "arguments": arguments,
        }
        (self.root / "machine.json").write_text(json.dumps(self.receipt, indent=2))
        self.wait_ready(process)

    def resume(self):
        """Resume the already prepared QA overlay, without re-creating disks or sharing folders."""
        if not self.receipt:
            raise RuntimeError("There is no VM registered in this folder.")
        try:
            if (
                str(self.root / "disk.qcow2").encode()
                in Path(f"/proc/{self.receipt['pid']}/cmdline").read_bytes()
            ):
                raise RuntimeError("This VM is already running.")
        except FileNotFoundError:
            pass
        with (self.root / "qemu.log").open("a") as log:
            process = subprocess.Popen(
                self.receipt["arguments"],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self.receipt["pid"] = process.pid
        self.receipt["started"] = time.time()
        (self.root / "machine.json").write_text(json.dumps(self.receipt, indent=2))
        self.wait_ready(process)

    def wait_ready(self, process):
        """Wait only for the started VM's SSH, with a deadline and boot diagnostics."""
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError((self.root / "qemu.log").read_text())
            if self.ssh("true", check=False, timeout=5).returncode == 0:
                print("VM pronta:", self.receipt["target"], flush=True)
                return
            time.sleep(2)
        raise RuntimeError("SSH did not become available; see the VM's serial.log.")

    def ssh(self, command, check=True, timeout=600, **kwargs):
        """Run in the guest with a temporary key, never forwarding the host agent or environment."""
        return subprocess.run(
            [
                "ssh",
                "-F",
                "/dev/null",
                "-i",
                str(self.root / "qa-key"),
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "UserKnownHostsFile=" + str(self.root / "known_hosts"),
                "-o",
                "ConnectTimeout=3",
                "-p",
                str(self.receipt["port"]),
                "qa@127.0.0.1",
                command,
            ],
            check=check,
            timeout=timeout,
            **kwargs,
        )

    def copy_to(self, source, destination):
        """Copia somente artefatos/rotinas de QA explicitamente indicados para o convidado."""
        subprocess.run(
            [
                "scp",
                "-F",
                "/dev/null",
                "-i",
                str(self.root / "qa-key"),
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "UserKnownHostsFile=" + str(self.root / "known_hosts"),
                "-P",
                str(self.receipt["port"]),
                str(source),
                "qa@127.0.0.1:" + destination,
            ],
            check=True,
        )

    def prepare_display(self):
        """Install the graphical test infrastructure, not the applications' Python/backend."""
        if self.receipt["target"] == "ubuntu24.04":
            command = "sudo apt-get update && sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y xvfb xauth dbus-x11 x11-utils xdotool imagemagick flatpak"
        else:
            command = "sudo dnf -y install xorg-x11-server-Xvfb xorg-x11-xauth dbus-x11 xdotool ImageMagick flatpak"
        self.ssh(command, timeout=1200)
        self.ssh("cat /etc/os-release; uname -m; python3 --version")

    def stop(self):
        """Desliga somente o QEMU cujo argv ainda referencia o overlay registrado."""
        pid = self.receipt["pid"]
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes()
            if str(self.root / "disk.qcow2").encode() not in command:
                raise RuntimeError("The PID no longer belongs to this VM; not signaling.")
            self.ssh("sudo poweroff", check=False, timeout=10)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and Path(f"/proc/{pid}").exists():
                time.sleep(0.2)
            if Path(f"/proc/{pid}").exists():
                os.killpg(pid, signal.SIGTERM)
        except FileNotFoundError:
            pass


def main():
    """Reproducible CLI to prepare and shut down the validation VMs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "resume", "display", "ssh", "stop"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--target", choices=("ubuntu24.04", "fedora44"))
    parser.add_argument("--port", type=int, default=22241)
    parser.add_argument("--command")
    args = parser.parse_args()
    machine = Machine(args.root)
    if args.action == "start":
        machine.start(args.image, args.target, args.port)
    elif args.action == "resume":
        machine.resume()
    elif args.action == "display":
        machine.prepare_display()
    elif args.action == "ssh":
        machine.ssh(args.command)
    else:
        machine.stop()


if __name__ == "__main__":
    main()
