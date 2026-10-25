"""Aceitação da reformulação com widgets reais, miniaturas nativas e workspace Blockly."""

import argparse
import json
import os
from pathlib import Path
import tempfile
import time


def main():
    """Percorre Mapa/Design/Lógica/Código e configurações sem usar projetos do proprietário."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("qt", "gtk"), default="qt")
    parser.add_argument("--theme", choices=("light", "dark"), default="dark")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="makebench-ux-qa-") as directory:
        root = Path(directory)
        os.environ["XDG_CONFIG_HOME"] = str(root / "config")
        os.environ["XDG_STATE_HOME"] = str(root / "state")
        from PySide6.QtCore import Qt, QTimer, QEventLoop, QCoreApplication, QEvent, QPoint, QPointF
        from PySide6.QtGui import QTextCursor
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QDialog, QComboBox, QLineEdit

        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        from native_palette import kde_palette

        app.setPalette(kde_palette(args.theme))
        from makebench.core.project import Project, ComponentKind
        from makebench.core.navigation import add_window, add_state, find_navigation_block
        from makebench.editor.window import MainWindow
        from makebench.editor.theme import manager

        project = Project.empty("Fluxo de acesso")
        project.application = {
            "name": project.name,
            "id": "br.exemplo.fluxo",
            "version": "0.1.0",
            "backend": args.backend,
        }
        project.root.properties.update(title="Entrar", width=620, height=420)
        title = project.add(project.root.id, ComponentKind.LABEL)
        title.properties["text"] = "Acesse seu painel"
        field = project.add(project.root.id, ComponentKind.TEXT_INPUT)
        field.properties["placeholder"] = "Seu nome"
        button = project.add(project.root.id, ComponentKind.BUTTON)
        button.properties.update(text="Entrar", tooltip="Abrir painel principal")
        state = add_state(project, project.root.id, "Entrada inválida")
        state["overrides"] = {title.id: {"text": "Preencha seu nome"}}
        other = add_window(project, "Painel principal")
        project.add(other.id, ComponentKind.LABEL).properties["text"] = "Seja bem-vindo ao painel"
        window = MainWindow(project)
        window.recovery_timer.stop()
        window.show()
        manager().set_mode(args.theme)
        results = []

        def wait(predicate, seconds=20):
            """Espera condições observáveis mantendo a fila de eventos responsiva."""
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                QTest.qWait(20)
                if predicate():
                    return
            errors = [
                node.preview_error for node in window.map_panel.nodes.values() if node.preview_error
            ]
            raise AssertionError("Prazo excedido. " + str(errors) + window.logic.diagnostics.text())

        def js(source):
            """Consulta somente a página Blockly incorporada para verificar dados e seleção."""
            loop = QEventLoop()
            values = []

            def done(value):
                """Conclui uma consulta de dados ao navegador local."""
                values.append(value)
                loop.quit()

            window.logic.page.runJavaScript(source, done)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            assert values, "JavaScript sem resposta"
            return values[0]

        def capture(name, widget=None):
            """Registra a própria janela testada, sem compor uma imagem artificial."""
            QTest.qWait(80)
            (widget or window).grab().save(str(args.output / (name + ".png")))

        def check(label, callback):
            """Cada etapa registra resultado real, sem continuar em estado inconsistente."""
            started = time.monotonic()
            callback()
            results.append(
                {"scenario": label, "ok": True, "seconds": round(time.monotonic() - started, 3)}
            )

        marker = root / "executed"
        source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('execução explícita')\n\ndef minha_funcao(ctx, valor):\n    return valor\n"
        window.source_editor.setPlainText(source)

        def thumbnails():
            """Miniaturas contêm os controles, distinguem estados e não executam fonte própria."""
            window.set_mode("Mapa")
            wait(
                lambda: (
                    len(window.map_panel.nodes) == 3
                    and all(not n.thumbnail.isNull() for n in window.map_panel.nodes.values())
                )
            )
            window.map_panel.fit()
            assert not marker.exists()
            capture("01-mapa")
            first = window.map_panel.nodes[project.root.id + "|@default"]
            second = window.map_panel.nodes[project.root.id + "|" + state["id"]]
            assert first.thumbnail.toImage() != second.thumbnail.toImage()

        def designer_map_update():
            """Uma propriedade invalida só a miniatura, preservando cartões e a janela nativa."""
            node = window.map_panel.nodes[project.root.id + "|@default"]
            image = node.thumbnail.toImage()
            native = window.winId()
            window.activate_window(project.root.id)
            window.set_mode("Design")
            window._select(button.id)
            inspector_field = window.inspector.findChild(QLineEdit, "property_text")
            window._change_property(button.id, "text", "Abrir meu painel")
            assert window.inspector.findChild(QLineEdit, "property_text") is inspector_field
            assert window.winId() == native

            if args.backend == "gtk":
                wait(
                    lambda: (
                        getattr(window.canvas.gtk_surface, "rendered_version", None)
                        == window.canvas.gtk_surface.version
                        and window.canvas.gtk_surface.job is None
                    )
                )
            capture("02-design")
            window.left_tabs.setCurrentIndex(1)
            window.insert_category.setCurrentIndex(2)
            window.insert_search.setText("texto")
            assert any(not window.palette.item(i).isHidden() for i in range(window.palette.count()))
            capture("03-biblioteca")
            window.insert_search.clear()
            window.insert_category.setCurrentIndex(0)
            window.set_mode("Mapa")
            wait(lambda: node.thumbnail.toImage() != image)
            assert window.map_panel.nodes[node.key] is node
            assert not marker.exists()

        def select_open():
            """Clique inspeciona e duplo clique abre exatamente a janela e estado escolhidos."""
            node = window.map_panel.nodes[project.root.id + "|" + state["id"]]
            point = window.map_panel.view.mapFromScene(node.sceneBoundingRect().center())
            QTest.mouseClick(window.map_panel.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
            QTest.qWait(80)
            assert window._mode == "Mapa"
            assert window.map_panel.details.isVisible()
            capture("04-mapa-interface")
            point = window.map_panel.view.mapFromScene(node.sceneBoundingRect().center())
            QTest.mouseDClick(
                window.map_panel.view.viewport(), Qt.MouseButton.LeftButton, pos=point
            )
            QTest.mouseRelease(
                window.map_panel.view.viewport(), Qt.MouseButton.LeftButton, pos=point
            )
            wait(lambda: window._mode == "Design")
            assert window.active_state == state["id"]
            assert window.active_window == project.root.id
            window.activate_window(project.root.id)
            window.set_mode("Mapa")

        def map_gestures():
            """Arraste, histórico, grupos e organização não mudam os comportamentos do app."""
            window.map_panel.details.hide()
            window.map_panel.fit()
            QTest.qWait(app.doubleClickInterval() + 30)
            view = window.map_panel.view
            key = project.root.id + "|@default"
            node = window.map_panel.nodes[key]
            start = view.mapFromScene(node.scenePos() + QPointF(50, 30))
            delta = QPoint(30, 25)
            assert view.viewport().rect().contains(start), (start, view.viewport().rect())
            assert view.node_at(start) is node, (start, view.itemAt(start))
            QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
            for step in range(1, 5):
                QTest.mouseMove(view.viewport(), start + delta * step / 4)
                QTest.qWait(20)
            QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=start + delta)
            wait(lambda: key in window.project.map_layout)
            moved = window.project.map_layout[key]
            assert moved != [0, 0]
            assert (
                abs(moved[0] - delta.x() / view.transform().m11()) < 2
                and abs(moved[1] - delta.y() / view.transform().m11()) < 2
            ), moved
            window.undo()
            assert key not in window.project.map_layout
            window.redo()
            assert window.project.map_layout[key] == moved
            before = window.project.workflows[:]
            window.map_panel.organize()
            assert window.project.workflows == before
            window.map_panel.toggle_group(project.root.id)
            assert len(window.map_panel.nodes) == 2
            window.map_panel.toggle_group(project.root.id)
            assert len(window.map_panel.nodes) == 3
            window.map_panel.fit()

        def connection():
            """O diálogo cria uma ligação executável, que também é editável e reversível."""

            def accept():
                """Confirma o evento escolhido no diálogo aberto pelo gesto da porta."""
                dialog = app.activeModalWidget()
                assert isinstance(dialog, QDialog)
                dialog.findChild(QComboBox, "transition_event").setCurrentIndex(
                    dialog.event.findData(button.id)
                )
                dialog.accept()

            view = window.map_panel.view
            origin = window.map_panel.nodes[project.root.id + "|@default"]
            destination = window.map_panel.nodes[other.id + "|@default"]
            start = view.mapFromScene(origin.scenePos() + QPointF(300, 126))
            end = view.mapFromScene(destination.sceneBoundingRect().center())
            QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(view.viewport(), end)
            QTimer.singleShot(400, accept)
            QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
            wait(lambda: len(window.project.workflows) == 1)
            edge = window.map_panel.edges[0]
            points = [
                view.mapFromScene(edge.path().pointAtPercent(value)) for value in (0.25, 0.5, 0.75)
            ]
            point = next((point for point in points if view.itemAt(point) is edge), None)
            assert point is not None, "Ligação sem trecho acessível ao clique"
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
            assert edge.isSelected()
            capture("05-transicao")
            assert window.map_panel.details.isVisible()
            flow = window.project.workflows[0]
            assert flow["body"][0]["op"] == "open_window"

            def edit():
                """Altera a navegação no editor nativo de transição."""
                dialog = app.activeModalWidget()
                dialog.target.setCurrentIndex(
                    dialog.target.findData(project.root.id + "|" + state["id"])
                )
                dialog.accept()

            QTimer.singleShot(60, edit)
            window.map_panel.edit_edge(edge.edge)
            assert window.project.workflows[0]["body"][0]["op"] == "go_state"
            window.undo()
            assert window.project.workflows[0]["body"][0]["op"] == "open_window"
            window.navigate_to_item("flow", flow["id"])
            wait(lambda: window.logic.ready)
            assert window.logic.context_label.text().startswith("Quando clicar")

        def blocks_code():
            """Modelo real, workspace, comentários e código usam o mesmo bloco e origem."""
            flow = window.project.workflows[0]
            window.insert_behavior("read_field")
            wait(
                lambda: js("!!window.makebench.workspace.getBlocksByType('mb_assign',false).length")
            )
            assert window.logic.flush()
            assert window.project.workflows[0]["body"][-1]["value"]["component"] == field.id
            capture("06-logica")
            window.python_action.setChecked(True)
            capture("07-logica-python")
            block = window.project.workflows[0]["body"][0]
            line = window.logic.generated.lines[(flow["id"], block["id"])]
            window.show_generated_line(line)
            capture("08-codigo-gerado")
            window.generated_origin(line)
            assert window._mode == "Lógica"
            assert window.logic.flow_id == flow["id"]
            window.logic.show_origin()
            assert window._mode == "Design"
            assert window.selected_id == button.id
            window.set_mode("Código")
            window.code_files.setCurrentIndex(1)
            window.source_editor.find_text.setText("minha_funcao")
            window.source_editor.replace_text.setText("funcao_propria")
            window.source_editor.replace_all()
            assert "def funcao_propria" in window.source.text
            assert window.source.dirty
            assert window.function_outline.count() == 1
            window.source_editor.open_replace()
            capture("09-codigo-proprio")
            window.source_editor.close_find()
            path = root / "project.makebench.json"
            assert window.save_to(path)
            window._replace_project(
                __import__("makebench.core.storage", fromlist=["load_project"]).load_project(path),
                path,
            )
            assert "funcao_propria" in window.source.text
            assert len(window.project.workflows[0]["body"]) == 2
            assert not marker.exists()

        def execution_drawer():
            """F5 é a primeira execução da fonte; tarefas, filtros e cancelamento são observados."""
            from makebench.core.logic_defaults import default_block, literal
            from makebench.core.behaviors import append_behavior

            flow = window.project.workflows[0]
            task = default_block("script", window.project, project.root.id)
            task["source"] = literal(
                'printf "saída real\\n"; printf "aviso real\\n" >&2; sleep 0.2'
            )
            window._edit(lambda: append_behavior(flow, [task]))
            assert not marker.exists()
            window._trusted_session = True
            window.refresh_trust_banner()
            window.run_project()
            wait(lambda: window.runtime_window is not None and window.runtime_window.session.active)
            wait(marker.exists)
            runtime = window.runtime_window
            if args.backend == "qt":
                runtime.view.widgets[button.id].click()
            else:
                runtime.command({"command": "click", "component": button.id})
            wait(
                lambda: (
                    any("aviso real" in text for channel, text in window.log_entries)
                    and not runtime.session.busy
                )
            )
            assert window.task_tree.topLevelItemCount() == 1
            assert window.task_tree.topLevelItem(0).text(2) == "Concluído"
            assert "PID" in window.process_info.text()
            window.output_filter.setCurrentIndex(window.output_filter.findData("stderr"))
            assert "aviso real" in window.output_log.toPlainText()
            assert "saída real" not in window.output_log.toPlainText()
            assert [
                window.drawer.tabText(i).split(" (")[0] for i in range(window.drawer.count())
            ] == ["Saída", "Problemas", "Script", "Tarefas", "Erro"]
            window.output_filter.setCurrentIndex(0)
            window.drawer.setCurrentIndex(0)
            assert window.output_log.isVisible()
            capture("14-saida")
            window.drawer.setCurrentIndex(3)
            assert window.task_tree.isVisible()
            capture("15-tarefas")
            window.drawer.setCurrentIndex(1)
            assert window.problems.isVisible()
            capture("16-problemas")
            window.drawer.setCurrentIndex(2)
            assert window.script_editor.isVisible()
            capture("17-scripts")
            window.clear_output()
            assert window.output_log.toPlainText() == ""
            window.stop_test()
            wait(lambda: runtime.session.closed)
            assert "encerrada" in window.process_info.text()
            window.drawer.hide()

        def settings():
            """Valida identidade, exibe páginas e mantém preferências fora do documento."""
            from makebench.editor.settings import ApplicationSettings, EditorPreferences

            dialog = ApplicationSettings(window)
            dialog.show()
            original = window.project.application["id"]
            dialog.change("id", "invalido")
            assert window.project.application["id"] == original
            assert dialog.identity_notice.text()
            dialog.change("id", original)
            for index in range(dialog.sections.count()):
                dialog.sections.setCurrentRow(index)
                capture("10-config-" + str(index), dialog)
            dialog.close()
            dialog = EditorPreferences(window)
            dialog.show()
            for index in range(dialog.sections.count()):
                dialog.sections.setCurrentRow(index)
                capture("11-preferencias-" + str(index), dialog)
            dialog.close()
            window.export_application()
            window.publish_panel.check()
            capture("12-exportacao", window.publish_dialog)
            window.publish_dialog.hide()

        try:
            for label, operation in [
                ("miniaturas nativas e prévia inerte", thumbnails),
                ("propriedade → miniatura sem reconstruir mapa", designer_map_update),
                ("seleção e duplo clique no estado", select_open),
                ("arraste, histórico, grupos e organização do mapa", map_gestures),
                ("criar/editar/desfazer transição real", connection),
                ("modelos → Blockly → Python → origem → salvar/reabrir", blocks_code),
                ("execução explícita, tarefas e filtros da gaveta", execution_drawer),
                ("configurações, preferências e exportação", settings),
            ]:
                check(label, operation)
            window.resize(1000, 640)
            window.set_mode("Mapa")
            window.map_panel.fit()
            capture("13-janela-menor")
            assert window.mode_buttons["Mapa"].isVisible()
        finally:
            report = {
                "platform": app.platformName(),
                "backend": args.backend,
                "theme": args.theme,
                "scale": window.devicePixelRatioF(),
                "results": results,
            }
            (args.output / "results.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2)
            )
            window.history.mark_saved()
            window.source.mark_saved()
            window.close()
            if window.logic.view:
                window.logic.page.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            window.deleteLater()
            app.processEvents()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
