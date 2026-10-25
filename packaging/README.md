# Packaging

Package builders live in the Python package, not here:

- `src/makebench/core/packages.py` and `core/exporter.py`: recipes for Python
  source, DEB, RPM, AppImage and Flatpak.
- `src/makebench/core/build_environment.py`: tools prepared in rootless Podman
  containers, with pinned downloads and hash-checked wheels.
- `src/makebench/core/portable.py` and `src/makebench/portable/`: the bundled
  Python runtime and the editor AppImage.

Use the Export window in the editor, or `checks/build_portable_examples.py`.
See [docs/building.md](../docs/building.md#packages). Builds never install tools
on the host system.
