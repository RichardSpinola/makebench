# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable block contract: references, generation and source preservation."""

import support  # noqa: F401  (first: isolates settings and data)
import ast
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from makebench.core.codegen import generate
from makebench.core.logic import create_flow, validate, function_names
from makebench.core.project import ComponentKind, Project, ProjectError
from makebench.core.source import SourceBuffer, source_path
from makebench.core.storage import load_project, save_project


def literal(identifier, value):
    return {"id": identifier, "op": "literal", "value": value}


class LogicTests(unittest.TestCase):
    def setUp(self):
        self.project = Project.empty()
        self.button = self.project.add(self.project.root.id, ComponentKind.BUTTON)
        self.flow = create_flow(self.project, self.button.id)

    def test_binding_roundtrip_and_old_versions(self):
        self.assertIs(create_flow(self.project, self.button.id), self.flow)
        data = self.project.to_dict()
        self.assertEqual(Project.from_dict(data).to_dict(), data)
        for version in (1, 2):
            legacy = Project.empty().to_dict()
            legacy["format_version"] = version
            legacy["workflows"] = [{"extension": "opaque", "blocks": [{"unknown": True}]}]
            result = Project.from_dict(legacy)
            self.assertEqual(result.workflows, legacy["workflows"])
            with self.assertRaises(ProjectError):
                create_flow(result, result.root.id)

    def test_validation_rejects_wrong_event_target_and_unknown_versions(self):
        data = self.project.to_dict()
        data["workflows"][0]["event"]["component"] = "missing"
        with self.assertRaises(ProjectError):
            Project.from_dict(data)
        data = self.project.to_dict()
        data["metadata"]["logic_version"] = 2
        with self.assertRaises(ProjectError):
            Project.from_dict(data)

    def test_removal_checks_references_and_duplicate_remaps_only_internal_targets(self):
        label = self.project.add(self.project.root.id, ComponentKind.LABEL)
        group = self.project.add(self.project.root.id, ComponentKind.CONTAINER)
        self.project.move(self.button.id, group.id)
        own_label = self.project.add(group.id, ComponentKind.LABEL)
        self.flow["body"] = [
            {
                "id": "s1",
                "op": "set_text",
                "component": own_label.id,
                "value": literal("v1", "Interno"),
            },
            {
                "id": "s2",
                "op": "set_text",
                "component": label.id,
                "value": literal("v2", "Externo"),
            },
        ]
        copy = self.project.duplicate(group.id)
        copied = self.project.workflows[1]
        self.assertEqual(copied["event"]["component"], copy.children[0].id)
        self.assertEqual(copied["body"][0]["component"], copy.children[1].id)
        self.assertEqual(copied["body"][1]["component"], label.id)
        self.assertNotEqual(copied["body"][0]["id"], "s1")
        validate(self.project)
        with self.assertRaises(ProjectError):
            self.project.remove(label.id)
        spare = self.project.add(self.project.root.id, ComponentKind.LABEL)
        self.project.remove(spare.id)
        self.project.workflows = []
        self.project.remove(group.id)

    def test_python_events_are_validated_created_and_converted(self):
        from makebench.core.codegen import convert_to_python, generate
        from makebench.core.logic import create_python_event, guard_removal, is_draft

        project = Project.empty()
        button = project.add(project.root.id, ComponentKind.BUTTON)
        button.properties["text"] = "Salvar já"
        project.metadata["programming"] = "python"
        flow, source = create_python_event(
            project, button.id, "def on_salvar_ja_click():\n    pass\n"
        )
        self.assertEqual(flow["function"], "on_salvar_ja_click_2")
        self.assertIn("def on_salvar_ja_click_2(ctx):", source)
        self.assertFalse(is_draft(flow))
        self.assertEqual(create_python_event(project, button.id, source), (flow, source))
        validate(project)
        self.assertIn("ctx.handle_event('on_salvar_ja_click_2')", generate(project, source).text)
        with self.assertRaises(ProjectError):
            guard_removal(project, {button.id})
        flow["function"] = "not a name"
        with self.assertRaisesRegex(ProjectError, "Python name"):
            validate(project)
        flow["function"] = "ok"
        flow["body"] = []
        with self.assertRaisesRegex(ProjectError, "blocks"):
            validate(project)

        blocks = Project.empty()
        create_flow(blocks, blocks.root.id)["body"] = None
        blocks.workflows[0]["workspace"] = {"blocks": {}}
        with self.assertRaisesRegex(ProjectError, "Finish"):
            convert_to_python(blocks, "")

    def test_generated_control_flow_is_valid_and_has_source_map(self):
        self.flow["body"] = [
            {
                "id": "a",
                "op": "assign",
                "name": "counter",
                "value": literal("n", 0),
                "comment": "Contar mensagens",
            },
            {
                "id": "r",
                "op": "repeat",
                "count": literal("times", 3),
                "body": [
                    {
                        "id": "a2",
                        "op": "assign",
                        "name": "counter",
                        "value": {
                            "id": "sum",
                            "op": "binary",
                            "operator": "+",
                            "left": {"id": "v", "op": "variable", "name": "counter"},
                            "right": literal("one", 1),
                        },
                    }
                ],
            },
            {
                "id": "if",
                "op": "if",
                "condition": {
                    "id": "cmp",
                    "op": "binary",
                    "operator": "==",
                    "left": {"id": "v2", "op": "variable", "name": "counter"},
                    "right": literal("three", 3),
                },
                "then": [{"id": "ok", "op": "log", "value": literal("done", "Completed")}],
                "else": [{"id": "fail", "op": "message", "value": literal("bad", "Falhou")}],
            },
        ]
        generated = generate(self.project)
        ast.parse(generated.text)

        class Context:
            variables = {}
            output = []

            def log(ctx, value):
                ctx.output.append(value)

            def message(ctx, value):
                ctx.output.append(value)

        # Runs only the test fixture built above, never an opened project.
        namespace = {}
        exec(generated.text, namespace)
        ctx = Context()
        namespace["on_event_1"](ctx)
        self.assertEqual(ctx.variables["counter"], 3)
        self.assertEqual(ctx.output, ["Completed"])
        self.assertIn("# Contar mensagens", generated.text)
        line = generated.lines[(self.flow["id"], "ok")]
        self.assertEqual(generated.lines[(self.flow["id"], "done")], line)
        self.assertIn("ctx.log('Completed')", generated.text.splitlines()[line - 1])

    def test_literals_and_variable_names_cannot_inject_python(self):
        hostile = "x'); __import__('os').system('false') #\n"
        self.flow["name"] = "nome\ndef injection(): pass\r"
        self.flow["body"] = [
            {"id": "s", "op": "assign", "name": hostile, "value": literal("v", hostile)}
        ]
        generated = generate(self.project)
        tree = ast.parse(generated.text)
        self.assertEqual(len([n for n in tree.body if isinstance(n, ast.FunctionDef)]), 1)
        self.flow["body"] = [
            {"id": "s", "op": "call", "function": hostile, "value": literal("v", "")}
        ]
        with self.assertRaises(ProjectError):
            generate(self.project)

    def test_invalid_references_and_duplicate_ids_rejected(self):
        self.flow["body"] = [
            {"id": "s", "op": "set_text", "component": "missing", "value": literal("v", "")}
        ]
        with self.assertRaises(ProjectError):
            validate(self.project)
        self.flow["body"] = [{"id": "s", "op": "log", "value": literal("s", "")}]
        with self.assertRaises(ProjectError):
            validate(self.project)

    def test_incomplete_draft_preserves_workspace_and_never_generates_handler(self):
        self.flow.update(
            body=None,
            workspace={
                "blocks": {"blocks": [{"type": "mb_log", "id": "pending"}]},
                "workspaceComments": [{"text": "Revisar"}],
            },
            errors=["Falta uma entrada."],
        )
        restored = Project.from_dict(self.project.to_dict())
        self.assertEqual(restored.workflows, self.project.workflows)
        generated = generate(restored)
        self.assertNotIn("def on_event", generated.text)
        self.assertIn("Falta uma entrada.", generated.diagnostics[0])

    def test_functions_are_inspected_without_import_and_syntax_errors_are_reported(self):
        names, error = function_names(
            "raise RuntimeError('Não executar')\ndef teste(ctx, valor):\n    return valor\n"
        )
        self.assertEqual(names, ["teste"])
        self.assertIsNone(error)
        self.flow["body"] = [
            {"id": "call", "op": "call", "function": "missing", "value": literal("arg", "Oi")}
        ]
        self.assertIn("not found", generate(self.project).diagnostics[0])
        self.assertIsNotNone(function_names("def broken(")[1])


class SourceTests(unittest.TestCase):
    def test_source_survives_regeneration_save_as_and_external_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project.makebench.json"
            source = SourceBuffer.load(path)
            text = "# meu comentário\nraise RuntimeError('nunca importar')\ndef minha(ctx, valor):\n    return valor\n"
            source.text = text
            source.write(path)
            source.mark_saved()
            self.assertFalse(source.dirty)
            project = Project.empty()
            create_flow(project, project.root.id)
            generate(project, text)
            save_project(project, path)
            self.assertEqual(SourceBuffer.load(path).text, text)
            other = Path(temp) / "copy.makebench.json"
            source.write(other)
            source.mark_saved()
            self.assertEqual(source_path(other).read_text(), text)
            source_path(other).write_text("# edição externa\n")
            source.text += "# edição interna\n"
            with self.assertRaisesRegex(ProjectError, "changed outside"):
                source.write(other)
            self.assertEqual(source_path(other).read_text(), "# edição externa\n")
            self.assertTrue(source.dirty)

    def test_save_as_conflict_symlink_and_missing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project.makebench.json"
            source = SourceBuffer.load(path)
            self.assertIsNone(source.original)
            target = source_path(path)
            target.write_text("externo")
            with self.assertRaises(ProjectError):
                source.write(path)
            target.unlink()
            outside = Path(temp) / "external.py"
            outside.write_text("outside")
            target.symlink_to(outside)
            with self.assertRaises(ProjectError):
                SourceBuffer.load(path)
            with self.assertRaises(ProjectError):
                source.write(path)
            self.assertEqual(outside.read_text(), "outside")

    def test_invalid_python_is_preserved_as_text(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "a.makebench.json"
            source = SourceBuffer.load(path)
            source.text = "def unfinished(\n"
            source.write(path)
            self.assertEqual(SourceBuffer.load(path).text, source.text)
