"""Edição de janelas/estados e mapa derivado da lógica neutra."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QInputDialog,
    QLabel,
)
from makebench.core.navigation import add_state, add_window, navigation_edges


from .map_panel import MapPanel


class NavigationMixin:
    """Mantém contexto selecionado sem gravá-lo no arquivo do aplicativo."""

    def install_navigation_editor(self):
        """Adiciona seletores, comandos e mapa de navegação real."""
        self.active_window = self.project.root.id
        self.active_state = "@default"
        self.tree.active_root = lambda: self.active_window
        self.window_selector = QComboBox()
        self.window_selector.setAccessibleName("Janela em edição")
        self.window_selector.setMaximumWidth(210)
        self.state_selector = QComboBox()
        self.state_selector.setAccessibleName("Estado em edição")
        self.state_selector.setMaximumWidth(170)
        self.context_bar.insertWidget(self.context_bar.actions()[0], self.window_selector)
        self.context_bar.insertWidget(self.context_bar.actions()[-1], self.state_selector)
        self.window_selector.currentIndexChanged.connect(self.window_selected)
        self.state_selector.currentIndexChanged.connect(self.state_selected)
        menu = self.menuBar().addMenu("&Projeto")
        for label, callback in [
            ("Nova janela…", self.new_window_dialog),
            ("Novo estado…", self.new_state_dialog),
            ("Definir janela como inicial", self.make_entry_window),
            ("Definir estado como inicial", self.make_initial_state),
            ("Renomear estado…", self.rename_state_dialog),
            ("Restaurar seleção do Padrão", self.restore_default_properties),
            ("Remover estado", self.remove_state),
            ("Remover janela", self.remove_window),
        ]:
            action = menu.addAction(label)
            action.triggered.connect(callback)
        self.map_panel = MapPanel(self)
        self.tabs.addTab(self.map_panel, "Mapa")
        self.sync_navigation()

    def sync_navigation(self):
        """Reconcilia seleção com desfazer, carregamento e remoção de janelas."""
        if not hasattr(self, "window_selector"):
            return
        if self.active_window not in {r.id for r in self.project.roots}:
            self.active_window = self.project.root.id
            self.active_state = "@default"
        owner = self.project.window_of(self.selected_id)
        if owner and owner.id != self.active_window:
            self.active_window = owner.id
            self.active_state = "@default"
        from .controls import reconcile_combo

        empty = bool(self.project.metadata.get("empty_map"))
        self.window_selector.setEnabled(not empty)
        self.state_selector.setEnabled(not empty)
        if empty:
            reconcile_combo(self.window_selector, [("Nenhuma interface", None)], None)
            reconcile_combo(self.state_selector, [], None)
            return
        reconcile_combo(
            self.window_selector,
            [(root.properties.get("title", "Janela"), root.id) for root in self.project.roots],
            self.active_window,
        )
        states = self.project.states.get(self.active_window, [])
        if self.active_state not in {"@default", *[s["id"] for s in states]}:
            self.active_state = "@default"
        reconcile_combo(
            self.state_selector,
            [
                (
                    self.project.find(self.active_window).properties.get(
                        "default_state_name", "Padrão"
                    ),
                    "@default",
                ),
                *[(state["name"], state["id"]) for state in states],
            ],
            self.active_state,
        )

    def activate_window(self, window_id, state="@default"):
        """Muda o contexto após confirmar alterações dos blocos e campos."""
        if not self._finish_field_edit():
            return
        self.active_window = window_id
        self.active_state = state
        self.selected_id = window_id
        self._refresh()

    def window_selected(self):
        """Recebe escolha explícita de uma janela real."""
        if self.window_selector.currentData():
            self.activate_window(self.window_selector.currentData())

    def state_selected(self):
        """Revela uma variação mantendo a seleção válida da mesma janela."""
        if self.state_selector.currentData() is not None:
            if not self._finish_field_edit():
                return
            self.active_state = self.state_selector.currentData()
            self._refresh()

    def new_window_dialog(self):
        """Cria janela vazia ou cópia da composição atual com novos IDs."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Nova interface")
        form = QFormLayout(dialog)
        from PySide6.QtWidgets import QLineEdit

        empty = bool(self.project.metadata.get("empty_map"))
        name = QLineEdit("Tela principal" if empty else "Nova interface")
        name.setObjectName("new_interface_name")
        base = QComboBox()
        base.addItem("Em branco", None)
        if not empty:
            for root in self.project.roots:
                base.addItem("Duplicar " + root.properties.get("title", "Janela"), root.id)
        form.addRow("Nome", name)
        form.addRow("Base", base)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Criar interface")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted or not name.text().strip():
            return

        def create():
            """Cria o item solicitado com os valores validados do diálogo."""
            if self.project.metadata.pop("empty_map", False):
                root = self.project.root
                root.properties["title"] = name.text().strip()
            else:
                root = add_window(self.project, name.text(), base.currentData())
            self.active_window = root.id
            self.active_state = "@default"
            self.selected_id = root.id

        self._edit(create)

    def new_state_dialog(self):
        """Cria variação independente sobre a estrutura padrão."""
        from PySide6.QtWidgets import QLineEdit

        dialog = QDialog(self)
        dialog.setWindowTitle("Novo estado")
        form = QFormLayout(dialog)
        name = QLineEdit()
        base = QComboBox()
        base.addItem("Padrão", "@default")
        for state in self.project.states.get(self.active_window, []):
            base.addItem(state["name"], state["id"])
        base.setCurrentIndex(base.findData(self.active_state))
        form.addRow("Nome", name)
        form.addRow("Começar de", base)
        note = QLabel(
            "Copia as diferenças da etapa escolhida. A estrutura continua vindo do Padrão."
        )
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Criar estado")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def create():
            """Cria o item solicitado com os valores validados do diálogo."""
            state = add_state(self.project, self.active_window, name.text(), base.currentData())
            self.active_state = state["id"]

        self._edit(create)

    def make_entry_window(self):
        """Define explicitamente qual janela abre ao iniciar o aplicativo."""
        self._edit(lambda: setattr(self.project, "entry_window", self.active_window))

    def make_initial_state(self):
        """Define a variação aplicada antes do evento de início da janela."""
        self._edit(
            lambda: self.project.find(self.active_window).properties.update(
                initial_state=self.active_state
            )
        )

    def rename_state_dialog(self):
        """Renomeia a variação mantendo IDs e todas as transições."""
        if self.active_state == "@default":
            root = self.project.find(self.active_window)
            name, ok = QInputDialog.getText(
                self,
                "Nome da composição padrão",
                "Nome da etapa inicial",
                text=root.properties.get("default_state_name", "Padrão"),
            )
            if ok and name.strip():
                self._edit(lambda: root.properties.update(default_state_name=name.strip()))
            return
        state = next(
            s for s in self.project.states[self.active_window] if s["id"] == self.active_state
        )
        name, ok = QInputDialog.getText(self, "Renomear estado", "Nome", text=state["name"])
        if ok and name.strip():
            self._edit(lambda: state.update(name=name.strip()))

    def restore_default_properties(self):
        """Remove somente sobrescritas da seleção no estado ativo."""
        if self.active_state == "@default":
            return

        def restore():
            """Remove as diferenças escolhidas, preservando os demais dados."""
            state = next(
                s for s in self.project.states[self.active_window] if s["id"] == self.active_state
            )
            state.get("overrides", {}).pop(self.selected_id, None)

        self._edit(restore)

    def remove_state(self):
        """Recusa exclusão de estado ainda referenciado pela lógica."""
        if self.active_state == "@default":
            return
        state_id = self.active_state
        for flow in self.project.workflows:
            if state_id in flow.get("states", []) or any(
                e["target"] == state_id for e in navigation_edges(self.project)
            ):
                self._show_error("Revise os fluxos que usam este estado antes de removê-lo.")
                return

        def remove():
            """Remove os dados selecionados como uma operação reversível."""
            self.project.states[self.active_window] = [
                s for s in self.project.states[self.active_window] if s["id"] != state_id
            ]
            if self.project.find(self.active_window).properties.get("initial_state") == state_id:
                self.project.find(self.active_window).properties["initial_state"] = "@default"
            self.active_state = "@default"

        self._edit(remove)

    def remove_window(self):
        """Protege a raiz e janelas referenciadas; remoção é reversível pelo histórico."""
        if len(self.project.roots) == 1:
            self._show_error("Mantenha pelo menos uma janela no aplicativo.")
            return
        identifier = self.active_window
        ids = {n.id for n in self.project.find(identifier).walk()}
        if any(e["target"] == identifier for e in navigation_edges(self.project)) or any(
            f["event"]["component"] in ids for f in self.project.workflows
        ):
            self._show_error("Revise os fluxos desta janela e suas conexões antes de removê-la.")
            return

        def remove():
            """Remove os dados selecionados como uma operação reversível."""
            if identifier == self.project.root.id:
                self.project.root = self.project.windows.pop(0)
            else:
                self.project.windows = [r for r in self.project.windows if r.id != identifier]
            self.project.states.pop(identifier, None)
            self.project.variables = [
                v for v in self.project.variables if v.get("window") != identifier
            ]
            if self.project.entry_window == identifier:
                self.project.entry_window = self.project.root.id
            self.active_window = self.project.root.id
            self.active_state = "@default"
            self.selected_id = self.project.root.id

        self._edit(remove)
