# SPDX-License-Identifier: GPL-3.0-or-later
"""Inert compatibility of the GTK editor and content of the five exporters."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from makebench.core.project import Project, ComponentKind, LayoutKind
from makebench.core.storage import save_project, load_project
from makebench.core.document import Document
from makebench.gtk_runtime.renderer import layout_spec
from makebench.core.navigation import welcome_template
from makebench.core.packages import write_recipe, build_package, preflight
from makebench.core.exporter import export_source, BuildCancelled
from makebench.core.diagnostics import environment_report


class NativeReleaseTests(unittest.TestCase):
    """Data tests need no display and start no project subprocesses."""

    def setUp(self):
        """Each test uses disposable files; owner preferences are never changed."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture(self, backend="gtk"):
        """Application with a valid identity and its own embedded icon."""
        p = welcome_template()
        p.application = {
            "backend": backend,
            "name": "My application",
            "id": "br.exemplo.app",
            "version": "0.1.0",
            "icon": "assets/icon.svg",
            "description": "Uma ferramenta visual para Linux",
            "license": "MIT",
        }
        assets = {
            "assets/icon.svg": b'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256"/></svg>'
        }
        return p, assets

    def test_open_save_recovery_never_execute_and_noop_is_unchanged(self):
        """JSON and source with malicious effects are only data during these operations."""
        p, assets = self.fixture()
        path = self.root / "project.makebench.json"
        save_project(p, path)
        (self.root / "assets").mkdir()
        (self.root / "assets/icon.svg").write_bytes(assets["assets/icon.svg"])
        source = self.root / "project.actions.py"
        source.write_text("raise RuntimeError('Nunca executar ao abrir ou salvar')\n")
        before = (
            path.read_bytes(),
            source.read_bytes(),
            path.stat().st_mtime_ns,
            source.stat().st_mtime_ns,
        )
        with patch("subprocess.Popen") as process, patch("subprocess.run") as run:
            doc = Document(path=path)
            doc.save()
            recovery = self.root / "recovery.json"
            doc.recovery(recovery)
            recovered = Document.recover(recovery)
            process.assert_not_called()
            run.assert_not_called()
            self.assertEqual(recovered.source.text, doc.source.text)
        self.assertEqual(
            before,
            (
                path.read_bytes(),
                source.read_bytes(),
                path.stat().st_mtime_ns,
                source.stat().st_mtime_ns,
            ),
        )

    def test_model_to_gtk_layout_translation(self):
        """Neutral layouts and sizes have a translation independent of the graphical context."""
        p = Project.empty()
        p.root.layout = LayoutKind.GRID
        p.root.properties.update(spacing=18, padding=24, columns=3)
        child = p.add(p.root.id, ComponentKind.BUTTON)
        child.properties["size_mode"] = {"width": "fill", "height": "fixed"}
        spec = layout_spec(p.root)
        self.assertEqual(
            (spec["layout"], spec["spacing"], spec["padding"], spec["columns"]), ("grid", 18, 24, 3)
        )
        self.assertEqual(spec["children"][0]["size"], child.properties["size_mode"])

    def test_source_backends_include_only_corresponding_runtime(self):
        """Exported GTK needs no Qt and includes the neutral worker."""
        for backend in ("gtk", "qt"):
            p, assets = self.fixture(backend)
            path = self.root / (backend + ".zip")
            export_source(p, "", assets.__getitem__, path)
            with zipfile.ZipFile(path) as z:
                compile(z.read("run.py"), "run.py", "exec")
                names = z.namelist()
                requirements = z.read("requirements.txt").decode()
                self.assertIn("makebench/runtime/worker.py", names)
                if backend == "gtk":
                    self.assertIn("makebench/gtk_runtime/application.py", names)
                    self.assertNotIn("makebench/runtime/window.py", names)
                    self.assertNotIn("PySide6", requirements)
                else:
                    self.assertIn("makebench/runtime/window.py", names)
                    self.assertIn("PySide6", requirements)
                self.assertFalse(any("/editor/" in n or "/gtk_editor/" in n for n in names))

    def test_each_recipe_contains_metadata_launchers_and_no_execution(self):
        """Control, spec, manifest and AppDir are inspectable, inert files."""
        p, assets = self.fixture()
        for format in ("deb", "appimage", "flatpak", "rpm"):
            with self.subTest(format=format), patch("subprocess.Popen") as process:
                root = write_recipe(
                    p,
                    "raise RuntimeError('não rodar no build')\n",
                    assets.__getitem__,
                    format,
                    self.root / format,
                )
                process.assert_not_called()
                self.assertTrue((root / "br.exemplo.app.desktop").exists())
                self.assertTrue((root / "app/run.py").exists())
                if format == "deb":
                    self.assertIn(
                        "Architecture: amd64", (root / "payload/DEBIAN/control").read_text()
                    )
                    self.assertNotIn("python3", (root / "payload/DEBIAN/control").read_text())
                elif format == "rpm":
                    self.assertNotIn("Requires: python3", (root / "app.spec").read_text())
                    self.assertIn("AutoReqProv: no", (root / "app.spec").read_text())
                elif format == "flatpak":
                    manifest = json.loads((root / "br.exemplo.app.json").read_text())
                    self.assertNotIn("--filesystem=host", manifest["finish-args"])
                    self.assertEqual(manifest["runtime"], "org.gnome.Platform")
                elif format == "appimage":
                    self.assertTrue((root / "AppDir/AppRun").stat().st_mode & 0o111)

    def test_admin_policy_requires_authentication_and_flatpak_blocks_host(self):
        """Administrative packages add no automatic authorization policy."""
        from makebench.core.logic import create_flow

        p, assets = self.fixture()
        button = next(n for n in p.root.walk() if n.kind == ComponentKind.BUTTON)
        from makebench.core.logic_defaults import default_block

        node = default_block("run", p, p.root.id)
        node["admin"] = True
        create_flow(p, button.id)["body"] = [node]
        for format in ("deb", "rpm"):
            root = write_recipe(p, "", assets.__getitem__, format, self.root / format)
            policy = (root / "br.exemplo.app.policy").read_text()
            self.assertIn("auth_admin", policy)
            self.assertNotIn("allow_active>yes", policy)
        self.assertTrue(
            any(i["level"] == "error" for i in preflight(p, "", assets.__getitem__, "flatpak"))
        )

    def test_missing_tools_and_cancel_never_publish_partial_package(self):
        """A generated recipe has an explicit status; cancelling keeps the destination empty."""
        p, assets = self.fixture()
        target = self.root / "deb-recipe.zip"
        with patch("makebench.core.packages.build_tools", return_value={}):
            result = build_package(p, "", assets.__getitem__, target, "deb", recipe_only=True)
        self.assertIn("Generated, not built", result["status"])
        self.assertTrue(zipfile.is_zipfile(target))
        with self.assertRaises(BuildCancelled):
            build_package(
                p,
                "",
                assets.__getitem__,
                self.root / "cancel.zip",
                "rpm",
                cancelled=lambda: True,
                recipe_only=True,
            )
        self.assertFalse((self.root / "cancel.zip").exists())
        self.assertFalse(list(self.root.glob(".makebench-package-*")))

    def test_environment_report_is_readonly_and_clear_about_polkit(self):
        """Building the diagnostics runs no tools and does not suggest validated authentication."""
        with patch("subprocess.run") as run, patch("subprocess.Popen") as process:
            report = environment_report({"Display": "teste"})
            run.assert_not_called()
            process.assert_not_called()
        self.assertIn("Qt Widgets", report)
        self.assertIn("does not validate the Polkit agent", report)
        self.assertIn("Display: teste", report)
