"""Edição de janelas/estados e mapa derivado da lógica neutra."""
from PySide6.QtCore import Qt,QPointF,QRectF,Signal,QTimer
from PySide6.QtGui import QBrush,QColor,QPainter,QPainterPath,QPen,QFontMetricsF
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDialog,QDialogButtonBox,QFormLayout,QGraphicsItem,
    QGraphicsPathItem,QGraphicsRectItem,QGraphicsScene,QGraphicsSimpleTextItem,QGraphicsView,
    QHBoxLayout,QInputDialog,QLabel,QMessageBox,QMenu,QPushButton,QVBoxLayout,QWidget,QApplication)
from makebench.core.project import ComponentKind,ProjectError,new_id
from makebench.core.navigation import add_state,add_window,navigation_edges
from .theme import manager,icon


class MapNode(QGraphicsRectItem):
    """Nó navegável e reposicionável, com porta para criar uma transição."""
    def __init__(self,key,label,position,view):
        """Guarda apenas identidade e posição; a lógica fica no documento."""
        super().__init__(0,0,230,78)
        self.key=key;self.map_view=view
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable|QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPos(*position)
        t=manager().tokens
        self.setBrush(QColor(t['raised']));self.setPen(QPen(QColor(t['control']),1))
        text=QGraphicsSimpleTextItem('',self);text.setFont(QApplication.font());metrics=QFontMetricsF(text.font());text.setText('\n'.join(metrics.elidedText(line,Qt.TextElideMode.ElideRight,200) for line in label.splitlines()));text.setBrush(QColor(t['text']));text.setPos(12,12)
        port=QGraphicsSimpleTextItem('○',self);port.setBrush(QColor(t['accent']));port.setPos(207,44)
        self.setToolTip(label+'\n\nDuplo clique para entrar na interface. Arraste da porta à direita até outro nó para conectar.')

    def paint(self,painter,option,widget=None):
        """Cartão de interface com desenho Qt, seleção explícita e cantos discretos."""
        t=manager().tokens;painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(t['accent'] if self.isSelected() else t['control']),2 if self.isSelected() else 1));painter.setBrush(QColor(t['raised']));painter.drawRoundedRect(self.rect(),8,8)

    def mouseDoubleClickEvent(self,event):
        """Abre a composição no contexto exato deste nó."""
        key=self.key;panel=self.map_view.panel
        QTimer.singleShot(0,lambda:panel.activate(key));event.accept()


class NavigationView(QGraphicsView):
    """Canvas de mapa com zoom, pan e conexão por arraste entre portas."""
    zoom_changed=Signal(float)
    def __init__(self,panel):
        """Configura interação sem substituir o modelo por itens gráficos."""
        super().__init__(panel)
        self.graph_scene=QGraphicsScene(self);self.setScene(self.graph_scene)
        self.panel=panel;self.connection=None;self.connection_item=None;self._press_positions={}
        self.empty_hint=QLabel('Nenhuma interface\nCrie uma tela para começar.',self.viewport())
        self.empty_action=QPushButton(icon('add'),'Nova interface…',self.viewport());self.empty_action.setFixedSize(164,32);self.empty_action.clicked.connect(panel.window.new_window_dialog);self.empty_action.hide()
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter);self.empty_hint.setWordWrap(True)
        self.empty_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.empty_hint.hide()
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def node_at(self,point):
        """Resolve o nó mesmo quando texto ou porta recebe o clique."""
        item=self.itemAt(point)
        while item and not isinstance(item,MapNode):item=item.parentItem()
        return item

    def mousePressEvent(self,event):
        """Inicia ligação apenas na porta, preservando o arraste do corpo do nó."""
        self._press_positions={key:[node.pos().x(),node.pos().y()] for key,node in self.panel.nodes.items()}
        node=self.node_at(event.position().toPoint())
        if node:
            local=node.mapFromScene(self.mapToScene(event.position().toPoint()))
            if local.x()>197 and local.y()>34:self.connection=node.key;event.accept();return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        """Confirma ligação ou posição; uma edição corresponde a um Desfazer."""
        if self.connection:
            source=self.connection;self.connection=None
            if self.connection_item:self.graph_scene.removeItem(self.connection_item);self.connection_item=None
            target=self.node_at(event.position().toPoint())
            if target and target.key!=source:
                key=target.key;QTimer.singleShot(0,lambda:self.panel.connect_nodes(source,key))
            event.accept();return
        super().mouseReleaseEvent(event)
        positions={node.key:[node.pos().x(),node.pos().y()] for node in self.panel.nodes.values()}
        moved={key:value for key,value in positions.items() if key in self._press_positions and self._press_positions[key]!=value}
        self._press_positions={}
        if moved:
            project=self.panel.window.project
            def commit():
                """A cena só pode ser reconstruída depois que Qt termina o evento dos itens."""
                if self.panel.window.project is project:
                    self.panel.window._edit(lambda:project.map_layout.update(moved))
            QTimer.singleShot(0,commit)

    def mouseMoveEvent(self,event):
        """A ligação acompanha o cursor antes da confirmação, sem criar blocos ainda."""
        if self.connection:
            source=self.panel.nodes.get(self.connection)
            if source:
                start=source.scenePos()+QPointF(230,50);end=self.mapToScene(event.position().toPoint());path=QPainterPath(start)
                path.cubicTo(start+QPointF(80,0),end-QPointF(80,0),end)
                if self.connection_item is None:self.connection_item=self.graph_scene.addPath(path,QPen(QColor(manager().tokens['accent']),2,Qt.PenStyle.DashLine))
                else:self.connection_item.setPath(path)
            event.accept();return
        super().mouseMoveEvent(event)

    def resizeEvent(self,event):
        """A orientação pertence ao viewport, sem aumentar nem sumir com o zoom."""
        super().resizeEvent(event);self.position_hint()

    def position_hint(self):
        """Centraliza o estado vazio sem criar objetos editáveis no mapa."""
        width=min(360,max(0,self.viewport().width()-32));height=110
        self.empty_hint.setGeometry((self.viewport().width()-width)//2,(self.viewport().height()-height)//2-24,width,height)
        self.empty_action.move((self.viewport().width()-self.empty_action.width())//2,self.viewport().height()//2+32)

    def contextMenuEvent(self,event):
        """O espaço de interfaces cria janelas pelo botão direito, inclusive vazio."""
        node=self.node_at(event.pos());menu=QMenu(self);point=self.mapToScene(event.pos())
        def create():
            """Após o diálogo, posiciona a nova interface no ponto escolhido."""
            empty=bool(self.panel.window.project.metadata.get('empty_map'));before=set() if empty else {r.id for r in self.panel.window.project.roots};self.panel.window.new_window_dialog()
            root=next((r for r in self.panel.window.project.roots if r.id not in before),None)
            if root:
                self.panel.window._edit(lambda:self.panel.window.project.map_layout.update({root.id+'|@default':[point.x(),point.y()]}));self.panel.sync()
        menu.addAction('Criar interface aqui…',create)
        if node:
            menu.addAction('Entrar na interface',lambda:self.panel.activate(node.key))
            def state_here():
                """O estado pertence à interface sob o cursor, mesmo sem entrar nela."""
                self.panel.window.active_window=node.key.split('|')[0];self.panel.window.active_state='@default';self.panel.window.new_state_dialog()
            menu.addAction('Criar estado…',state_here)
        menu.exec(event.globalPos())

    def keyPressEvent(self,event):
        """Permite remover uma conexão selecionada sem exigir gestos precisos."""
        if event.key()==Qt.Key.Key_Escape and self.connection:
            self.connection=None
            if self.connection_item:self.graph_scene.removeItem(self.connection_item);self.connection_item=None
            event.accept();return
        if event.key()==Qt.Key.Key_Delete:
            selected=self.scene().selectedItems()
            edge=next((item.data(0) for item in selected if isinstance(item,QGraphicsPathItem) and item.data(0)),None)
            if edge:self.panel.remove_edge(edge);event.accept();return
        super().keyPressEvent(event)

    def wheelEvent(self,event):
        """Ctrl+roda amplia o mapa; a roda normal continua rolando a área."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor=1.15 if event.angleDelta().y()>0 else 1/1.15
            scale=self.transform().m11()*factor
            if .25<=scale<=4:self.scale(factor,factor);self.zoom_changed.emit(self.transform().m11())
            event.accept()
        else:super().wheelEvent(event)


class MapPanel(QWidget):
    """Mostra janelas/estados e as mesmas transições que existem nos blocos."""
    def __init__(self,window):
        """Cria comandos de mapa e adia leitura do documento até a sincronização."""
        super().__init__();self.window=window;self.nodes={};self.edge_labels=[];self._signature=None;self._fit_project=None
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0);row=QHBoxLayout();row.setContentsMargins(4,2,4,2)
        self.summary=QLabel();row.addWidget(self.summary,1)
        from PySide6.QtWidgets import QToolButton
        self.interface_actions=[]
        for symbol,label,callback in [('settings','Aplicativo…',window.application_settings),('add','Nova interface…',window.new_window_dialog),('new','Novo estado',window.new_state_dialog),('logic','Conectar…',self.connect_dialog),('map','Organizar',self.organize),('fit','Ajustar',self.fit)]:
            button=QToolButton();button.setIcon(icon(symbol));button.setProperty('makebenchIcon',symbol);button.setAutoRaise(True);button.setToolTip(label);button.setAccessibleName(label);button.clicked.connect(callback);row.addWidget(button)
            if symbol in {'settings','add'}:button.setText(label);button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            if symbol not in {'settings','add','fit'}:self.interface_actions.append(button)
        layout.addLayout(row);self.view=NavigationView(self);self.view.scene().selectionChanged.connect(self.show_selected_edge);layout.addWidget(self.view,1)
        hint=QLabel('Este é o espaço das interfaces do projeto. Botão direito cria uma interface; duplo clique entra nela para trabalhar em Design, Lógica e Código.')
        self.hint=hint;hint.setWordWrap(True);hint.hide();self.view.setToolTip(hint.text())

    def sync(self):
        """Reconstrói quando documento/tema mudam, mantendo posições salvas."""
        import json
        project=self.window.project
        app=project.application;empty=bool(project.metadata.get('empty_map'))
        self.summary.setText((app.get('name') or project.name)+' · '+app.get('backend','qt').upper()+(' · '+app['version'] if app.get('version') else ''))
        self.summary.setToolTip(app.get('id','Configurações do aplicativo'))
        for button in self.interface_actions:button.setEnabled(not empty)
        edges=navigation_edges(project)
        visual={'windows':[(r.id,r.properties.get('title','Janela'),r.properties.get('initial_state','@default')) for r in project.roots],
            'states':{key:[(state['id'],state['name']) for state in states] for key,states in project.states.items()},'entry':project.entry_window,'positions':project.map_layout,'edges':edges,'empty':empty}
        signature=json.dumps(visual,sort_keys=True)+str(manager().tokens)+str(manager().scale)
        if signature==self._signature:return
        self._signature=signature;scene=self.view.scene();self.view.connection=None;self.view.connection_item=None;self.edge_labels=[];scene.clear();self.nodes={}
        scene.setBackgroundBrush(QColor(manager().tokens['canvas']))
        empty=bool(project.metadata.get('empty_map'));self.view.empty_hint.setVisible(empty);self.view.empty_action.setVisible(empty);self.view.position_hint()
        if empty:
            scene.setSceneRect(0,0,1000,650);return
        incoming={edge['target'] for edge in navigation_edges(project) if edge['op']=='open_window'}
        for row,root in enumerate(project.roots):
            states=[{'id':'@default','name':'Padrão'},*project.states.get(root.id,[])]
            for column,state in enumerate(states):
                key=root.id+'|'+state['id']
                entry=' · início' if root.id==(project.entry_window or project.root.id) and state['id']==root.properties.get('initial_state','@default') else ''
                label=root.properties.get('title','Janela')[:27]+entry+'\n'+state['name'][:30]
                if state['id']=='@default' and root.id!=(project.entry_window or project.root.id) and root.id not in incoming:label+=' · sem entrada'
                node=MapNode(key,label,project.map_layout.get(key,[column*310,row*220]),self.view)
                scene.addItem(node);self.nodes[key]=node
        for root in project.roots:
            members=[node for key,node in self.nodes.items() if key.startswith(root.id+'|')]
            bounds=members[0].sceneBoundingRect()
            for node in members[1:]:bounds=bounds.united(node.sceneBoundingRect())
            bounds=bounds.adjusted(-16,-40,16,16)
            group=scene.addRect(bounds,QPen(QColor(manager().tokens['border']),1),QBrush(QColor(manager().tokens['panel'])));group.setZValue(-3)
            title=scene.addSimpleText(root.properties.get('title','Janela'));title.setBrush(QColor(manager().tokens['muted']));title.setPos(bounds.left()+12,bounds.top()+10);title.setZValue(-2)
        for edge in navigation_edges(project):
            sources=edge['states'] or ['@default']
            for state in sources:
                source=self.nodes.get(edge['source']+'|'+state)
                if edge['op']=='go_state':target=self.nodes.get(edge['source']+'|'+edge['target'])
                elif edge['op']=='open_window':
                    root=project.find(edge['target']);target=self.nodes.get(root.id+'|'+root.properties.get('initial_state','@default'))
                else:continue
                if not source or not target:continue
                source_rect=source.sceneBoundingRect();target_rect=target.sceneBoundingRect();vertical=False
                if target_rect.left()>source_rect.right():
                    start=QPointF(source_rect.right(),source_rect.center().y());end=QPointF(target_rect.left(),target_rect.center().y());path=QPainterPath(start);bend=max(30,(end.x()-start.x())/2);path.cubicTo(start+QPointF(bend,0),end-QPointF(bend,0),end)
                else:
                    # Retornos passam por cima; outra janela abaixo usa portas verticais.
                    # Evita curvas que ampliavam a cena muito além dos cartões.
                    below=target_rect.top()>source_rect.bottom()+20;vertical=True
                    start=QPointF(source_rect.center().x(),source_rect.bottom() if below else source_rect.top());end=QPointF(target_rect.center().x(),target_rect.top());path=QPainterPath(start)
                    if below:
                        bend=max(40,(end.y()-start.y())/2);path.cubicTo(start+QPointF(0,bend),end-QPointF(0,bend),end)
                    else:
                        lane=min(start.y(),end.y())-64;path.cubicTo(QPointF(start.x(),lane),QPointF(end.x(),lane),end)
                line=scene.addPath(path,QPen(QColor(manager().tokens['muted']),1.5));line.setZValue(-1)
                line.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True);line.setData(0,edge);line.setToolTip(edge['event']+' · Delete remove esta conexão')
                arrow=QPainterPath(end);arrow.lineTo(end+(QPointF(-4,-9) if vertical else QPointF(-9,-4)));arrow.lineTo(end+(QPointF(4,-9) if vertical else QPointF(-9,4)));arrow.closeSubpath()
                head=scene.addPath(arrow,QPen(Qt.PenStyle.NoPen),QBrush(QColor(manager().tokens['muted'])));head.setZValue(-1)
                head.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True);head.setData(0,edge)
                label=scene.addSimpleText(edge['event'][:30]);label.setBrush(QColor(manager().tokens['muted']));label.setPos(path.pointAtPercent(.5)+QPointF(0,-24));label.setZValue(2);label.hide();self.edge_labels.append((line,head,label))
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-40,-40,40,40))

    def show_selected_edge(self):
        """O nome da ação aparece só na conexão selecionada, reduzindo sobreposições."""
        for line,head,label in self.edge_labels:label.setVisible(line.isSelected() or head.isSelected())

    def showEvent(self,event):
        """Enquadra uma vez por projeto após o layout obter seu tamanho real."""
        super().showEvent(event)
        if self._fit_project!=self.window.project.id:
            self._fit_project=self.window.project.id;QTimer.singleShot(0,self.fit)

    def organize(self):
        """Restaura organização da esquerda para a direita como uma edição reversível."""
        self.window._edit(lambda:self.window.project.map_layout.clear());self.sync();self.fit()

    def fit(self):
        """Enquadra o mapa sem modificar seus dados ou posições."""
        if not self.nodes:
            self.view.resetTransform();self.view.centerOn(self.view.sceneRect().center());self.view.zoom_changed.emit(1);return
        self.view.fitInView(self.view.scene().itemsBoundingRect().adjusted(-24,-24,24,24),Qt.AspectRatioMode.KeepAspectRatio)
        scale=self.view.transform().m11()
        if scale>1.25:self.view.scale(1.25/scale,1.25/scale)
        self.view.zoom_changed.emit(self.view.transform().m11())

    def activate(self,key):
        """Seleciona janela/estado e muda para Design."""
        window,state=key.split('|',1);self.window.activate_window(window,state);self.window.set_mode('Design')

    def connect_dialog(self):
        """Oferece a mesma conexão por teclado, sem exigir arraste de portas."""
        keys=list(self.nodes)
        if len(keys)<2:self.window.statusBar().showMessage('Crie outra janela ou estado para conectar.',5000);return
        labels=[self.nodes[key].childItems()[0].text().replace('\n',' · ') for key in keys]
        source,ok=QInputDialog.getItem(self,'Conectar','Origem',labels,0,False)
        if not ok:return
        target,ok=QInputDialog.getItem(self,'Conectar','Destino',labels,1,False)
        if ok:self.connect_nodes(keys[labels.index(source)],keys[labels.index(target)])

    def connect_nodes(self,source,target):
        """Gera bloco no fluxo com filtro da origem; não cria tabela lógica paralela."""
        window_id,state=source.split('|',1);target_window,target_state=target.split('|',1)
        root=self.window.project.find(window_id)
        buttons=[n for n in root.walk() if n.kind==ComponentKind.BUTTON]
        if not buttons:self.window.statusBar().showMessage('Adicione um botão na janela de origem.',6000);return
        names=[f'{index+1}. '+(n.properties.get('code_name') or n.display_name) for index,n in enumerate(buttons)]
        dialog=QDialog(self);dialog.setWindowTitle('Conectar navegação');form=QFormLayout(dialog)
        choice=QComboBox();choice.addItems(names);form.addRow('Ao clicar em',choice)
        closing=QCheckBox('Fechar a janela de origem ao abrir o destino');closing.setVisible(window_id!=target_window);form.addRow(closing)
        controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Save).setText('Conectar');controls.accepted.connect(dialog.accept);controls.rejected.connect(dialog.reject);form.addRow(controls)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        selected_button=choice.currentIndex()
        from makebench.core.logic import create_flow
        def connect():
            """Grava a transição no fluxo, mantendo uma fonte de verdade."""
            flow=create_flow(self.window.project,buttons[selected_button].id,states=[state])
            if flow.get('body') is None:raise ProjectError('Complete os blocos deste evento antes de criar a conexão.')
            block={'id':new_id('block'),'op':'go_state','state':target_state} if window_id==target_window else {'id':new_id('block'),'op':'open_window','window':target_window,'close_current':closing.isChecked()}
            flow['body'].append(block);flow['workspace']={'workspaceComments':flow.get('workspace',{}).get('workspaceComments',[])}
        self.window._edit(connect)

    def remove_edge(self,edge):
        """Remove o bloco de navegação correspondente; mantém os demais efeitos."""
        flow=next(f for f in self.window.project.workflows if f['id']==edge['flow'])
        if len(flow.get('body',[]))>1 and QMessageBox.warning(self,'Remover transição?','Será removido somente o bloco desta navegação. As demais ações do evento continuam no fluxo.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
        def remove():
            """Remove os dados selecionados como uma operação reversível."""
            def visit(items):
                """Percorre dados estruturados sem executar conteúdo do projeto."""
                for item in list(items):
                    if item.get('id')==edge['block']:items.remove(item);return True
                    for key in ('then','else','body'):
                        if isinstance(item.get(key),list) and visit(item[key]):return True
                return False
            visit(flow['body']);flow['workspace']={'workspaceComments':flow.get('workspace',{}).get('workspaceComments',[])}
        self.window._edit(remove)


class NavigationMixin:
    """Mantém contexto selecionado sem gravá-lo no arquivo do aplicativo."""
    def install_navigation_editor(self):
        """Adiciona seletores, comandos e mapa de navegação real."""
        self.active_window=self.project.root.id;self.active_state='@default'
        self.window_selector=QComboBox();self.window_selector.setAccessibleName('Janela em edição');self.window_selector.setMaximumWidth(210)
        self.state_selector=QComboBox();self.state_selector.setAccessibleName('Estado em edição');self.state_selector.setMaximumWidth(170)
        self.context_bar.insertWidget(self.context_bar.actions()[0],self.window_selector)
        self.context_bar.insertWidget(self.context_bar.actions()[-1],self.state_selector)
        self.window_selector.currentIndexChanged.connect(self.window_selected)
        self.state_selector.currentIndexChanged.connect(self.state_selected)
        menu=self.menuBar().addMenu('&Projeto')
        for label,callback in [('Nova janela…',self.new_window_dialog),('Novo estado…',self.new_state_dialog),('Definir janela como inicial',self.make_entry_window),('Definir estado como inicial',self.make_initial_state),('Renomear estado…',self.rename_state_dialog),('Restaurar seleção do Padrão',self.restore_default_properties),('Remover estado',self.remove_state),('Remover janela',self.remove_window)]:
            action=menu.addAction(label);action.triggered.connect(callback)
        self.map_panel=MapPanel(self);self.tabs.addTab(self.map_panel,'Mapa')
        self.sync_navigation()

    def sync_navigation(self):
        """Reconcilia seleção com desfazer, carregamento e remoção de janelas."""
        if not hasattr(self,'window_selector'):return
        if self.active_window not in {r.id for r in self.project.roots}:
            self.active_window=self.project.root.id;self.active_state='@default'
        owner=self.project.window_of(self.selected_id)
        if owner and owner.id!=self.active_window:self.active_window=owner.id;self.active_state='@default'
        from .controls import reconcile_combo
        empty=bool(self.project.metadata.get('empty_map'));self.window_selector.setEnabled(not empty);self.state_selector.setEnabled(not empty)
        if empty:
            reconcile_combo(self.window_selector,[('Nenhuma interface',None)],None);reconcile_combo(self.state_selector,[],None);return
        reconcile_combo(self.window_selector,[(root.properties.get('title','Janela'),root.id) for root in self.project.roots],self.active_window)
        states=self.project.states.get(self.active_window,[])
        if self.active_state not in {'@default',*[s['id'] for s in states]}:self.active_state='@default'
        reconcile_combo(self.state_selector,[(self.project.find(self.active_window).properties.get('default_state_name','Padrão'),'@default'),*[(state['name'],state['id']) for state in states]],self.active_state)

    def activate_window(self,window_id,state='@default'):
        """Muda o contexto após confirmar alterações dos blocos e campos."""
        if not self._finish_field_edit():return
        self.active_window=window_id;self.active_state=state;self.selected_id=window_id;self._refresh()

    def window_selected(self):
        """Recebe escolha explícita de uma janela real."""
        if self.window_selector.currentData():self.activate_window(self.window_selector.currentData())

    def state_selected(self):
        """Revela uma variação mantendo a seleção válida da mesma janela."""
        if self.state_selector.currentData() is not None:
            if not self._finish_field_edit():return
            self.active_state=self.state_selector.currentData();self._refresh()

    def new_window_dialog(self):
        """Cria janela vazia ou cópia da composição atual com novos IDs."""
        dialog=QDialog(self);dialog.setWindowTitle('Nova interface');form=QFormLayout(dialog)
        from PySide6.QtWidgets import QLineEdit
        empty=bool(self.project.metadata.get('empty_map'));name=QLineEdit('Tela principal' if empty else 'Nova interface');name.setObjectName('new_interface_name');base=QComboBox();base.addItem('Em branco',None)
        if not empty:
            for root in self.project.roots:base.addItem('Duplicar '+root.properties.get('title','Janela'),root.id)
        form.addRow('Nome',name);form.addRow('Base',base)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Criar interface');buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted or not name.text().strip():return
        def create():
            """Cria o item solicitado com os valores validados do diálogo."""
            if self.project.metadata.pop('empty_map',False):
                root=self.project.root;root.properties['title']=name.text().strip()
            else:root=add_window(self.project,name.text(),base.currentData())
            self.active_window=root.id;self.active_state='@default';self.selected_id=root.id
        self._edit(create)

    def new_state_dialog(self):
        """Cria variação independente sobre a estrutura padrão."""
        from PySide6.QtWidgets import QLineEdit
        dialog=QDialog(self);dialog.setWindowTitle('Novo estado');form=QFormLayout(dialog)
        name=QLineEdit();base=QComboBox();base.addItem('Padrão','@default')
        for state in self.project.states.get(self.active_window,[]):base.addItem(state['name'],state['id'])
        base.setCurrentIndex(base.findData(self.active_state));form.addRow('Nome',name);form.addRow('Começar de',base)
        note=QLabel('Copia as diferenças da etapa escolhida. A estrutura continua vindo do Padrão.');note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Criar estado');buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        def create():
            """Cria o item solicitado com os valores validados do diálogo."""
            state=add_state(self.project,self.active_window,name.text(),base.currentData());self.active_state=state['id']
        self._edit(create)

    def make_entry_window(self):
        """Define explicitamente qual janela abre ao iniciar o aplicativo."""
        self._edit(lambda:setattr(self.project,'entry_window',self.active_window))

    def make_initial_state(self):
        """Define a variação aplicada antes do evento de início da janela."""
        self._edit(lambda:self.project.find(self.active_window).properties.update(initial_state=self.active_state))

    def rename_state_dialog(self):
        """Renomeia a variação mantendo IDs e todas as transições."""
        if self.active_state=='@default':
            root=self.project.find(self.active_window)
            name,ok=QInputDialog.getText(self,'Nome da composição padrão','Nome da etapa inicial',text=root.properties.get('default_state_name','Padrão'))
            if ok and name.strip():self._edit(lambda:root.properties.update(default_state_name=name.strip()))
            return
        state=next(s for s in self.project.states[self.active_window] if s['id']==self.active_state)
        name,ok=QInputDialog.getText(self,'Renomear estado','Nome',text=state['name'])
        if ok and name.strip():self._edit(lambda:state.update(name=name.strip()))

    def restore_default_properties(self):
        """Remove somente sobrescritas da seleção no estado ativo."""
        if self.active_state=='@default':return
        def restore():
            """Remove as diferenças escolhidas, preservando os demais dados."""
            state=next(s for s in self.project.states[self.active_window] if s['id']==self.active_state)
            state.get('overrides',{}).pop(self.selected_id,None)
        self._edit(restore)

    def remove_state(self):
        """Recusa exclusão de estado ainda referenciado pela lógica."""
        if self.active_state=='@default':return
        state_id=self.active_state
        for flow in self.project.workflows:
            if state_id in flow.get('states',[]) or any(e['target']==state_id for e in navigation_edges(self.project)):
                self._show_error('Revise os fluxos que usam este estado antes de removê-lo.');return
        def remove():
            """Remove os dados selecionados como uma operação reversível."""
            self.project.states[self.active_window]=[s for s in self.project.states[self.active_window] if s['id']!=state_id]
            if self.project.find(self.active_window).properties.get('initial_state')==state_id:self.project.find(self.active_window).properties['initial_state']='@default'
            self.active_state='@default'
        self._edit(remove)

    def remove_window(self):
        """Protege a raiz e janelas referenciadas; remoção é reversível pelo histórico."""
        if len(self.project.roots)==1:self._show_error('Mantenha pelo menos uma janela no aplicativo.');return
        identifier=self.active_window;ids={n.id for n in self.project.find(identifier).walk()}
        if any(e['target']==identifier for e in navigation_edges(self.project)) or any(f['event']['component'] in ids for f in self.project.workflows):
            self._show_error('Revise os fluxos desta janela e suas conexões antes de removê-la.');return
        def remove():
            """Remove os dados selecionados como uma operação reversível."""
            if identifier==self.project.root.id:self.project.root=self.project.windows.pop(0)
            else:self.project.windows=[r for r in self.project.windows if r.id!=identifier]
            self.project.states.pop(identifier,None);self.project.variables=[v for v in self.project.variables if v.get('window')!=identifier]
            if self.project.entry_window==identifier:self.project.entry_window=self.project.root.id
            self.active_window=self.project.root.id;self.active_state='@default';self.selected_id=self.project.root.id
        self._edit(remove)
