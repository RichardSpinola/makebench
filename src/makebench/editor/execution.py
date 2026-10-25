"""Supervisão do teste na gaveta do editor, utilizando sinais do runtime real."""

from datetime import datetime
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from makebench.runtime.window import append_output
from .theme import manager


class ExecutionMixin:
    """Apresenta logs, tarefas e origem sem executar código no processo do editor."""

    def install_execution(self):
        """Acrescenta filtros e comandos sobre o mesmo log compartilhado."""
        self.log_entries = []
        self.task_items = {}
        self.task_running = {}
        self.test_started = None
        # Remover antes de reparentear evita deslocar e apagar a aba Problemas.
        self.drawer.removeTab(self.drawer.indexOf(self.output_log))
        self.drawer.setMinimumHeight(145)
        output = QWidget()
        layout = QVBoxLayout(output)
        layout.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.output_filter = QComboBox()
        for label, key in [
            ("Tudo", None),
            ("Saída padrão", "stdout"),
            ("Avisos / stderr", "stderr"),
            ("Erros", "error"),
            ("Execução", "status"),
        ]:
            self.output_filter.addItem(label, key)
        self.output_filter.currentIndexChanged.connect(self.rebuild_output)
        row.addWidget(self.output_filter)
        self.process_info = QLabel("Nenhum teste iniciado")
        row.addWidget(self.process_info, 1)
        for label, callback in [
            (
                "Copiar",
                lambda: (
                    __import__("PySide6.QtWidgets", fromlist=["QApplication"])
                    .QApplication.clipboard()
                    .setText(self.output_log.toPlainText())
                ),
            ),
            ("Limpar", self.clear_output),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(self.output_log, 1)
        self.output_log.show()
        self.drawer.insertTab(0, output, "Saída")
        tasks = QWidget()
        tl = QVBoxLayout(tasks)
        self.task_tree = QTreeWidget()
        self.task_tree.setHeaderLabels(["Tarefa", "Tipo", "Estado", "Duração"])
        tl.addWidget(self.task_tree)
        self.task_empty = QLabel(
            "As tarefas iniciadas pelo aplicativo aparecem aqui, com resultado e duração."
        )
        self.task_empty.setWordWrap(True)
        tl.addWidget(self.task_empty)
        self.cancel_task_button = QPushButton("Cancelar tarefa comum e encerrar teste")
        self.cancel_task_button.setEnabled(False)
        self.cancel_task_button.clicked.connect(self.stop_test)
        tl.addWidget(self.cancel_task_button)
        self.drawer.addTab(tasks, "Tarefas")
        error = QWidget()
        er = QVBoxLayout(error)
        self.run_error_label = QLabel()
        self.run_error_label.setWordWrap(True)
        er.addWidget(self.run_error_label)
        locate = QPushButton("Ir à origem")
        locate.clicked.connect(self.locate_test_error)
        er.addWidget(locate, 0, Qt.AlignmentFlag.AlignLeft)
        details = QPushButton("Detalhes técnicos")
        details.setCheckable(True)
        er.addWidget(details, 0, Qt.AlignmentFlag.AlignLeft)
        self.run_trace = QPlainTextEdit()
        self.run_trace.setReadOnly(True)
        self.run_trace.hide()
        details.toggled.connect(self.run_trace.setVisible)
        er.addWidget(self.run_trace)
        self.drawer.addTab(error, "Erro")
        from makebench.terminal.qt import TerminalPanel

        self.terminal_panel = TerminalPanel(self)
        from pathlib import Path

        self.terminal_panel.directory_provider = lambda: (
            self.path.parent if self.path else Path.home()
        )
        self.drawer.addTab(self.terminal_panel, "Terminal")
        from .debug import DebugPanel

        self.debug_panel = DebugPanel(self)
        self.drawer.addTab(self.debug_panel, "Depurar")
        self.debug_panel.command.connect(self.debug_command)
        self.debug_panel.locate.connect(self.locate_debug)
        self.source_editor.breakpoints_enabled = True
        self.generated_editor.breakpoints_enabled = True
        self.source_editor.breakpoint_requested.connect(self.toggle_source_breakpoint)
        self.generated_editor.breakpoint_requested.connect(self.toggle_generated_breakpoint)
        self.logic.breakpoint_requested.connect(self.toggle_block_breakpoint)
        self._next_debug = False
        self._debug_restart = False

        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self.update_test_time)
        self.clock.start()
        self._runtime_project_fingerprint = None
        self._debug_active = False
        manager().changed.connect(self.rebuild_output)

    def execution_fingerprint(self):
        """Compara código e documento do snapshot, excluindo marcas de depuração."""
        import hashlib, json

        data = self.project.to_dict()
        data["metadata"].pop("debug_breakpoints", None)
        from makebench.core.source import source_signature

        return hashlib.sha256(
            (json.dumps(data, sort_keys=True) + repr(source_signature(self.source.text))).encode()
        ).hexdigest()

    def monitor_runtime(self, window):
        """Conecta um processo real antes de seu início explícito."""
        from .settings import preference

        if preference("test/clear"):
            self.clear_output()
        self.run_number += 1
        self.test_started = time.monotonic()
        self._runtime_project_fingerprint = self.execution_fingerprint()
        self.process_info.setText(f"Execução {self.run_number} · {datetime.now():%H:%M:%S}")
        self.task_empty.setVisible(not self.task_items)
        self.add_output(
            "status",
            f"\n──────── Execução {self.run_number} · {datetime.now():%H:%M:%S} ────────\n",
        )
        process = getattr(window.session, "process", None) or getattr(window, "process", None)
        if process:
            process.started.connect(
                lambda: self.process_info.setText(
                    f"Execução {self.run_number} · Python · PID {process.processId()}"
                )
            )
        if self._debug_active:
            self.debug_panel.changed({"state": "running"})
        window.session.debug_changed.connect(self.debug_changed)
        window.session.output.connect(self.add_output)
        window.session.busy_changed.connect(lambda _: self._update_actions())
        window.session.error.connect(self.show_test_error)
        window.status_changed.connect(self.set_test_status)
        window.session.task_changed.connect(self.update_task)
        window.session.admin_changed.connect(lambda active: self.stop_action.setEnabled(not active))
        window.session.stopped.connect(self.runtime_stopped)
        self.drawer.show()
        self.drawer.setCurrentIndex(0)

    def debug_project(self):
        """Inicia novo snapshot depurável por ação separada de Executar."""
        self._next_debug = True
        self.run_project()

    def debug_command(self, action):
        """Envia somente controles conhecidos ao processo proprietário do snapshot."""
        window = self.runtime_window
        if window is None or window.session.closed:
            return
        if action == "stop":
            self.stop_test()
            return
        window.session.debug_command(action)

    def breakpoints(self):
        """Lê marcas declarativas do projeto, sem executá-las ao abrir."""
        return self.project.metadata.get("debug_breakpoints", [])

    def toggle_source_breakpoint(self, line, path="@actions"):
        """Alterna uma linha própria e atualiza o worker se houver depuração ativa."""
        self._toggle_breakpoint(
            {"file": "source", "line": line, **({"path": path} if path != "@actions" else {})}
        )

    def toggle_generated_breakpoint(self, line):
        """Resolve linha gerada para o ID original em vez de armazenar linha instável."""
        key = next(
            (key for key, number in self.logic.generated.lines.items() if number == line), None
        )
        if key:
            self.toggle_block_breakpoint(*key)

    def toggle_block_breakpoint(self, flow, block):
        """Armazena origem por ID para preservar pontos entre salvamentos."""
        self._toggle_breakpoint({"file": "block", "flow": flow, "block": block})

    def _toggle_breakpoint(self, point):
        """Altera marcas por transação, preservando histórico e workspace Blockly."""
        points = [dict(p) for p in self.breakpoints()]
        if point in points:
            points.remove(point)
        else:
            points.append(point)
        self._edit(lambda: self.project.metadata.update(debug_breakpoints=points), refresh=False)
        self.sync_breakpoints()
        window = self.runtime_window
        if window and not window.session.closed:
            window.session.debug_command("breakpoints", items=points)

    def sync_breakpoints(self):
        """Atualiza margens sem reconstruir o código nem os controles do Designer."""
        if not hasattr(self, "debug_panel"):
            return
        points = self.breakpoints()
        self.source_editor.breakpoints = {
            p["line"]
            for p in points
            if p.get("file") == "source"
            and p.get("path", "@actions") == "@actions"
            and type(p.get("line")) is int
        }
        for name, editor in getattr(self, "module_editors", {}).items():
            editor.breakpoints = {
                p["line"] for p in points if p.get("file") == "source" and p.get("path") == name
            }
            editor.numbers.update()
        block_keys = {(p.get("flow"), p.get("block")) for p in points if p.get("file") == "block"}
        blocks = {block for flow, block in block_keys if flow == self.logic.flow_id}
        self.generated_editor.breakpoints = {
            line
            for (flow, block), line in self.logic.generated.lines.items()
            if (flow, block) in block_keys
        }
        self.source_editor.numbers.update()
        self.generated_editor.numbers.update()
        self.logic.graph_panel.breakpoints = blocks
        for card in self.logic.graph_panel.cards.values():
            card.update()
        if self.logic.ready and self.logic.editor_kind.currentData() != "nodes":
            self.logic.page.runJavaScript(
                "window.makebench.setBreakpoints(" + __import__("json").dumps(list(blocks)) + ")"
            )

    def debug_changed(self, message):
        """Exibe observações do snapshot e destaca sua origem sem editar o projeto."""
        message = dict(message)
        window = self.runtime_window
        if window:
            component = window.project.find(message.get("component"))
            flow = next(
                (f for f in window.project.workflows if f["id"] == message.get("flow")), None
            )
            if component:
                message["component_label"] = component.display_name
            if flow:
                message["flow_label"] = flow["name"]
        self.debug_panel.changed(message)
        if message.get("state") != "paused":
            for card in self.logic.graph_panel.cards.values():
                card.active = False
                card.update()
        if message.get("state") == "paused":
            self.test_status.setText("Pausado")
            self.drawer.show()
            self.drawer.setCurrentWidget(self.debug_panel)
            self.locate_debug(message)

    def locate_debug(self, message):
        """Navega somente se a origem ainda corresponde ao documento em edição."""
        window = self.runtime_window
        if not window or self.project.id != window.project.id:
            return
        if self.execution_fingerprint() != self._runtime_project_fingerprint:
            self.debug_panel.status.setText(
                "Snapshot pausado · projeto alterado; reinicie para aplicar as mudanças."
            )
            return
        if message.get("source_line"):
            self.open_code_file(message.get("source_file", "@actions"), message["source_line"])
        elif message.get("block"):
            self.set_mode("Lógica")
            self.logic.focus_block(message["flow"], message["block"])

    def add_output(self, channel, text):
        """Mantém canais separados; stderr é aviso, falha explícita é erro."""
        self.log_entries.append((channel, text))
        if sum(len(t) for _, t in self.log_entries) > 500000:
            self.log_entries = self.log_entries[-1000:]
        if self.output_filter.currentData() is None or channel == self.output_filter.currentData():
            tokens = manager().tokens
            color = (
                tokens["warning"]
                if channel == "stderr"
                else tokens["error"]
                if channel == "error"
                else tokens["muted"]
                if channel == "status"
                else None
            )
            append_output(self.output_log, text, color)

    def rebuild_output(self):
        """Filtra a apresentação, preservando o histórico recebido."""
        entries = list(self.log_entries)
        self.output_log.clear()
        self.log_entries = []
        for channel, text in entries:
            self.add_output(channel, text)

    def clear_output(self):
        """Limpa somente a observação da execução, sem apagar arquivos ou lógica."""
        self.log_entries = []
        self.output_log.clear()

    def update_task(self, data):
        """Mostra duração e resultado de tarefas comuns ou administrativas."""
        self.task_empty.hide()
        key = f"{self.run_number}:{data['id']}"
        item = self.task_items.get(key)
        if item is None:
            item = QTreeWidgetItem()
            self.task_tree.addTopLevelItem(item)
            self.task_items[key] = item
        if data["state"] == "Executando":
            self.task_running[key] = time.monotonic() - data.get("duration", 0)
        else:
            self.task_running.pop(key, None)
        item.setText(0, data["program"])
        item.setText(1, "Administrativa" if data["admin"] else "Comum")
        item.setText(2, data["state"])
        item.setText(3, f"{data.get('duration', 0):.1f} s")
        self.cancel_task_button.setEnabled(not data["admin"] and data["state"] == "Executando")
        if data["admin"]:
            self.cancel_task_button.setToolTip(
                "Aguarde o término da tarefa autorizada pelo sistema; não há interrupção forçada administrativa."
            )

    def show_test_error(self, error):
        """Exibe causa e origem, mantendo traceback recolhido por padrão."""
        self._test_error = error
        self.run_error_label.setText(error["message"])
        self.run_trace.setPlainText(error.get("traceback", ""))
        self.run_trace.hide()
        self.add_output("error", "[Erro] " + error["message"] + "\n")
        self.drawer.show()
        self.drawer.setCurrentIndex(4)
        self.test_status.setText("Erro")

    def locate_test_error(self):
        """Reutiliza o mapa bloco/linha do snapshot, sem adivinhar a origem."""
        if self.runtime_window and hasattr(self, "_test_error"):
            self._locate_runtime_error(self._test_error, self.runtime_window)

    def update_test_time(self):
        """Avisa quando a edição se distancia do snapshot que está em execução."""
        for key, started in self.task_running.items():
            self.task_items[key].setText(3, f"{time.monotonic() - started:.1f} s")
        window = self.runtime_window
        from .settings import preference

        if (
            window
            and not window.session.closed
            and self.test_started
            and preference("test/duration")
        ):
            self.statusBar().showMessage(
                f"Teste em execução · {time.monotonic() - self.test_started:.0f} s"
            )
        if (
            window
            and not window.session.closed
            and self._runtime_project_fingerprint != self.execution_fingerprint()
        ):
            self.set_test_status("Projeto alterado · F5 para reiniciar")

    def set_test_status(self, text):
        """Mantém o cabeçalho compacto e o texto completo disponível no tooltip."""
        compact = text
        for phrase, label in [
            ("administrativa", "Autorização do sistema"),
            ("Aguardando resposta", "Aguardando resposta"),
            ("Iniciando", "Iniciando"),
            ("Fluxo concluído", "Concluído"),
            ("Fluxo cancelado", "Interrompido"),
            ("Erro", "Erro"),
            ("erro", "Erro"),
            ("Executando fluxo", "Executando"),
            ("Aplicativo em execução", "Em execução"),
            ("Encerrando", "Encerrando"),
            ("encerrada", "Parado"),
            ("Projeto alterado", "Alterações · F5 para reiniciar"),
        ]:
            if phrase in text:
                compact = label
                break
        self.test_status.setText(compact)
        self.test_status.setToolTip(text)

    def runtime_stopped(self):
        """Registra encerramento com duração real, sem misturar diagnóstico de edição."""
        self.debug_panel.changed({"state": "stopped"})
        for card in self.logic.graph_panel.cards.values():
            card.active = False
            card.update()
        elapsed = time.monotonic() - self.test_started if self.test_started else 0
        for key in list(self.task_running):
            if key.startswith(str(self.run_number) + ":"):
                self.task_items[key].setText(2, "Interrompido")
                self.task_items[key].setText(
                    3, f"{time.monotonic() - self.task_running.pop(key):.1f} s"
                )
        self.test_status.setText("Parado")
        self.process_info.setText(f"Execução {self.run_number} · encerrada · {elapsed:.1f} s")
        self.cancel_task_button.setEnabled(False)
        self.add_output("status", f"\nExecução encerrada · {elapsed:.1f} s\n")
