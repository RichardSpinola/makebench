"""Contratos de distribuição isolada, compatibilidade e ambiente de processos externos."""

import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from makebench.core.project import Project, ProjectError
from makebench.core.portable import (
    ready,
    requirements,
    command,
    syntax_compatibility,
    assemble,
    wheel_root,
    CONTAINERFILE,
    IMAGE,
)
from makebench.core.build_environment import cache_root
from makebench.terminal.environment import external_environment


class PortableTests(unittest.TestCase):
    """Verificações não podem preparar SDKs, executar fontes nem aceitar cache alterado."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.root / "cache")})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_ready_and_requirements_are_inert(self):
        """Abrir Exportar inspeciona recibos; não inicia Podman, pip ou código de projeto."""
        project = Project.empty()
        project.application = {"backend": "gtk", "packages": ["packaging==25.0"]}
        with patch("subprocess.Popen") as popen, patch("subprocess.run") as run:
            self.assertFalse(ready(project))
            self.assertIn("pyte==0.8.2", requirements(project))
            popen.assert_not_called()
            run.assert_not_called()
        project.application["packages"] = ["--index-url=https://example.invalid"]
        with self.assertRaises(ProjectError):
            requirements(project)

    def test_staging_is_only_mount_and_network_disabled(self):
        """Construir usa somente staging; resolver pacotes precisa da preparação explícita."""
        with patch("shutil.which", return_value="/usr/bin/podman"):
            args = command(["python3.12", str(self.root / "payload.py")], self.root)
        self.assertIn("--network=none", args)
        self.assertIn("--read-only", args)
        self.assertIn("--cap-drop=all", args)
        self.assertEqual(args.count("--volume"), 1)
        self.assertIn(str(self.root) + ":/work:rw,Z", args)
        self.assertIn("/work/payload.py", args)

    def test_changed_wheel_never_reaches_installer(self):
        """O hash da cópia em staging é conferido antes de rodar a ferramenta."""
        project = Project.empty()
        project.application["backend"] = "gtk"
        root = wheel_root(project)
        root.mkdir(parents=True)
        wheel = root / "sample-1-py3-none-any.whl"
        wheel.write_bytes(b"original")
        (root / "receipt.json").write_text(
            json.dumps(
                {
                    "requirements": requirements(project),
                    "files": {wheel.name: hashlib.sha256(b"original").hexdigest()},
                }
            )
        )
        (cache_root() / "portable-sdk.json").write_text(
            json.dumps(
                {
                    "image": IMAGE,
                    "recipe_sha256": hashlib.sha256(CONTAINERFILE.encode()).hexdigest(),
                }
            )
        )
        appdir = self.root / "stage/AppDir"
        appdir.mkdir(parents=True)
        wheel.write_bytes(b"alterado")
        with patch("subprocess.Popen") as popen:
            with self.assertRaisesRegex(ProjectError, "alterada"):
                assemble(project, appdir)
            popen.assert_not_called()
        self.assertFalse((appdir.parent / "wheels" / wheel.name).exists())

    def test_target_grammar_is_checked_without_running_code(self):
        """Uma construção para Python3.12 rejeita gramática incompatível antes de preparar."""
        source = 'type Alias = int\nraise RuntimeError("não executar")\n'
        self.assertIsNone(syntax_compatibility(source, 12))
        self.assertIn("incompatível", syntax_compatibility(source, 11))
        for path in (Path(__file__).resolve().parents[1] / "src").rglob("*.py"):
            ast.parse(path.read_text(), feature_version=(3, 12))

    def test_host_programs_do_not_receive_bundled_python_or_libraries(self):
        """Terminal/tarefas do sistema preservam seu Python e bibliotecas próprios."""
        root = self.root / "AppDir"
        root.mkdir()
        original = {
            "PYTHONHOME": None,
            "PYTHONPATH": None,
            "LD_LIBRARY_PATH": "/original/lib",
            "PATH": "/usr/bin:/bin",
            "GI_TYPELIB_PATH": None,
        }
        environment = {
            "MAKEBENCH_PORTABLE_ROOT": str(root),
            "MAKEBENCH_ORIGINAL_ENV": json.dumps(original),
            "PYTHONHOME": str(root / "usr"),
            "PYTHONPATH": str(root / "site"),
            "LD_LIBRARY_PATH": str(root / "usr/lib"),
            "GI_TYPELIB_PATH": str(root / "typelibs"),
            "PATH": str(root / "usr/bin") + ":/usr/bin:/bin",
        }
        host = external_environment("/usr/bin/python3", environment)
        self.assertNotIn("PYTHONHOME", host)
        self.assertNotIn("PYTHONPATH", host)
        self.assertEqual(host["LD_LIBRARY_PATH"], "/original/lib")
        self.assertNotIn("GI_TYPELIB_PATH", host)
        bundled = external_environment(str(root / "usr/bin/python3.12"), environment)
        self.assertEqual(bundled["PYTHONHOME"], str(root / "usr"))

    def test_build_tools_use_host_environment_from_portable_editor(self):
        """Ferramentas externas também não recebem o PYTHONHOME privado do AppImage."""
        import sys
        from makebench.core.build_environment import run_tool

        original = {
            "PYTHONHOME": None,
            "PYTHONPATH": None,
            "LD_LIBRARY_PATH": None,
            "PATH": os.environ.get("PATH"),
        }
        with patch.dict(
            os.environ,
            {
                "MAKEBENCH_PORTABLE_ROOT": str(self.root / "AppDir"),
                "MAKEBENCH_ORIGINAL_ENV": json.dumps(original),
                "PYTHONHOME": "/runtime-que-nao-existe",
                "PYTHONPATH": "/pacote-privado",
            },
        ):
            output = run_tool(
                [
                    sys.executable,
                    "-c",
                    "import os; assert not os.environ.get('PYTHONHOME'); assert not os.environ.get('PYTHONPATH'); print('FERRAMENTA_OK')",
                ]
            )
        self.assertIn("FERRAMENTA_OK", output)

    def test_missing_sdk_is_not_a_fake_package(self):
        """Pedir DEB sem preparar falha claramente, sem criar um ZIP com extensão DEB."""
        from makebench.core.packages import build_package

        project = Project.empty()
        project.application = {
            "name": "Teste",
            "id": "org.exemplo.test",
            "version": "0.1.0",
            "backend": "gtk",
            "icon": "assets/icon.svg",
        }
        target = self.root / "app.deb"
        with self.assertRaisesRegex(ProjectError, "Preparar"):
            build_package(
                project, "", lambda _: b'<svg xmlns="http://www.w3.org/2000/svg"/>', target, "deb"
            )
        self.assertFalse(target.exists())

    def test_flatpak_allows_sandbox_tasks_without_host_permission(self):
        """Comandos comuns e terminal continuam dentro do pacote; admin é recusado."""
        from makebench.core.packages import preflight, write_recipe
        from makebench.core.logic import create_flow
        from makebench.core.logic_defaults import default_block

        project = Project.empty()
        project.application = {
            "name": "Teste",
            "id": "org.exemplo.test",
            "version": "0.1.0",
            "backend": "gtk",
            "icon": "assets/icon.svg",
        }
        project.add(project.root.id, "terminal")
        flow = create_flow(project, project.root.id)
        flow["body"] = [default_block("run", project, project.root.id)]
        assets = lambda _: b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        self.assertFalse(
            any(i["level"] == "error" for i in preflight(project, "", assets, "flatpak"))
        )
        root = write_recipe(project, "", assets, "flatpak", self.root / "recipe")
        manifest = json.loads((root / "org.exemplo.test.json").read_text())
        self.assertNotIn("--filesystem=host", manifest["finish-args"])
        self.assertNotIn("--talk-name=org.freedesktop.Flatpak", manifest["finish-args"])
        flow["body"][0]["admin"] = True
        self.assertTrue(
            any(i["level"] == "error" for i in preflight(project, "", assets, "flatpak"))
        )


class PortableInterfaceTests(unittest.TestCase):
    """Trocar o produto preserva a configuração do projeto sem preparar ou executar."""

    def test_editor_product_is_appimage_and_preserves_project_recipe(self):
        """Receita escondida não muda a ação do editor; retornar restaura formato/receita."""
        from PySide6.QtWidgets import QApplication
        from makebench.editor.window import MainWindow

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {
                    "XDG_CONFIG_HOME": directory,
                    "XDG_STATE_HOME": directory,
                    "XDG_CACHE_HOME": directory,
                },
            ),
        ):
            window = MainWindow(Project.empty())
            window.recovery_timer.stop()
            try:
                panel = window.publish_panel
                panel.format.setCurrentIndex(panel.format.findData("rpm"))
                panel.recipe_only.setChecked(True)
                snapshot = window.project.to_dict()
                with patch("subprocess.Popen") as popen, patch("subprocess.run") as run:
                    panel.product.setCurrentIndex(1)
                    self.assertEqual(panel.format.currentData(), "appimage")
                    self.assertEqual(panel.build.text(), "Construir AppImage…")
                    self.assertTrue(panel.recipe_only.isHidden())
                    self.assertFalse(
                        panel.format.model().item(panel.format.findData("rpm")).isEnabled()
                    )
                    panel.product.setCurrentIndex(0)
                    self.assertEqual(panel.format.currentData(), "rpm")
                    self.assertTrue(panel.recipe_only.isChecked())
                    self.assertEqual(window.project.to_dict(), snapshot)
                    popen.assert_not_called()
                    run.assert_not_called()
            finally:
                window.history.mark_saved()
                window.source.mark_saved()
                window.close()
                app.processEvents()

    def test_close_waits_for_inflight_designer_preview(self):
        """Fechar cancela a prévia e mantém sua QThread viva até limpar o helper."""
        import threading
        import time
        from PySide6.QtWidgets import QApplication
        from makebench.editor.window import MainWindow
        from makebench.editor.native_preview import GtkDesignSurface, GtkPreviewJob

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        started = threading.Event()

        def rendering(job):
            """Simula um renderizador ainda finalizando recursos após receber cancelamento."""
            started.set()
            job.cancel.wait(5)
            time.sleep(0.25)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"XDG_STATE_HOME": directory}),
        ):
            window = MainWindow(Project.empty())
            window.recovery_timer.stop()
            window.show()
            surface = GtkDesignSurface(window.canvas)
            window.canvas.gtk_surface = surface
            job = GtkPreviewJob({}, surface)
            surface.job = job
            with patch.object(GtkPreviewJob, "render", rendering):
                job.start()
                self.assertTrue(started.wait(2))
                try:
                    window.close()
                    self.assertTrue(job.cancel.is_set())
                    self.assertTrue(window.isVisible())
                    deadline = time.monotonic() + 4
                    while window.isVisible() and time.monotonic() < deadline:
                        app.processEvents()
                        time.sleep(0.02)
                    self.assertFalse(window.isVisible())
                    self.assertFalse(job.isRunning())
                finally:
                    job.cancel.set()
                    job.wait(2000)
                    window.close()
                    app.processEvents()


if __name__ == "__main__":
    unittest.main()
