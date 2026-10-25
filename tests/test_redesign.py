"""Compatibility, recovery, navigation and export of the real workbench."""

import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QFileDialog, QMessageBox
from PySide6.QtTest import QTest
from makebench.core.project import ComponentKind, LayoutKind, Project, ProjectError
from makebench.core.navigation import add_state, add_window, welcome_template
from makebench.core.storage import save_project, load_project
from makebench.core.bundle import read_bundle, write_bundle
from makebench.core.exporter import BuildCancelled, export_source, verify
from makebench.editor.assets import AssetStore
from makebench.ui.theme import PALETTES, contrast


class RedesignModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_legacy_stays_v4_and_upgrade_keeps_backup(self):
        p = Project.empty()
        path = self.root / "project.makebench.json"
        save_project(p, path)
        before = path.read_bytes()
        mtime = path.stat().st_mtime_ns
        q = load_project(path)
        save_project(q, path)
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(mtime, path.stat().st_mtime_ns)
        add_window(q, "Outra")
        save_project(q, path)
        self.assertEqual(path.with_name(path.name + ".bak-v4").read_bytes(), before)
        self.assertEqual(load_project(path).to_dict()["format_version"], 5)

    def test_every_legacy_example_roundtrips_without_semantic_loss(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        for path in examples.rglob("*.makebench.json"):
            if json.loads(path.read_text())["format_version"] > 4:
                continue
            with self.subTest(path=path):
                p = load_project(path)
                data = p.to_dict()
                q = Project.from_dict(data)
                self.assertEqual(q.to_dict(), data)
                self.assertEqual(q.to_dict()["format_version"], 4)

    def test_states_preserve_base_and_all_ids(self):
        p = welcome_template()
        before = p.root.to_dict()
        state = p.states[p.root.id][0]
        effective = p.effective_root(p.root.id, state["id"])
        self.assertEqual(p.root.to_dict(), before)
        self.assertEqual([n.id for n in effective.walk()], [n.id for n in p.root.walk()])
        q = Project.from_dict(p.to_dict())
        self.assertEqual(q.to_dict(), p.to_dict())
        self.assertNotEqual(effective.to_dict(), before)

    def test_invalid_navigation_and_metadata_are_rejected(self):
        p = welcome_template()
        data = p.to_dict()
        mutations = [
            lambda d: d.update(windows={}),
            lambda d: d.update(entry_window="missing"),
            lambda d: d["ui"]["properties"].update(initial_state="missing"),
            lambda d: d.update(application={"icon": "/etc/passwd"}),
            lambda d: d["ui"]["properties"].update(size_mode=[]),
            lambda d: d["ui"]["properties"].update(visible="yes"),
        ]
        for mutation in mutations:
            copy = json.loads(json.dumps(data))
            mutation(copy)
            with self.subTest(mutation=mutation):
                with self.assertRaises(ProjectError):
                    Project.from_dict(copy)

    def test_shared_bundle_is_inert_and_preserves_source_assets(self):
        p = Project.empty()
        image = p.add(p.root.id, ComponentKind.IMAGE)
        image.properties["source"] = "assets/test.png"
        source = "raise RuntimeError('NUNCA EXECUTAR AO ABRIR')\n"
        archive = self.root / "project.zip"
        write_bundle(p, source, lambda _: b"fixture", archive)
        path = read_bundle(archive, self.root / "extracted")
        self.assertEqual(load_project(path).to_dict(), p.to_dict())
        self.assertEqual((path.parent / "project.actions.py").read_text(), source)
        self.assertEqual((path.parent / "assets/test.png").read_bytes(), b"fixture")

    def test_bundle_rejects_escape_and_symlink(self):
        for name, link in [("../escape", False), ("/tmp/escape", False), ("assets/link", True)]:
            archive = self.root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("project.makebench.json", json.dumps(Project.empty().to_dict()))
                item = zipfile.ZipInfo(name)
                if link:
                    item.external_attr = 0o120777 << 16
                z.writestr(item, "bad")
            with self.assertRaises(ProjectError):
                read_bundle(archive, self.root / "bad")
        self.assertFalse((self.root / "escape").exists())

    def export_fixture(self):
        p = Project.empty("Aplicativo exportado")
        p.application = {
            "name": p.name,
            "id": "br.exemplo.teste",
            "version": "0.1.0",
            "icon": "assets/icon.svg",
        }
        assets = {
            "assets/icon.svg": b'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#3584e4"/></svg>'
        }
        return p, assets

    def test_scoped_logic_alone_requires_v5(self):
        from makebench.core.logic import create_flow

        p = Project.empty()
        button = p.add(p.root.id, ComponentKind.BUTTON)
        create_flow(p, button.id)["body"] = [
            {
                "id": "local",
                "op": "assign",
                "scope": "window",
                "name": "valor",
                "value": {"id": "v", "op": "literal", "value": 1},
            }
        ]
        self.assertEqual(p.to_dict()["format_version"], 5)
        self.assertEqual(Project.from_dict(p.to_dict()).to_dict(), p.to_dict())

    def test_legacy_metadata_application_is_preserved_as_opaque_extension(self):
        p = Project.empty()
        data = p.to_dict()
        data["metadata"]["application"] = {"custom": "do not interpret", "icon": 42}
        q = Project.from_dict(data)
        self.assertEqual(q.metadata, data["metadata"])
        self.assertEqual(q.application, {})
        self.assertEqual(q.to_dict()["format_version"], 4)

    def test_removing_component_cleans_state_override_and_roundtrips(self):
        p = Project.empty()
        label = p.add(p.root.id, ComponentKind.LABEL)
        state = add_state(p, p.root.id, "Outra")
        state["overrides"][label.id] = {"text": "Variação"}
        p.remove(label.id)
        self.assertNotIn(label.id, state["overrides"])
        Project.from_dict(p.to_dict())

    def test_export_is_real_inert_complete_and_cancellable(self):
        p, assets = self.export_fixture()
        destination = self.root / "app.zip"
        source = "raise RuntimeError('SEM EXECUCAO NO BUILD')\n"
        result = export_source(p, source, assets.__getitem__, destination)
        self.assertEqual(len(result["sha256"]), 64)
        with zipfile.ZipFile(destination) as archive:
            self.assertIn("run.py", archive.namelist())
            self.assertIn("makebench/runtime/worker.py", archive.namelist())
            self.assertEqual(archive.read("project.actions.py").decode(), source)
            self.assertFalse(
                any("/editor/" in name or "/web/" in name for name in archive.namelist())
            )
        with self.assertRaises(ProjectError):
            export_source(p, source, assets.__getitem__, destination)
        cancel = self.root / "cancelled.zip"
        with self.assertRaises(BuildCancelled):
            export_source(p, source, assets.__getitem__, cancel, cancelled=lambda: True)
        self.assertFalse(cancel.exists())
        self.assertFalse(list(self.root.glob(".makebench-build-*")))

    def test_export_runs_outside_editor_and_last_window_exits(self):
        from makebench.core.logic import create_flow

        p, assets = self.export_fixture()
        create_flow(p, p.root.id)["body"] = [{"id": "close", "op": "close_window"}]
        source = (
            "from pathlib import Path\nPath('started.txt').write_text('executado explicitamente')\n"
        )
        destination = self.root / "app.zip"
        export_source(p, source, assets.__getitem__, destination)
        target = self.root / "standalone"
        target.mkdir()
        with zipfile.ZipFile(destination) as archive:
            archive.extractall(target)
        self.assertFalse((target / "started.txt").exists())
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH="")
        result = subprocess.run(
            [sys.executable, "run.py"],
            cwd=target,
            env=environment,
            timeout=10,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((target / "started.txt").read_text(), "executado explicitamente")

    def test_tokens_meet_contrast_on_used_surfaces(self):
        for name, t in PALETTES.items():
            for surface in ("panel", "raised", "canvas"):
                for text in ("text", "muted", "warning", "error", "success", "info"):
                    with self.subTest(theme=name, surface=surface, text=text):
                        self.assertGreaterEqual(contrast(t[text], t[surface]), 4.5)
                self.assertGreaterEqual(contrast(t["control"], t[surface]), 3)
            self.assertGreaterEqual(contrast(t["fill"], t["on_accent"]), 4.5)


class RedesignQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {"XDG_STATE_HOME": str(self.root / "state")})
        self.environment.start()
        self.windows = []

    def tearDown(self):
        for w in self.windows:
            if hasattr(w, "session"):
                if not w.session.closed:
                    w.stop()
                    self.wait(lambda: w.session.closed)
                w.close()
            else:
                w.history.mark_saved()
                w.source.mark_saved()
                w.close()
        self.environment.stop()
        self.temp.cleanup()

    def wait(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate())

    def test_wizard_runs_three_states_and_opens_second_window(self):
        from makebench.runtime.window import RuntimeWindow

        p = welcome_template()
        w = RuntimeWindow(p, "", lambda _: b"", self.root)
        self.windows.append(w)
        w.show()
        w.start()
        self.wait(lambda: w.session.active and not w.session.busy)
        button = next(n for n in p.root.walk() if n.properties.get("text") == "Next")
        heading = next(n for n in p.root.walk() if n.kind == ComponentKind.LABEL)
        original = heading.properties["text"]
        for _ in range(3):
            w.view.widgets[button.id].click()
            self.wait(lambda: not w.session.busy)
        self.assertEqual(w.view.widgets[button.id].text(), "Finish")
        self.assertEqual(w.open_windows, {p.windows[0].id})
        self.assertTrue(w.app_windows[p.windows[0].id].isVisible())
        self.assertEqual(heading.properties["text"], original)

    def test_editor_modes_preserve_selection_and_layout_memory(self):
        from makebench.editor.window import MainWindow

        p = Project.empty()
        p.root.layout = LayoutKind.FREE
        b = p.add(p.root.id, ComponentKind.BUTTON)
        b.geometry.update(x=150, y=110)
        w = MainWindow(p)
        self.windows.append(w)
        w.show()
        self.app.processEvents()
        w._select(b.id)
        for mode in ("code", "map", "publish", "design"):
            w.set_mode(mode)
            self.assertEqual(w.selected_id, b.id)
        w._change_property(p.root.id, "layout", "vertical")
        w._change_property(p.root.id, "layout", "free")
        self.assertEqual(w.project.find(b.id).geometry["x"], 150)
        self.assertEqual(w.project.find(b.id).geometry["y"], 110)
        w.undo()
        self.assertEqual(w.project.root.layout, LayoutKind.VERTICAL)

    def test_recovery_does_not_touch_original_or_execute_functions(self):
        from makebench.editor.window import MainWindow

        p = Project.empty()
        path = self.root / "project.makebench.json"
        save_project(p, path)
        original = path.read_bytes()
        w = MainWindow(p, path)
        self.windows.append(w)
        w.source_editor.setPlainText("raise RuntimeError('NAO EXECUTAR')\n")
        w._change_property(p.root.id, "title", "Alterado")
        with patch("subprocess.Popen", side_effect=AssertionError("Não executar")):
            w.snapshot_recovery()
            w.refresh_recovery()
            self.assertTrue(w.recoveries)
        self.assertEqual(path.read_bytes(), original)
        archive = w.recoveries[0] / "project.zip"
        with zipfile.ZipFile(archive) as z:
            self.assertIn("NAO EXECUTAR", z.read("project.actions.py").decode())

    def test_state_edit_never_changes_default_structure(self):
        from makebench.editor.window import MainWindow

        p = welcome_template()
        w = MainWindow(p)
        self.windows.append(w)
        label = next(n for n in p.root.walk() if n.kind == ComponentKind.LABEL)
        before = label.properties["text"]
        state = p.states[p.root.id][0]
        w.activate_window(p.root.id, state["id"])
        w._select(label.id)
        w._change_property(label.id, "text", "Só neste estado")
        self.assertEqual(w.project.find(label.id).properties["text"], before)
        self.assertEqual(
            w.project.effective_root(p.root.id, state["id"]).children[0].properties["text"],
            "Só neste estado",
        )
        count = len(list(w.project.walk()))
        w.add_component()
        self.assertEqual(len(list(w.project.walk())), count)

    def test_pt_buttons_without_catalog_or_desktop_locale(self):
        """Brazilian Portuguese labels Qt's own dialogs even without the system catalog."""
        from makebench.i18n import set_language
        from makebench.ui.dialogs import install_translation, translate_buttons

        set_language("pt_BR")

        def restore():
            """Leave English and the app's translators as the other tests expect."""
            set_language("en")
            for name in ("_makebench_translator", "_makebench_translation_fallback"):
                translator = getattr(self.app, name, None)
                if translator is not None:
                    self.app.removeTranslator(translator)
                    delattr(self.app, name)

        self.addCleanup(restore)
        install_translation(self.app)
        from PySide6.QtCore import QCoreApplication

        self.assertEqual(
            QCoreApplication.translate("unrelated", "Texto preservado"), "Texto preservado"
        )
        picker = QFileDialog()
        picker.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        from PySide6.QtWidgets import QLabel

        labels = [label.text() for label in picker.findChildren(QLabel)]
        self.assertTrue(any("Procurar em" in value for value in labels))
        self.assertTrue(any("Nome do arquivo" in value for value in labels))
        dialog = QMessageBox()
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        translate_buttons(dialog)
        self.assertEqual(
            [
                dialog.button(key).text()
                for key in (
                    QMessageBox.StandardButton.Save,
                    QMessageBox.StandardButton.Discard,
                    QMessageBox.StandardButton.Cancel,
                )
            ],
            ["Salvar", "Descartar", "Cancelar"],
        )


class ExtendedRedesignTests(unittest.TestCase):
    """Added journeys that exercise gestures and scopes, beyond serialization."""

    setUpClass = classmethod(RedesignQtTests.setUpClass.__func__)
    setUp = RedesignQtTests.setUp
    tearDown = RedesignQtTests.tearDown
    wait = RedesignQtTests.wait

    def test_window_duplication_preserves_states_flows_and_comments(self):
        p = welcome_template()
        before_ids = {n.id for n in p.walk()}
        flow = p.workflows[0]
        flow["body"][0]["comment"] = "Transição documentada"
        clone = add_window(p, "Cópia", p.root.id)
        Project.from_dict(p.to_dict())
        self.assertFalse(before_ids & {n.id for n in clone.walk()})
        copies = [f for f in p.workflows if p.window_of(f["event"]["component"]).id == clone.id]
        self.assertEqual(len(copies), 5)
        self.assertEqual(copies[0]["body"][0]["comment"], "Transição documentada")
        self.assertIn(copies[0]["body"][0]["state"], {s["id"] for s in p.states[clone.id]})

    def test_insert_tool_places_component_at_click_and_single_undo_removes_it(self):
        from PySide6.QtCore import QPoint, Qt
        from makebench.editor.window import MainWindow

        p = Project.empty()
        p.root.layout = LayoutKind.FREE
        w = MainWindow(p)
        self.windows.append(w)
        w.show()
        self.app.processEvents()
        w.canvas.set_insert_tool("button")
        frame = w.canvas._frames[p.root.id]
        QTest.mouseClick(
            frame, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(120, 104)
        )
        self.app.processEvents()
        self.assertEqual(len(w.project.root.children), 1)
        node = w.project.root.children[0]
        self.assertEqual((node.geometry["x"], node.geometry["y"]), (120, 104))
        w.undo()
        self.assertEqual(len(w.project.root.children), 0)

    def test_rectangle_selection_and_group_alignment_are_undoable(self):
        from PySide6.QtCore import QPoint, Qt
        from makebench.editor.window import MainWindow

        p = Project.empty()
        p.root.layout = LayoutKind.FREE
        a = p.add(p.root.id, ComponentKind.BUTTON)
        a.geometry.update(x=30, y=30, width=80, height=40)
        b = p.add(p.root.id, ComponentKind.BUTTON)
        b.geometry.update(x=180, y=30, width=80, height=40)
        w = MainWindow(p)
        self.windows.append(w)
        w.show()
        self.app.processEvents()
        frame = w.canvas._frames[p.root.id]
        QTest.mousePress(
            frame, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(5, 5)
        )
        QTest.mouseMove(frame, QPoint(290, 90))
        QTest.mouseRelease(
            frame, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(290, 90)
        )
        self.assertEqual(w.selected_ids, {a.id, b.id})
        self.assertFalse(w.history.dirty)
        w.selection_command("left")
        self.assertEqual(w.project.find(b.id).geometry["x"], 30)
        w.undo()
        self.assertEqual(w.project.find(b.id).geometry["x"], 180)

    def test_layout_handle_commits_one_change_and_undo_restores_default(self):
        from PySide6.QtCore import QPoint, Qt
        from makebench.editor.window import MainWindow

        p = Project.empty()
        p.add(p.root.id, ComponentKind.BUTTON)
        p.add(p.root.id, ComponentKind.BUTTON)
        w = MainWindow(p)
        self.windows.append(w)
        w.show()
        self.app.processEvents()
        QTest.qWait(30)
        handle = next(h for h in w.canvas._layout_handles if h.key == "spacing")
        start = handle.rect().center()
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(handle, start + QPoint(0, 10))
        QTest.mouseRelease(
            handle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start + QPoint(0, 10)
        )
        self.assertEqual(w.project.root.properties["spacing"], 16)
        w.undo()
        self.assertNotIn("spacing", w.project.root.properties)

    def test_specific_state_handler_overrides_generic_handler(self):
        from makebench.core.logic import create_flow
        from makebench.runtime.window import RuntimeWindow

        p = Project.empty()
        b = p.add(p.root.id, ComponentKind.BUTTON)
        state = add_state(p, p.root.id, "Outro")

        def log(identifier, text):
            return {
                "id": identifier,
                "op": "log",
                "value": {"id": identifier + "value", "op": "literal", "value": text},
            }

        create_flow(p, b.id)["body"] = [log("generic", "GENERICO")]
        create_flow(p, b.id, states=[state["id"]])["body"] = [log("specific", "ESPECIFICO")]
        w = RuntimeWindow(p, "", lambda _: b"", self.root)
        self.windows.append(w)
        w.show()
        w.start()
        self.wait(lambda: w.session.active and not w.session.busy)
        w.view.widgets[b.id].click()
        self.wait(lambda: not w.session.busy)
        w.apply_state(p.root.id, state["id"])
        w.view.widgets[b.id].click()
        self.wait(lambda: not w.session.busy)
        self.assertEqual(w.output.toPlainText().count("GENERICO"), 1)
        self.assertEqual(w.output.toPlainText().count("ESPECIFICO"), 1)

    def test_window_scope_initial_values_and_project_scope_survive_events(self):
        from makebench.core.logic import create_flow
        from makebench.runtime.window import RuntimeWindow

        p = Project.empty()
        button = p.add(p.root.id, ComponentKind.BUTTON)
        label = p.add(p.root.id, ComponentKind.LABEL)
        p.variables = [
            {"name": "total", "scope": "project", "initial": 10},
            {"name": "local_da_janela", "scope": "window", "window": p.root.id, "initial": 20},
        ]

        def increment(identifier, name, scope):
            return {
                "id": identifier,
                "op": "assign",
                "scope": scope,
                "name": name,
                "value": {
                    "id": identifier + "sum",
                    "op": "binary",
                    "operator": "+",
                    "left": {
                        "id": identifier + "read",
                        "op": "variable",
                        "scope": scope,
                        "name": name,
                    },
                    "right": {"id": identifier + "one", "op": "literal", "value": 1},
                },
            }

        create_flow(p, button.id)["body"] = [
            increment("global", "total", "project"),
            increment("window", "local_da_janela", "window"),
            {
                "id": "show",
                "op": "set_text",
                "component": label.id,
                "value": {
                    "id": "read_total",
                    "op": "variable",
                    "scope": "window",
                    "name": "local_da_janela",
                },
            },
        ]
        w = RuntimeWindow(p, "", lambda _: b"", self.root)
        self.windows.append(w)
        w.show()
        w.start()
        self.wait(lambda: w.session.active and not w.session.busy)
        for _ in range(2):
            w.view.widgets[button.id].click()
            self.wait(lambda: not w.session.busy)
        self.assertEqual(w.view.widgets[label.id].text(), "22")
        self.assertFalse(w.last_error)


class FinalJourneyTests(unittest.TestCase):
    setUpClass = classmethod(RedesignQtTests.setUpClass.__func__)
    setUp = RedesignQtTests.setUp
    tearDown = RedesignQtTests.tearDown
    wait = RedesignQtTests.wait

    def test_opaque_legacy_flows_open_and_save_without_interpretation(self):
        from makebench.editor.window import MainWindow

        data = Project.empty().to_dict()
        data["workflows"] = [{"extension": "opaque", "blocks": [{"unknown": True}]}]
        p = Project.from_dict(data)
        w = MainWindow(p)
        self.windows.append(w)
        w.show()
        self.app.processEvents()
        w.set_mode("map")
        self.app.processEvents()
        self.assertEqual(w.project.workflows, data["workflows"])
        self.assertTrue(w.save_to(self.root / "legacy.makebench.json"))
        self.assertEqual(
            load_project(self.root / "legacy.makebench.json").workflows, data["workflows"]
        )

    def test_inline_text_cancel_and_confirm_are_single_document_edits(self):
        from PySide6.QtCore import Qt
        from makebench.editor.window import MainWindow
        from makebench.editor.inline import InlineText

        p = Project.empty()
        b = p.add(p.root.id, ComponentKind.BUTTON)
        w = MainWindow(p)
        self.windows.append(w)
        w.show()
        self.app.processEvents()
        w._select(b.id)
        w.rename_selected()
        editor = w.canvas.findChild(InlineText)
        self.assertIsNotNone(editor)
        editor.setText("Cancelar alteração")
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        self.assertEqual(w.project.find(b.id).properties["text"], "New button")
        self.assertFalse(w.history.dirty)
        self.app.processEvents()
        w.rename_selected()
        editor = w.canvas.findChild(InlineText)
        editor.setText("Confirmado")
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.assertEqual(w.project.find(b.id).properties["text"], "Confirmado")
        w.undo()
        self.assertEqual(w.project.find(b.id).properties["text"], "New button")

    def test_admin_task_starting_during_close_does_not_disable_editor(self):
        from types import SimpleNamespace
        from PySide6.QtGui import QCloseEvent
        from makebench.editor.window import MainWindow

        w = MainWindow()
        self.windows.append(w)
        session = SimpleNamespace(admin_active=False, closed=False)
        runtime = SimpleNamespace(session=session, stop=lambda: False)
        w.runtime_window = runtime

        def admin_started():
            session.admin_active = True
            return True

        event = QCloseEvent()
        with patch.object(w, "_confirm_discard", side_effect=admin_started):
            w.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(w.isEnabled())
        self.assertFalse(w._closing_after_runtime)
        w.runtime_window = None

    def test_app_configuration_is_v5_and_noop_save_preserves_source_mtime(self):
        from makebench.editor.window import MainWindow

        w = MainWindow()
        self.windows.append(w)
        w.project.application = {"name": "App", "version": "0.1.0", "id": "br.exemplo.app"}
        path = self.root / "project.makebench.json"
        self.assertTrue(w.save_to(path))
        source = path.with_name("project.actions.py")
        original = source.stat().st_mtime_ns
        self.assertTrue(w.save_to(path))
        self.assertEqual(source.stat().st_mtime_ns, original)
        self.assertEqual(load_project(path).application["name"], "App")
        self.assertEqual(load_project(path).to_dict()["format_version"], 5)
