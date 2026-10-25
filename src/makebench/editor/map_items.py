"""Itens gráficos do Mapa: composição real, portas e linhas fáceis de selecionar."""

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QFontMetricsF,
    QPixmap,
    QPainterPathStroker,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsPathItem,
    QGraphicsSimpleTextItem,
)
from .theme import manager, icon

CARD_WIDTH = 300
CARD_HEIGHT = 252


class MapNode(QGraphicsRectItem):
    """Cartão é uma vista do documento: contém miniatura, nome, estado e diagnóstico."""

    def __init__(self, key, label, position, view, initial=False, issue="", count=0):
        """Nenhum controle da miniatura recebe eventos de execução do aplicativo."""
        super().__init__(0, 0, CARD_WIDTH, CARD_HEIGHT)
        self.key = key
        self.label = label
        self.map_view = view
        self.initial = initial
        self.issue = issue
        self.count = count
        self.thumbnail = QPixmap()
        self.preview_error = ""
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setPos(*position)
        self.setToolTip(
            label
            + "\nDuplo clique abre o Designer. Arraste a porta para conectar."
            + ("\n" + issue if issue else "")
        )

    def boundingRect(self):
        """Inclui a porta no retângulo de atualização e de hit testing da cena."""
        return self.rect().adjusted(-1, -1, 8, 1)

    def shape(self):
        """A porta também pode receber um arraste na sua metade externa."""
        path = QPainterPath()
        path.addRect(self.rect())
        path.addEllipse(QPointF(CARD_WIDTH, 126), 8, 8)
        return path

    def paint(self, painter, option, widget=None):
        """Apenas o cartão é gráfico; seu conteúdo é renderizado pelo toolkit real."""
        t = manager().tokens
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(t["raised"]))
        painter.setPen(
            QPen(
                QColor(t["accent"] if self.isSelected() else t["border"]),
                2 if self.isSelected() else 1,
            )
        )
        painter.drawRoundedRect(self.rect(), 4, 4)
        painter.setFont(QApplication.font())
        metrics = QFontMetricsF(painter.font())
        lines = self.label.split("\n", 1)
        painter.setPen(QColor(t["text"]))
        painter.drawText(
            QRectF(12, 8, 264, 22), metrics.elidedText(lines[0], Qt.TextElideMode.ElideRight, 264)
        )
        painter.setPen(QColor(t["muted"]))
        painter.drawText(
            QRectF(12, 30, 264, 18),
            metrics.elidedText(
                lines[1] if len(lines) > 1 else "Janela", Qt.TextElideMode.ElideRight, 264
            ),
        )
        area = QRectF(12, 54, 276, 174)
        painter.fillRect(area, QColor(t["canvas"]))
        if not self.thumbnail.isNull():
            painter.drawPixmap(
                round(area.center().x() - self.thumbnail.width() / 2),
                round(area.center().y() - self.thumbnail.height() / 2),
                self.thumbnail,
            )
        else:
            painter.drawText(
                area,
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                "Prévia indisponível" if self.preview_error else "Preparando prévia…",
            )
        painter.setPen(QColor(t["text"]))
        footer = "▶ Inicial" if self.initial else f"{self.count} elemento(s)"
        if self.issue or self.preview_error:
            footer += "  ·  !"
        painter.drawText(QRectF(12, 230, 250, 20), footer)
        painter.setBrush(QColor(t["raised"]))
        painter.setPen(QPen(QColor(t["accent"]), 2))
        painter.drawEllipse(QPointF(CARD_WIDTH, 126), 6, 6)

    def mouseDoubleClickEvent(self, event):
        """Adia navegação até o Qt terminar o evento gráfico."""
        key = self.key
        QTimer.singleShot(0, lambda: self.map_view.panel.activate(key))
        event.accept()

    def keyPressEvent(self, event):
        """Enter oferece a mesma navegação que o duplo clique."""
        if event.key() in {Qt.Key.Key_Enter, Qt.Key.Key_Return}:
            self.map_view.panel.activate(self.key)
            event.accept()
        else:
            super().keyPressEvent(event)


class MapEdge(QGraphicsPathItem):
    """Linha com área de clique maior sem aumentar o peso visual."""

    def __init__(self, path, edge):
        """Guarda somente os IDs do bloco e fluxo que originaram esta navegação."""
        super().__init__(path)
        self.edge = edge
        self.setData(0, edge)
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setToolTip(edge["event"] + "\nClique para inspecionar; Delete remove a transição.")

    def shape(self):
        """Uma linha fina continua acessível ao mouse em zoom reduzido."""
        stroke = QPainterPathStroker()
        stroke.setWidth(14)
        return stroke.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        """Seleção usa o destaque nativo e a seta segue a tangente final da curva."""
        t = manager().tokens
        color = QColor(t["accent"] if self.isSelected() else t["muted"])
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, 2 if self.isSelected() else 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())
        end = self.path().pointAtPercent(1)
        before = self.path().pointAtPercent(0.96)
        delta = end - before
        length = max(1, (delta.x() ** 2 + delta.y() ** 2) ** 0.5)
        unit = delta / length
        normal = QPointF(-unit.y(), unit.x())
        head = QPainterPath(end)
        head.lineTo(end - unit * 11 + normal * 4)
        head.lineTo(end - unit * 11 - normal * 4)
        head.closeSubpath()
        painter.fillPath(head, color)


class GroupHeader(QGraphicsSimpleTextItem):
    """Título recolhível de uma janela e seus estados; não altera o documento."""

    def __init__(self, label, identifier, panel):
        """A árvore nativa oferece o mesmo comando por teclado."""
        super().__init__(label)
        self.identifier = identifier
        self.panel = panel
        self.setFont(QApplication.font())
        self.setBrush(QColor(manager().tokens["text"]))
        self.setToolTip("Clique para expandir ou recolher os estados desta janela.")

    def mousePressEvent(self, event):
        """Não começa arraste de cartão ao clicar no cabeçalho do grupo."""
        identifier = self.identifier
        QTimer.singleShot(0, lambda: self.panel.toggle_group(identifier))
        event.accept()
