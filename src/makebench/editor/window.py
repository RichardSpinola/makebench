"""Janela principal da primeira etapa do Makebench."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QLabel, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSplitter, QToolBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from makebench.core.history import History
from makebench.core.project import (
    KIND_LABELS, Component, ComponentKind, LayoutKind, Project, ProjectError,
)
from makebench.core.storage import load_project, save_project
from makebench.editor.canvas import PreviewCanvas
from makebench.editor.inspector import Inspector


class MainWindow(QMainWindow):
    """Coordena documento, histórico, seleção e comandos de arquivo.

    O documento é a fonte de verdade; árvore, prévia e propriedades são vistas.
    A etapa inicial permite montar a interface, mas ainda não executa tarefas.
    """

    def __init__(self, project: Project | None = None, path: Path | None = None) -> None:
        """Abre um projeto fornecido ou inicia uma nova interface vazia."""
        super().__init__()
        self.project = project or Project.empty()
        self.path = path
        self.history = History(self.project)
        self.selected_id = self.project.root.id
        self._tree_items: dict[str, QTreeWidgetItem] = {}
        self._refreshing = False
        self.resize(1280, 800)
        self.setMinimumSize(980, 600)
        self.setWindowModified(False)
        self._create_actions()
        self._create_workspace()
        self._refresh()

    def _create_actions(self) -> None:
        """Registra menus e atalhos que têm comportamento implementado."""
        file_menu = self.menuBar().addMenu("&Arquivo")
        edit_menu = self.menuBar().addMenu("&Editar")
        help_menu = self.menuBar().addMenu("Aj&uda")
        self.new_action = QAction("Novo projeto", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self.new_project)
        self.open_action = QAction("Abrir…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_project)
        self.save_action = QAction("Salvar", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save)
        save_as_action = QAction("Salvar como…", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_as)
        quit_action = QAction("Sair", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addActions([self.new_action, self.open_action, self.save_action, save_as_action])
        file_menu.addSeparator()
        file_menu.addAction(quit_action)
        self.undo_action = QAction("Desfazer", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.redo_action = QAction("Refazer", self)
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        self.redo_action.triggered.connect(self.redo)
        self.remove_action = QAction("Remover componente", self)
        self.remove_action.triggered.connect(self.remove_component)
        edit_menu.addActions([self.undo_action, self.redo_action, self.remove_action])
        about_action = QAction("Sobre o Makebench", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        toolbar = QToolBar("Projeto", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.addActions([self.new_action, self.open_action, self.save_action])
        toolbar.addSeparator()
        toolbar.addActions([self.undo_action, self.redo_action])
        self.addToolBar(toolbar)

    def _create_workspace(self) -> None:
        """Monta os três painéis: componentes, prévia e propriedades."""
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        brand = QLabel("Makebench")
        font = brand.font()
        font.setPointSize(font.pointSize() + 8)
        font.setBold(True)
        brand.setFont(font)
        left_layout.addWidget(brand)
        subtitle = QLabel("Dê forma ao seu aplicativo.")
        subtitle.setWordWrap(True)
        left_layout.addWidget(subtitle)
        left_layout.addSpacing(16)
        left_layout.addWidget(QLabel("Adicionar componente"))
        self.palette = QComboBox()
        for kind, label in KIND_LABELS.items():
            if kind != ComponentKind.WINDOW:
                self.palette.addItem(label, kind.value)
        left_layout.addWidget(self.palette)
        add_button = QPushButton("Adicionar à interface")
        add_button.clicked.connect(self.add_component)
        left_layout.addWidget(add_button)
        left_layout.addSpacing(16)
        left_layout.addWidget(QLabel("Componentes"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(210)
        self.tree.currentItemChanged.connect(self._tree_selection_changed)
        left_layout.addWidget(self.tree, 1)
        remove_button = QPushButton("Remover selecionado")
        remove_button.clicked.connect(self.remove_component)
        self.remove_action.changed.connect(
            lambda: remove_button.setEnabled(self.remove_action.isEnabled())
        )
        left_layout.addWidget(remove_button)
        splitter.addWidget(left)

        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        heading = QLabel("Interface")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        middle_layout.addWidget(heading)
        hint = QLabel("Clique em um componente para editar suas propriedades.")
        hint.setWordWrap(True)
        middle_layout.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.canvas = PreviewCanvas()
        self.canvas.component_selected.connect(self._select)
        scroll.setWidget(self.canvas)
        middle_layout.addWidget(scroll, 1)
        preview_note = QLabel("Prévia de edição · os botões selecionam componentes.")
        preview_note.setWordWrap(True)
        middle_layout.addWidget(preview_note)
        splitter.addWidget(middle)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        properties_heading = QLabel("Propriedades")
        properties_heading.setStyleSheet("font-size: 16px; font-weight: bold;")
        right_layout.addWidget(properties_heading)
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        self.inspector = Inspector()
        self.inspector.property_changed.connect(self._change_property)
        inspector_scroll.setWidget(self.inspector)
        right_layout.addWidget(inspector_scroll)
        splitter.addWidget(right)
        splitter.setSizes([250, 700, 300])
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

    def _refresh(self) -> None:
        """Atualiza as vistas a partir do documento e preserva a seleção válida."""
        self._refreshing = True
        self._tree_items = {}
        self.tree.clear()

        def append(node: Component, parent: QTreeWidgetItem | None = None) -> None:
            item = QTreeWidgetItem([node.display_name])
            item.setData(0, Qt.ItemDataRole.UserRole, node.id)
            if parent:
                parent.addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            self._tree_items[node.id] = item
            for child in node.children:
                append(child, item)

        append(self.project.root)
        self.tree.expandAll()
        self.canvas.set_project(self.project)
        if self.project.find(self.selected_id) is None:
            self.selected_id = self.project.root.id
        self._refreshing = False
        self._select(self.selected_id)
        self._update_actions()

    def _select(self, component_id: str) -> None:
        """Sincroniza seleção da árvore, prévia e formulário de propriedades."""
        if self._refreshing:
            return
        node = self.project.find(component_id)
        if node is None:
            return
        self.selected_id = component_id
        self.tree.blockSignals(True)
        self.tree.setCurrentItem(self._tree_items[component_id])
        self.tree.blockSignals(False)
        self.canvas.select(component_id)
        self.inspector.set_component(self.project, node)
        self._update_actions()

    def _tree_selection_changed(self, current: QTreeWidgetItem | None, _previous=None) -> None:
        """Recebe seleção por mouse ou teclado na árvore."""
        if current and not self._refreshing:
            self._select(current.data(0, Qt.ItemDataRole.UserRole))

    def _update_actions(self) -> None:
        """Atualiza comandos, título e indicador de alterações não salvas."""
        self.undo_action.setEnabled(self.history.can_undo)
        self.redo_action.setEnabled(self.history.can_redo)
        self.remove_action.setEnabled(self.selected_id != self.project.root.id)
        self.setWindowTitle(f"{self.project.name}[*] — Makebench")
        self.setWindowModified(self.history.dirty)
        count = len(list(self.project.root.walk())) - 1
        state = "Alterações não salvas" if self.history.dirty else "Pronto"
        self.statusBar().showMessage(f"{state} · {count} componente(s)")

    def _change_property(self, component_id: str, key: str, value: object) -> None:
        """Aplica uma propriedade válida e registra uma única alteração no histórico."""
        if self._refreshing:
            return
        if component_id == "@project":
            cleaned = str(value).strip()
            if not cleaned:
                self._refresh()
                self.statusBar().showMessage("O nome do projeto não pode ficar vazio.", 5000)
                return
            if self.project.name == cleaned:
                return
            self.project.name = cleaned
        else:
            node = self.project.find(component_id)
            if node is None:
                return
            if key == "layout":
                if node.layout == LayoutKind(value):
                    return
                node.layout = LayoutKind(value)
            elif key.startswith("geometry."):
                name = key.partition(".")[2]
                if node.geometry[name] == value:
                    return
                node.geometry[name] = int(value)
            else:
                if node.properties.get(key) == value:
                    return
                node.properties[key] = value
        self.history.push(self.project)
        self._refresh()

    def _finish_field_edit(self) -> None:
        """Confirma texto ainda em edição antes de salvar ou substituir o projeto."""
        focus = QApplication.focusWidget()
        if focus is not None:
            focus.clearFocus()

    def add_component(self) -> None:
        """Insere no contêiner selecionado ou no pai do componente selecionado."""
        self._finish_field_edit()
        selected = self.project.find(self.selected_id)
        parent = selected if selected.can_have_children else self.project.parent_of(selected.id)
        child = self.project.add(parent.id, ComponentKind(self.palette.currentData()))
        self.selected_id = child.id
        self.history.push(self.project)
        self._refresh()

    def remove_component(self) -> None:
        """Remove a seleção, mantendo a exclusão disponível para desfazer."""
        self._finish_field_edit()
        if self.selected_id == self.project.root.id:
            return
        try:
            self.selected_id = self.project.remove(self.selected_id)
        except ProjectError as exc:
            self._show_error(str(exc))
            return
        self.history.push(self.project)
        self._refresh()

    def undo(self) -> None:
        """Restaura o documento anterior, incluindo propriedades e ordem dos nós."""
        self._finish_field_edit()
        self.project = self.history.undo()
        self._refresh()

    def redo(self) -> None:
        """Reaplica uma alteração previamente desfeita."""
        self._finish_field_edit()
        self.project = self.history.redo()
        self._refresh()

    def new_project(self) -> None:
        """Cria um documento após resolver alterações não salvas."""
        if not self._confirm_discard():
            return
        self._replace_project(Project.empty(), None)

    def open_project(self) -> None:
        """Abre um documento validado; falhas não substituem o projeto atual."""
        if not self._confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Abrir projeto Makebench", str(self.path.parent) if self.path else "",
            "Projetos Makebench (*.makebench.json);;JSON (*.json)",
        )
        if not filename:
            return
        try:
            project = load_project(filename)
        except ProjectError as exc:
            self._show_error(str(exc))
            return
        self._replace_project(project, Path(filename))

    def _replace_project(self, project: Project, path: Path | None) -> None:
        """Troca o documento e inicia um histórico independente."""
        self.project = project
        self.path = path
        self.history = History(project)
        self.selected_id = project.root.id
        self._refresh()

    def save(self) -> bool:
        """Salva o projeto ou solicita um destino quando ainda não tem caminho."""
        self._finish_field_edit()
        if self.path is None:
            return self.save_as()
        return self.save_to(self.path)

    def save_as(self) -> bool:
        """Solicita um destino, sem mudar o caminho atual em caso de falha."""
        self._finish_field_edit()
        filename, _ = QFileDialog.getSaveFileName(
            self, "Salvar projeto Makebench",
            str(self.path) if self.path else "projeto.makebench.json",
            "Projetos Makebench (*.makebench.json)",
        )
        if not filename:
            return False
        if not filename.endswith(".makebench.json"):
            filename += ".makebench.json"
        return self.save_to(Path(filename))

    def save_to(self, path: Path) -> bool:
        """Persiste o documento e marca como salvo somente depois do sucesso."""
        self._finish_field_edit()
        try:
            save_project(self.project, path)
        except ProjectError as exc:
            self._show_error(str(exc))
            return False
        self.path = path
        self.history.mark_saved()
        self._update_actions()
        return True

    def _confirm_discard(self) -> bool:
        """Oferece salvar alterações antes de fechar, abrir ou criar um projeto."""
        self._finish_field_edit()
        if not self.history.dirty:
            return True
        choice = QMessageBox.warning(
            self, "Salvar alterações?", "O projeto tem alterações que ainda não foram salvas.",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        return choice == QMessageBox.StandardButton.Discard

    def _show_error(self, message: str) -> None:
        """Apresenta falhas recuperáveis sem fechar o editor."""
        QMessageBox.critical(self, "Makebench", message)

    def show_about(self) -> None:
        """Informa a versão e o limite funcional da entrega atual."""
        QMessageBox.about(
            self, "Sobre o Makebench",
            "<h2>Makebench</h2><p>Aplicativos Linux, construídos por você.</p>"
            "<p>Versão 0.1.0.dev1 — base do editor de interface.</p>"
            "<p>Blocos, execução de scripts e empacotamento serão adicionados nas próximas etapas.</p>",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Protege alterações não salvas ao encerrar a janela."""
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
