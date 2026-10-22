"""Decoração de edição Qt desenhada pelo estilo nativo, sem tema próprio."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget,QStyle,QStyleOptionTitleBar


class QtWindowChrome(QWidget):
    """Usa a mesma primitiva de barra de título do Qt instalado no desktop."""
    def __init__(self,root,parent=None):
        """Os botões de janela são visuais no canvas; não fecham a ferramenta de edição."""
        super().__init__(parent);self.root=root
        self.setFixedHeight(self.style().pixelMetric(QStyle.PixelMetric.PM_TitleBarHeight))
        self.setAccessibleName('Barra de título da janela')

    def paintEvent(self,event):
        """Título, ícone e controles de janela seguem QStyle e QPalette nativos."""
        option=QStyleOptionTitleBar();option.initFrom(self);option.rect=self.rect()
        option.text=self.root.properties.get('title','Aplicativo')
        option.titleBarFlags=Qt.WindowType.Window|Qt.WindowType.WindowSystemMenuHint|Qt.WindowType.WindowCloseButtonHint|Qt.WindowType.WindowMinimizeButtonHint
        if self.root.properties.get('resizable',True):option.titleBarFlags|=Qt.WindowType.WindowMaximizeButtonHint
        option.titleBarState=Qt.WindowState.WindowActive.value
        option.subControls=QStyle.SubControl.SC_All
        painter=QPainter(self);self.style().drawComplexControl(QStyle.ComplexControl.CC_TitleBar,option,painter,self)
