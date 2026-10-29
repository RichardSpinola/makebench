# Install

Makebench runs on **Linux x86_64**. Everything works offline: there is no
account, no server and no AI at run time.

## AppImage (recommended)

The AppImage is one file with Makebench, Python and Qt inside. Nothing is
installed on the system.

1. Download `Makebench-<version>-x86_64.AppImage` and `SHA256SUMS` from the
   [releases page](https://github.com/RichardSpinola/makebench/releases).
2. Check the download and make it executable:

    ```bash
    sha256sum -c SHA256SUMS --ignore-missing
    chmod +x Makebench-*-x86_64.AppImage
    ```

3. Run it:

    ```bash
    ./Makebench-*-x86_64.AppImage
    ```

!!! tip "No FUSE on your system?"
    AppImages normally mount themselves with FUSE. Without it, start the file
    with `--appimage-extract-and-run`.

The AppImage needs a distribution with glibc 2.39 or newer (Ubuntu 24.04,
Fedora 40 or later, and others of the same age).

## From source

You need Python 3.12, 3.13 or 3.14 and Git. On Ubuntu, Qt WebEngine also needs
these libraries:

```bash
sudo apt install libegl1 libgl1 libxkbcommon0 libnss3 libdbus-1-3 libasound2t64
```

Then:

```bash
git clone https://github.com/RichardSpinola/makebench.git
cd makebench
python3 -m venv .venv
.venv/bin/python -m pip install -e .
./run-makebench
```

Everything goes into the `.venv` folder; nothing is installed system-wide. To
update later, run `git pull` and the `pip install` line again.

## Optional pieces

| For | You need |
|---|---|
| GTK 4 projects and their faithful preview | GTK 4, PyGObject and `gtk4-broadwayd` from your distribution |
| Building DEB, RPM, AppImage and Flatpak packages | Podman (rootless), so Makebench can prepare its build tools; or the packaging tools installed on the system |
| Version history and cloud copies | Git; `gh` signed in to create GitHub repositories |
| Tasks that need administrator rights | Polkit (`pkexec`), present on most desktops |

**Help › Environment diagnostics…** shows what Makebench found and what is
missing.

## Language

The interface is in English or Brazilian Portuguese. Change it in
**View › Preferences… › Appearance › Interface language**; it applies the next
time Makebench starts.

## Next steps

- [Build your first app with blocks](tutorial-blocks.md), or the same
  [with Python](tutorial-python.md).
- Open a ready-made project from the [examples](examples.md).
