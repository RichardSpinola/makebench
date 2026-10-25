"""Build QA examples in every format, without running their functions."""

import argparse
import json
from pathlib import Path
from package_fixture import fixture
from makebench.core.portable import prepare, build_editor_appimage, editor_project
from makebench.core.build_environment import prepare_flatpak
from makebench.core.packages import build_package, FORMATS


def main():
    """Explicit online preparation; the build uses only already verified environments and wheels."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--backend", choices=("qt", "gtk"), required=True)
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=("deb", "rpm", "appimage", "flatpak"),
        default=["deb", "rpm", "appimage", "flatpak"],
    )
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--editor", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    def progress(number, text):
        """Record the real output of each tool, without truncating the evidence file."""
        print(number, text, flush=True)

    if args.editor:
        if args.prepare:
            prepare(editor_project(), progress, editor=True)
        result = build_editor_appimage(args.output / "Makebench-editor.AppImage", progress)
        print(json.dumps(result), flush=True)
        return
    project, source, assets = fixture(args.backend)
    receipt = args.output / (args.backend + "-build.json")
    records = json.loads(receipt.read_text()) if receipt.exists() else []
    if args.prepare and any(format != "flatpak" for format in args.formats):
        prepare(project, progress)
    if args.prepare and "flatpak" in args.formats:
        prepare_flatpak(project, progress)
    for format in args.formats:
        target = args.output / (args.backend + FORMATS[format][2])
        if target.exists():
            raise RuntimeError(
                "Preserve artefatos anteriores escolhendo outra pasta: " + str(target)
            )
        result = build_package(project, source, assets, target, format, progress)
        records.append(result)
        (args.output / (args.backend + "-build.json")).write_text(
            json.dumps(records, ensure_ascii=False, indent=2)
        )
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
