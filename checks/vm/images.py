# SPDX-License-Identifier: GPL-3.0-or-later
"""Official images for disposable VMs; explicit download with SHA-256 checked."""

import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UBUNTU_BASE = "https://cloud-images.ubuntu.com/releases/noble/release/"
FEDORA_URL = "https://dl.fedoraproject.org/pub/fedora/linux/releases/44/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-44-1.7.x86_64.qcow2"
FEDORA_SHA = "28680fe5b371a5a82ebf43a31926e086a168e59949d03969c5093e7071f90b7f"


def fetch(url, path, digest):
    """Write to a partial file and publish only after checking the whole content."""
    if path.exists() and hashlib.file_digest(path.open("rb"), "sha256").hexdigest() == digest:
        return path
    part = path.with_suffix(".partial")
    hasher = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=60) as response, part.open("wb") as output:
        while block := response.read(1048576):
            output.write(block)
            hasher.update(block)
    if hasher.hexdigest() != digest:
        part.unlink()
        raise RuntimeError("SHA256 mismatch: " + url)
    part.replace(path)
    print("Imagem verificada:", path.name, flush=True)
    return path


def main(directory):
    """Download only the declared x86_64 versions; never starts a machine."""
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    checksum = urllib.request.urlopen(UBUNTU_BASE + "SHA256SUMS", timeout=30).read().decode()
    match = re.search(
        r"^([0-9a-f]{64})\s+\*?ubuntu-24\.04-server-cloudimg-amd64\.img$", checksum, re.M
    )
    if not match:
        raise RuntimeError("The Ubuntu image is not in the official manifest.")
    records = {
        "ubuntu24.04": {
            "url": UBUNTU_BASE + "ubuntu-24.04-server-cloudimg-amd64.img",
            "sha256": match[1],
        },
        "fedora44": {"url": FEDORA_URL, "sha256": FEDORA_SHA},
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(fetch, item["url"], root / (name + ".qcow2"), item["sha256"])
            for name, item in records.items()
        ]
        for future in futures:
            future.result()
    (root / "images.json").write_text(json.dumps(records, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
