"""Real build through the Export window, using only a known disposable project."""

import argparse
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch


def main():
    """Preparation that downloads tools only happens with the explicit --prepare option."""
    faulthandler.dump_traceback_later(180, repeat=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=["source", "deb", "rpm", "appimage", "flatpak"],
        default=["deb", "rpm", "appimage"],
    )
    parser.add_argument("--backend", choices=["gtk", "qt"], default="gtk")
    parser.add_argument("--editor", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mb-distribution-qa-") as temporary:
        root = Path(temporary)
        os.environ["XDG_CONFIG_HOME"] = str(root / "config")
        os.environ["XDG_STATE_HOME"] = str(root / "state")
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from makebench.core.project import Project
        from makebench.core.packages import FORMATS
        from makebench.editor.window import MainWindow

        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        project = Project.empty("Distribution test")
        project.application.update(
            backend=args.backend,
            name="Distribution test",
            id="br.exemplo.makebenchqa",
            version="0.1.0",
            description="Disposable test application",
        )
        window = MainWindow(project)
        window.recovery_timer.stop()
        icon = root / "icon.svg"
        icon.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256"><rect width="256" height="256" fill="#4285f4"/></svg>'
        )
        project.application["icon"] = window.assets.import_image(icon)
        window.logic.ensure_loaded()
        window.show()
        window.export_action.trigger()
        panel = window.publish_panel
        records = []
        if args.editor:
            panel.product.setCurrentIndex(1)
            assert panel.format.currentData() == "appimage"
            assert not panel.recipe_only.isVisible()
            args.formats = ["appimage"]

        def finish():
            """Also drain the completion signals, never accepting files from a previous run."""
            deadline = time.monotonic() + 600
            while panel.job and panel.job.isRunning() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)
            QTest.qWait(100)
            assert panel.job and not panel.job.isRunning()
            assert panel.build.isEnabled()
            assert not panel.cancel_button.isEnabled()
            print("Build thread finished: " + panel.result.text(), flush=True)

        try:
            for format in args.formats:
                panel.format.setCurrentIndex(panel.format.findData(format))
                if args.prepare and format != "source":
                    panel.prepare.click()
                    finish()
                    assert "pront" in panel.result.text(), panel.result.text()
                target = args.output / (
                    ("Makebench-editor" if args.editor else "teste-ui-" + args.backend)
                    + FORMATS[format][2]
                )
                assert not target.exists(), str(target) + " already exists"
                with patch(
                    "makebench.editor.publish.QFileDialog.getSaveFileName",
                    return_value=(str(target), ""),
                ):
                    panel.build.click()
                finish()
                (args.output / (format + "-construcao.log")).write_text(
                    panel.build_log.toPlainText()
                )
                assert target.is_file() and "Built" in panel.result.text(), panel.result.text()
                records.append(
                    {
                        "format": format,
                        "path": str(target.resolve()),
                        "size": target.stat().st_size,
                        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    }
                )
                print(panel.result.text(), flush=True)
            window.publish_dialog.grab().save(str(args.output / "exportacao.png"))
            (args.output / "results.json").write_text(
                json.dumps(records, ensure_ascii=False, indent=2)
            )
        finally:
            window.history.mark_saved()
            window.source.mark_saved()
            window.close()
            deadline = time.monotonic() + 15
            while window.isVisible() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)
            assert not window.isVisible()
        print("OK: Export window and real packages, without running the project code.", flush=True)


if __name__ == "__main__":
    main()
