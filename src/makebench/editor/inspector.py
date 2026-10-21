"""Formulário de propriedades, com alterações enviadas ao documento central."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QWidget,
)

from makebench.core.project import (
    KIND_LABELS, LAYOUT_LABELS, Component, ComponentKind, LayoutKind, Project,
)


class Inspector(QWidget):
    """Exibe as propriedades pertinentes ao componente selecionado."""

    property_changed = Signal(str, str, object)
    image_requested = Signal(str)
    image_cleared = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Cria um formulário que será preenchido conforme a seleção."""
        super().__init__(parent)
        self.form = QFormLayout(self)
        self.form.setContentsMargins(12, 12, 12, 12)
        self.form.setSpacing(12)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.setMinimumWidth(250)

    def set_component(self, project: Project, node: Component) -> None:
        """Recria campos com valores do modelo sem emitir alterações iniciais."""
        while self.form.rowCount():
            self.form.removeRow(0)
        self._text_field("Nome do projeto", "@project", "name", project.name)
        self.form.addRow(QLabel(""))
        heading = QLabel(KIND_LABELS[node.kind])
        heading.setStyleSheet("font-weight: bold;")
        self.form.addRow(heading)
        identifier = QLabel(node.id)
        identifier.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.form.addRow("Identificador", identifier)
        names = {"title": "Título", "text": "Texto", "placeholder": "Dica do campo"}
        for key, title in names.items():
            if key in node.properties:
                self._text_field(title, node.id, key, node.properties[key])
        if node.kind == ComponentKind.IMAGE:
            self._text_field("Descrição", node.id, "alt_text", node.properties.get("alt_text", ""))
            filename = QLabel(node.properties.get("image_name") or "Nenhuma imagem selecionada")
            filename.setWordWrap(True)
            self.form.addRow("Arquivo", filename)
            button = QPushButton("Escolher imagem…")
            button.clicked.connect(lambda: self.image_requested.emit(node.id))
            self.form.addRow(button)
            clear = QPushButton("Remover imagem")
            clear.setEnabled(bool(node.properties.get("source")))
            clear.clicked.connect(lambda: self.image_cleared.emit(node.id))
            self.form.addRow(clear)
        if node.kind == ComponentKind.CHECKBOX:
            checkbox = QCheckBox("Selecionada inicialmente")
            checkbox.setChecked(node.properties.get("checked", False))
            checkbox.toggled.connect(
                lambda value, node_id=node.id: self.property_changed.emit(node_id, "checked", value)
            )
            self.form.addRow(checkbox)
        if node.kind == ComponentKind.PROGRESS:
            self._number_field("Progresso (%)", node.id, "value", node.properties.get("value", 0), 0, 100)
        if node.kind == ComponentKind.PAGES:
            pages = QComboBox()
            for child in node.children:
                pages.addItem(child.properties.get("title", "Página"), child.id)
            pages.setCurrentIndex(pages.findData(node.properties["initial_page"]))
            pages.currentIndexChanged.connect(
                lambda _: self.property_changed.emit(node.id, "initial_page", pages.currentData())
            )
            self.form.addRow("Página inicial", pages)
        if node.can_have_children and node.kind != ComponentKind.PAGES:
            combo = QComboBox()
            for mode, label in LAYOUT_LABELS.items():
                combo.addItem(label, mode.value)
            combo.setCurrentIndex(list(LayoutKind).index(node.layout))
            combo.currentIndexChanged.connect(
                lambda _, node_id=node.id, field=combo: self.property_changed.emit(
                    node_id, "layout", field.currentData()
                )
            )
            self.form.addRow("Organização", combo)
            if node.layout == LayoutKind.GRID:
                self._number_field("Colunas", node.id, "columns", node.properties.get("columns", 2), 1, 12)
        parent = project.parent_of(node.id)
        if parent and parent.kind != ComponentKind.PAGES and parent.layout == LayoutKind.FREE:
            self.form.addRow(QLabel("Posição e tamanho"))
            for key, title in (("x", "X"), ("y", "Y"), ("width", "Largura"), ("height", "Altura")):
                self._number_field(title, node.id, f"geometry.{key}", node.geometry[key], 1 if key in {"width", "height"} else 0, 20000)

    def _text_field(self, label: str, node_id: str, key: str, value: str) -> None:
        """Confirma texto ao sair do campo, agrupando a digitação em uma alteração."""
        field = QLineEdit(value)
        field.setObjectName(f"property_{key}")
        field.editingFinished.connect(
            lambda field=field: self.property_changed.emit(node_id, key, field.text())
        )
        self.form.addRow(label, field)

    def _number_field(
        self, label: str, node_id: str, key: str, value: int, minimum: int, maximum: int,
    ) -> None:
        """Cria um campo numérico com limites adequados à propriedade."""
        field = QSpinBox()
        field.setObjectName(f"property_{key}")
        field.setRange(minimum, maximum)
        field.setValue(value)
        field.setKeyboardTracking(False)
        field.valueChanged.connect(
            lambda value: self.property_changed.emit(node_id, key, value)
        )
        self.form.addRow(label, field)
