"""Prévia GTK real sobre o canvas Qt; seleção e edição não disparam eventos do app."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading

from PySide6.QtCore import QThread, Signal, QTimer, Qt, QRect, QPoint, QSize
from PySide6.QtGui import QPainter, QPen, QPixmap, QDrag
from PySide6.QtWidgets import QWidget, QApplication, QRubberBand
from makebench.core.project import ComponentKind, LayoutKind
from .drag import read_payload,mime_for


class GtkPreviewJob(QThread):
    """Apenas componentes e bytes de imagens atravessam a fronteira de processo."""
    ready=Signal(bytes,dict);failed=Signal(str)

    def __init__(self,payload,parent):
        """Não recebe fonte Python, fluxos, scripts ou eventos do projeto."""
        super().__init__(parent);self.payload=payload;self.cancel=threading.Event()

    def run(self):
        """Renderiza fora da interface e limpa o display temporário ao sair."""
        try:self.render()
        except Exception as exc:
            if not self.cancel.is_set():self.failed.emit(str(exc))

    def render(self):
        """Arquivos intermediários são privados e removidos também em caso de falha."""
        with tempfile.TemporaryDirectory(prefix='makebench-gtk-preview-') as directory:
            root=Path(directory);source=root/'input.json';target=root/'result.json';source.write_text(json.dumps(self.payload))
            environment=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[2])+os.pathsep+os.environ.get('PYTHONPATH',''))
            process=subprocess.Popen([sys.executable,'-m','makebench.gtk_runtime.preview',str(source),str(target)],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            elapsed=0
            while process.poll() is None and not self.cancel.wait(.05):
                elapsed+=.05
                if elapsed>8:break
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            output,error=process.communicate()
            if self.cancel.is_set():return
            if process.returncode or not target.is_file():self.failed.emit(error.decode(errors='replace')[-1800:] or 'GTK não produziu a prévia.');return
            self.ready.emit(target.with_suffix('.png').read_bytes(),json.loads(target.read_text()))


class GtkDesignSurface(QWidget):
    """Imagem do GTK com regiões reais para selecionar, inserir, mover e redimensionar."""
    def __init__(self,canvas):
        """Mantém a última imagem enquanto outra está sendo calculada, sem piscar."""
        super().__init__(canvas);self.canvas=canvas;self.image=QPixmap();self.rectangles={};self.tab_rectangles={};self.job=None;self.payload=None;self.version=0;self.error='Preparando prévia GTK nativa…';self.drag=None;self.rubber=None
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(120);self.timer.timeout.connect(self.start_job)
        self.setAcceptDrops(True);self.setMouseTracking(True);self.hide()

    def request(self):
        """Agenda o documento visual mais recente, descartando resultados antigos."""
        if not self.canvas._project or self.canvas._project.application.get('backend','qt')!='gtk':self.hide();return
        self.show();self.raise_();self.setGeometry(self.canvas.rect());self.version+=1
        root=self.canvas._project.root
        key=(self.canvas._project.id,root.id)
        if key!=getattr(self,'document_key',None):
            self.document_key=key;self.image=QPixmap();self.rectangles={};self.error='Preparando prévia GTK nativa…';self.canvas.native_size=None
        assets={}
        for key in self.canvas._project.asset_paths():
            try:assets[key]=base64.b64encode(self.canvas.read_asset(key)).decode()
            except (OSError,ValueError):assets[key]=''
        self.payload={'root':root.to_dict(),'assets':assets,'visible_pages':dict(self.canvas._visible_pages)}
        if not shutil.which('gtk4-broadwayd'):
            self.error='A prévia fiel GTK precisa de gtk4-broadwayd e PyGObject/GTK4.';self.update();return
        self.timer.start();self.update()

    def start_job(self):
        """Serializa pedidos sem acumular processos durante digitação ou arraste."""
        if not self.isVisible() or self.job and self.job.isRunning():return
        version=self.version;self.job=job=GtkPreviewJob(self.payload,self)
        def ready(image,info):
            """Aplica somente a imagem que ainda corresponde à versão atual."""
            if version!=self.version:return
            self.image.loadFromData(image);self.rectangles={key:QRect(*[round(n) for n in values]).translated(20,20) for key,values in info['rectangles'].items()};self.tab_rectangles={key:QRect(*[round(n) for n in values]).translated(20,20) for key,values in info.get('tabs',{}).items()};self.error='';self.canvas.native_size=QSize(info['width']+40,info['height']+40);self.update();self.canvas.native_preview_ready.emit()
        job.ready.connect(ready);job.failed.connect(lambda error:self.failed(error) if version==self.version else None)
        def finished():
            """Um pedido mais recente substitui o anterior depois da limpeza do display."""
            self.job=None;job.deleteLater()
            if version!=self.version and self.isVisible():self.timer.start()
        job.finished.connect(finished);job.start()

    def failed(self,error):
        """Nunca apresenta controles Qt como se fossem GTK quando falta uma biblioteca."""
        self.error='Prévia GTK indisponível. '+error;self.setToolTip(self.error);self.update()

    def showEvent(self,event):
        """Só consome um processo de renderização quando Design está visível."""
        super().showEvent(event)
        if self.payload is not None:self.timer.start()

    def shutdown(self):
        """Encerra só o processo descartável da prévia, sem tocar no runtime do usuário."""
        self.timer.stop()
        if self.job and self.job.isRunning():self.job.cancel.set();self.job.wait(3000)

    def cancel_gesture(self):
        """Escape cancela somente a composição temporária, sem alterar o documento."""
        self.drag=None
        if self.rubber:self.rubber.hide();self.rubber.deleteLater();self.rubber=None
        self.update()

    def paintEvent(self,event):
        """O próprio GTK desenha controles e cabeçalho; Qt desenha apenas guias de edição."""
        painter=QPainter(self);painter.fillRect(self.rect(),self.palette().alternateBase())
        if self.image.isNull():painter.setPen(self.palette().windowText().color());painter.drawText(self.rect().adjusted(30,30,-30,-30),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,self.error);return
        painter.drawPixmap(20,20,self.image)
        painter.setPen(QPen(self.palette().highlight().color(),1))
        for identifier in getattr(self.canvas,'native_selection',{self.canvas._selected_id}):
            rect=self.rectangles.get(identifier)
            if rect:
                painter.drawRect(rect.adjusted(0,0,-1,-1));parent=self.canvas._project.parent_of(identifier)
                if parent and parent.layout==LayoutKind.FREE:
                    painter.setBrush(self.palette().base())
                    for x,y in ((rect.left(),rect.top()),(rect.center().x(),rect.top()),(rect.right(),rect.top()),(rect.right(),rect.center().y()),(rect.right(),rect.bottom()),(rect.center().x(),rect.bottom()),(rect.left(),rect.bottom()),(rect.left(),rect.center().y())):painter.drawEllipse(QPoint(x,y),3,3)
        if self.drag and self.drag.get('preview'):painter.drawRect(self.drag['preview'])
        if self.error:painter.drawText(QRect(20,self.image.height()+22,self.width()-40,24),self.error.splitlines()[0])

    def hit(self,point):
        """Percorre da folha ao contêiner, usando alocações fornecidas pelo GTK."""
        for node in reversed(list(self.canvas._project.root.walk())):
            if node.id in self.rectangles and self.rectangles[node.id].contains(point):return node
        return self.canvas._project.root

    def mousePressEvent(self,event):
        """Seleciona componentes sem clicar no botão GTK ou executar callbacks."""
        if event.button()!=Qt.MouseButton.LeftButton:return
        point=event.position().toPoint()
        for identifier,rect in self.tab_rectangles.items():
            if rect.contains(point):self.canvas.component_selected.emit(identifier);return
        node=self.hit(point);self.canvas.setFocus();self.canvas.component_selected.emit(node.id)
        if self.canvas.insert_tool:
            payload={'mode':'new','kind':self.canvas.insert_tool};self.insert(payload,point);self.canvas.set_insert_tool(None);return
        parent=self.canvas._project.parent_of(node.id)
        if node.can_have_children and node.layout==LayoutKind.FREE:
            self.rubber_origin=point;self.rubber_parent=node.id;self.rubber=QRubberBand(QRubberBand.Shape.Rectangle,self);self.rubber.setGeometry(QRect(point,QSize()));self.rubber.show()
        elif parent:
            rect=self.rectangles[node.id];edge=''
            if abs(point.x()-rect.left())<6:edge+='w'
            elif abs(point.x()-rect.right())<6:edge+='e'
            if abs(point.y()-rect.top())<6:edge+='n'
            elif abs(point.y()-rect.bottom())<6:edge+='s'
            self.drag={'node':node.id,'start':point,'geometry':dict(node.geometry),'rect':rect,'edge':edge,'free':parent.layout==LayoutKind.FREE,'transfer':bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)}
        self.update()

    def mouseMoveEvent(self,event):
        """Mostra o gesto sem reconstruir GTK a cada pixel; confirma somente ao soltar."""
        if self.rubber:self.rubber.setGeometry(QRect(self.rubber_origin,event.position().toPoint()).normalized());return
        if not self.drag:return
        delta=event.position().toPoint()-self.drag['start']
        if delta.manhattanLength()<QApplication.startDragDistance():return
        if not self.drag['free'] or self.drag['transfer']:
            state=self.drag;self.drag=None;offset=state['start']-state['rect'].topLeft();drag=QDrag(self)
            drag.setMimeData(mime_for({'mode':'move','id':state['node'],'project':self.canvas._project.id,'offset_x':offset.x(),'offset_y':offset.y()}));drag.setPixmap(self.image.copy(state['rect'].translated(-20,-20)));drag.setHotSpot(offset);drag.exec(Qt.DropAction.MoveAction);return
        geometry=dict(self.drag['geometry']);edge=self.drag['edge']
        dx,dy=(round(v/self.canvas.snap)*self.canvas.snap for v in (delta.x(),delta.y()))
        if not edge:geometry['x']=max(0,geometry['x']+dx);geometry['y']=max(0,geometry['y']+dy)
        else:
            if 'e' in edge:geometry['width']=max(24,geometry['width']+dx)
            if 's' in edge:geometry['height']=max(24,geometry['height']+dy)
            if 'w' in edge:geometry['x']=max(0,geometry['x']+dx);geometry['width']=max(24,geometry['width']-dx)
            if 'n' in edge:geometry['y']=max(0,geometry['y']+dy);geometry['height']=max(24,geometry['height']-dy)
        self.drag['result']=geometry;self.drag['preview']=QRect(self.drag['rect']).translated(dx,dy) if not edge else QRect(self.drag['rect'].topLeft()+QPoint(dx if 'w' in edge else 0,dy if 'n' in edge else 0),QSize(geometry['width'],geometry['height']));self.update()

    def mouseReleaseEvent(self,event):
        """Registra uma alteração reversível, como no canvas Qt."""
        if self.rubber:
            rect=self.rubber.geometry();self.rubber.hide();self.rubber.deleteLater();self.rubber=None
            nodes=self.canvas._project.find(self.rubber_parent).children
            identifiers=[node.id for node in nodes if node.id in self.rectangles and rect.intersects(self.rectangles[node.id])]
            if identifiers:self.canvas.components_selected.emit(identifiers)
        drag=self.drag;self.drag=None
        if drag and drag.get('result'):self.canvas.geometry_committed.emit(drag['node'],drag['result'])
        self.update()

    def mouseDoubleClickEvent(self,event):
        """O editor de texto pertence à ferramenta, nunca ao app sendo desenhado."""
        node=self.hit(event.position().toPoint());self.canvas.component_selected.emit(node.id);self.canvas.inline_edit_requested.emit()

    def contextMenuEvent(self,event):
        """Oferece o mesmo catálogo e os mesmos comandos da bancada Qt."""
        self.canvas.context_requested.emit(self.hit(event.pos()).id,event.globalPos())

    def dragEnterEvent(self,event):
        """Recebe apenas o formato de componentes já reconhecido pelo editor."""
        if read_payload(event.mimeData()) or self.canvas.external_image(event.mimeData()):event.acceptProposedAction()

    def dragMoveEvent(self,event):
        """Mantém o arraste sobre o retrato nativo, sem repassar eventos para GTK."""
        if read_payload(event.mimeData()) or self.canvas.external_image(event.mimeData()):event.acceptProposedAction()

    def insert(self,payload,point,image_file=None):
        """Resolve contêiner/ordem/posição usando os retângulos nativos e o modelo."""
        project=self.canvas._project;node=self.hit(point);kind=ComponentKind(payload['kind']) if payload.get('mode')=='new' else project.find(payload.get('id')).kind
        while node and not node.accepts(kind):node=project.parent_of(node.id)
        if node is None or not self.canvas.can_drop(payload,node.id):return False
        rect=self.rectangles.get(node.id,QRect());geometry=None;index=len(node.children)
        if node.layout==LayoutKind.FREE:geometry={'x':max(0,point.x()-rect.x()-payload.get('offset_x',0)),'y':max(0,point.y()-rect.y()-payload.get('offset_y',0))}
        else:
            horizontal=node.layout==LayoutKind.HORIZONTAL
            for i,child in enumerate(node.children):
                area=self.rectangles.get(child.id)
                if area and (point.x()<area.center().x() if horizontal else point.y()<area.center().y()):index=i;break
        if image_file:self.canvas.image_dropped.emit(image_file,node.id,index,geometry)
        else:self.canvas.drop_requested.emit(payload,node.id,index,geometry)
        return True

    def dropEvent(self,event):
        """Insere ou transfere somente depois da mesma validação usada no canvas Qt."""
        payload=read_payload(event.mimeData())
        image=self.canvas.external_image(event.mimeData())
        if image:payload={'mode':'new','kind':'image'}
        if payload and self.insert(payload,event.position().toPoint(),image):event.acceptProposedAction()
