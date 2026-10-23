"""Mapa de interfaces reais e inspeção de transições derivadas dos mesmos blocos."""
import json
from PySide6.QtCore import Qt,QPointF,QTimer
from PySide6.QtGui import QColor,QPen,QBrush,QPainterPath
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QToolButton,QLabel,QLineEdit,QTreeWidget,QTreeWidgetItem,
    QSplitter,QFormLayout,QPushButton,QMenu,QDialog,QMessageBox)
from makebench.core.navigation import navigation_edges,find_navigation_block,connect_navigation,remove_navigation_block,effective_edge_states
from .map_items import MapNode,MapEdge,GroupHeader,CARD_WIDTH,CARD_HEIGHT
from .map_view import NavigationView
from .map_preview import ThumbnailCache
from .map_connections import ConnectionDialog
from .theme import manager,icon


class MapPanel(QWidget):
    """Composição em miniatura, navegação por teclado e inspeção contextual no mesmo espaço."""
    def __init__(self,window):
        """As miniaturas e preferências de grupos nunca viram outra fonte de dados do app."""
        super().__init__();self.window=window;self.nodes={};self.edges=[];self._signature=None;self._fit_project=None;self.collapsed=set();self.selected_key=None;self._syncing=False
        self.previews=ThumbnailCache(self);self.previews.ready.connect(self.thumbnail_ready)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(4)
        row=QHBoxLayout();row.setContentsMargins(8,4,8,0);self.summary=QLabel();row.addWidget(self.summary,1);self.interface_actions=[]
        for symbol,label,callback in [('settings','Aplicativo…',window.application_settings),('add','Nova interface…',window.new_window_dialog),('logic','Conectar…',self.connect_dialog),('map','Organizar',self.organize),('fit','Enquadrar tudo',self.fit)]:
            button=QToolButton();button.setIcon(icon(symbol));button.setProperty('makebenchIcon',symbol);button.setText(label);button.setToolTip(label);button.setAccessibleName(label);button.setAutoRaise(True);button.clicked.connect(callback)
            if symbol in {'add','logic'}:button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            if symbol not in {'settings','add','fit'}:self.interface_actions.append(button)
            row.addWidget(button)
        layout.addLayout(row);self.splitter=QSplitter();self.splitter.setHandleWidth(4);layout.addWidget(self.splitter,1)
        self.outline_panel=QWidget();left=QVBoxLayout(self.outline_panel);left.setContentsMargins(6,2,2,4);left.setSpacing(6)
        self.search=QLineEdit();self.search.setPlaceholderText('Buscar interface…');self.search.setClearButtonEnabled(True);self.search.textChanged.connect(self.filter_outline);left.addWidget(self.search)
        self.outline=QTreeWidget();self.outline.setHeaderHidden(True);self.outline.setAccessibleName('Interfaces, estados e transições');self.outline.itemSelectionChanged.connect(self.outline_selected);self.outline.itemActivated.connect(self.outline_open);self.outline.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.outline.customContextMenuRequested.connect(self.outline_menu);left.addWidget(self.outline)
        self.outline_panel.setMinimumWidth(170);self.splitter.addWidget(self.outline_panel)
        self.view=NavigationView(self);self.view.scene().selectionChanged.connect(self.selection_changed);self.splitter.addWidget(self.view)
        self.details=QWidget();self.details.setMinimumWidth(220);self.details.setMaximumWidth(330);self.detail_layout=QVBoxLayout(self.details);self.detail_layout.setContentsMargins(8,8,8,8);self.detail_layout.setAlignment(Qt.AlignmentFlag.AlignTop);self.splitter.addWidget(self.details);self.details.hide();self.splitter.setSizes([195,850,260])
        self.hint=QLabel('Selecione uma interface ou conexão para inspecionar. Duplo clique abre o Designer.');self.hint.hide();self.view.setToolTip(self.hint.text())
        self._outline_items={}
        stored=window.settings.value('workspace/map_panels')
        if stored:self.splitter.restoreState(stored)
        self.splitter.splitterMoved.connect(lambda *_:window.settings.setValue('workspace/map_panels',self.splitter.saveState()))

    def sync(self):
        """Topologia e miniaturas têm invalidação independente; seleção e zoom sobrevivem."""
        project=self.window.project;empty=bool(project.metadata.get('empty_map'));self.summary.setText((project.application.get('name') or project.name)+' · '+project.application.get('backend','qt').upper());self.summary.setToolTip('Mapa das janelas e estados do aplicativo')
        for action in self.interface_actions:action.setEnabled(not empty)
        if getattr(self,'_project',None)!=project.id:
            self._project=project.id;self.collapsed=set(self.window.settings.value('map/collapsed/'+project.id,[],type=list));self.selected_key=None
        edges=navigation_edges(project);visual={'roots':[(r.id,r.properties.get('title','Interface'),r.properties.get('initial_state','@default'),len(list(r.walk()))) for r in project.roots], 'states':{r.id:[(s['id'],s['name']) for s in project.states.get(r.id,[])] for r in project.roots},'positions':project.map_layout,'entry':project.entry_window,'edges':edges,'collapsed':sorted(self.collapsed),'empty':empty,'theme':manager().tokens,'scale':manager().scale}
        signature=json.dumps(visual,sort_keys=True)
        if signature!=self._signature:
            self._signature=signature;self.rebuild(edges,empty)
        if not empty:
            for key in self.nodes:
                owner,state=key.split('|',1);self.previews.request(key,project.effective_root(owner,state),project.application.get('backend','qt'),self.window.assets.read)
        self.previews.retain(set(self.nodes))

    def rebuild(self,edges,empty):
        """Reconstrói só topologia alterada e mantém uma lista nativa acessível do mapa."""
        thumbnails={key:(node.thumbnail,node.preview_error) for key,node in self.nodes.items()}
        selected_edge=next(((line.edge['flow'],line.edge['block']) for line in self.edges if line.isSelected()),None)
        self.details.hide()
        self._syncing=True;self.view.connection=None;self.view.connection_item=None;scene=self.view.scene();scene.clear();self.nodes={};self.edges=[];self.outline.clear();self._outline_items={}
        scene.setBackgroundBrush(QColor(manager().tokens['canvas']));self.view.empty_hint.setVisible(empty);self.view.empty_action.setVisible(empty);self.view.position_hint();self.outline_panel.setVisible(not empty)
        if empty:self.details.hide();scene.setSceneRect(0,0,1000,650);self._syncing=False;return
        project=self.window.project;incoming={e['target'] for e in edges if e['op']=='open_window'}
        for row,root in enumerate(project.roots):
            states=[{'id':'@default','name':'Padrão'},*project.states.get(root.id,[])];title=root.properties.get('title','Interface');tree_root=QTreeWidgetItem([title]);tree_root.setIcon(0,icon('window'));tree_root.setData(0,Qt.ItemDataRole.UserRole,root.id+'|'+root.properties.get('initial_state','@default'));self.outline.addTopLevelItem(tree_root)
            representative=root.properties.get('initial_state','@default') if root.id in self.collapsed else None
            for column,state in enumerate(states):
                key=root.id+'|'+state['id'];item=QTreeWidgetItem([state['name']+(' · inicial' if root.id==(project.entry_window or project.root.id) and state['id']==root.properties.get('initial_state','@default') else '')]);item.setData(0,Qt.ItemDataRole.UserRole,key);tree_root.addChild(item);self._outline_items[key]=item
                if representative is not None and state['id']!=representative:continue
                initial=root.id==(project.entry_window or project.root.id) and state['id']==root.properties.get('initial_state','@default');issue='Sem transição de entrada por blocos.' if root.id!=(project.entry_window or project.root.id) and root.id not in incoming else ''
                if any(f.get('body') is None for f in project.editable_flows if project.window_of(f['event']['component']).id==root.id):issue='Há um comportamento incompleto nesta interface.'
                node=MapNode(key,title+'\nJanela · '+state['name'],project.map_layout.get(key,[column*(CARD_WIDTH+70),row*(CARD_HEIGHT+135)]),self.view,initial,issue,len(list(root.walk()))-1);
                if key in thumbnails:node.thumbnail,node.preview_error=thumbnails[key]
                scene.addItem(node);self.nodes[key]=node
            tree_root.setExpanded(True);members=[node for key,node in self.nodes.items() if key.startswith(root.id+'|')]
            bounds=members[0].sceneBoundingRect()
            for node in members[1:]:bounds=bounds.united(node.sceneBoundingRect())
            bounds=bounds.adjusted(-18,-42,18,18);group=scene.addRect(bounds,QPen(QColor(manager().tokens['border']),1),QBrush(QColor(manager().tokens['panel'])));group.setZValue(-4)
            header=GroupHeader(('▸ ' if root.id in self.collapsed else '▾ ')+title+f' · {len(states)} estado(s)',root.id,self);scene.addItem(header);header.setPos(bounds.left()+12,bounds.top()+10)
        for edge in edges:self.add_edge(edge)
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-70,-70,70,70));self._syncing=False;self.filter_outline()
        if self.selected_key in self.nodes:self.nodes[self.selected_key].setSelected(True)
        elif selected_edge:
            line=next((line for line in self.edges if (line.edge['flow'],line.edge['block'])==selected_edge),None)
            if line:line.setSelected(True)

    def node_for(self,owner,state):
        """Estados recolhidos usam o cartão representante, mantendo IDs reais no inspetor."""
        return self.nodes.get(owner+'|'+state) or next((n for key,n in self.nodes.items() if key.startswith(owner+'|')),None)

    def add_edge(self,edge):
        """A seta deriva exclusivamente de um bloco de navegação executável."""
        project=self.window.project
        for state in effective_edge_states(project,edge):
            source=self.node_for(edge['source'],state)
            if edge['op']=='go_state':target=self.node_for(edge['source'],edge['target'])
            elif edge['op']=='open_window':
                root=project.find(edge['target']);target=self.node_for(root.id,root.properties.get('initial_state','@default')) if root else None
            elif edge['op']=='show_page':
                root=project.window_of(edge['target']);target=self.node_for(root.id,state) if root else None
            else:target=source
            if not source or not target:continue
            if source is target and edge['source'] in self.collapsed:continue
            start=source.scenePos()+QPointF(CARD_WIDTH,126);end=target.scenePos()+QPointF(0,126);path=QPainterPath(start)
            if target.pos().x()>source.pos().x():bend=max(35,(end.x()-start.x())/2);path.cubicTo(start+QPointF(bend,0),end-QPointF(bend,0),end)
            else:
                start=source.scenePos()+QPointF(CARD_WIDTH/2,0);end=target.scenePos()+QPointF(CARD_WIDTH/2,0);lane=min(start.y(),end.y())-65;path=QPainterPath(start);path.cubicTo(QPointF(start.x()+35,lane),QPointF(end.x()-35,lane),end)
            line=MapEdge(path,edge);self.view.scene().addItem(line);self.edges.append(line)

    def thumbnail_ready(self,key,image,error):
        """Atualiza um único cartão, inclusive depois de editar texto ou trocar imagem."""
        node=self.nodes.get(key)
        if node:
            if not image.isNull():node.thumbnail=image
            node.preview_error=error;node.update();node.setToolTip(node.label+('\n'+error if error else '\nDuplo clique abre o Designer.'))

    def selection_changed(self):
        """Clique simples inspeciona; abrir o Designer permanece uma ação explícita."""
        if self._syncing:return
        selected=self.view.scene().selectedItems();node=next((n for n in selected if isinstance(n,MapNode)),None);edge=next((n for n in selected if isinstance(n,MapEdge)),None)
        if node:
            self.selected_key=node.key;self.outline.blockSignals(True);self.outline.setCurrentItem(self._outline_items.get(node.key));self.outline.blockSignals(False)
            # Abrir o inspetor no mouse-down alteraria as coordenadas de um arraste.
            if not self.view.dragging_card:self.show_details(node=node)
        elif edge:self.selected_key=None;self.show_details(edge=edge.edge)
        else:self.details.hide()

    def clear_details(self):
        """Destrói só o inspetor lateral; miniaturas e cena continuam disponíveis."""
        while self.detail_layout.count():
            item=self.detail_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()

    def show_details(self,node=None,edge=None):
        """Inspeção mostra origem/evento/destino e ações ligadas ao documento."""
        self.clear_details();self.details.show();heading=QLabel('Transição' if edge else 'Interface');font=heading.font();font.setBold(True);heading.setFont(font);self.detail_layout.addWidget(heading)
        def label(text):
            """Campos de leitura aceitam nomes longos sem ampliar o painel."""
            field=QLabel(text);field.setWordWrap(True);field.setTextFormat(Qt.TextFormat.PlainText);self.detail_layout.addWidget(field)
        def action(text,callback):
            """Cada ação usa os mesmos comandos do Designer e da Lógica."""
            button=QPushButton(text);button.clicked.connect(callback);self.detail_layout.addWidget(button)
        if node:
            label(node.label);label(node.issue) if node.issue else None;owner,state=node.key.split('|',1);root=self.window.project.find(owner);label(f"{root.properties.get('width',640)} × {root.properties.get('height',480)} · {self.window.project.application.get('backend','qt').upper()}")
            action('Abrir Designer',lambda:self.activate(node.key));action('Editar ao iniciar',lambda:self.open_logic_for_node(node.key));action('Definir como inicial',lambda:self.set_initial(node.key))
        else:
            flow,block=find_navigation_block(self.window.project,edge['flow'],edge['block'])
            if not flow or not block:return
            owner=self.window.project.find(edge['source']);label(owner.properties.get('title','Interface')+' → '+edge['event']);target=self.window.project.find(edge['target']) if edge['target'] else None
            if block['op']=='go_state':label('Mudar para '+next((s['name'] for s in self.window.project.states.get(owner.id,[]) if s['id']==edge['target']),'Padrão'))
            elif target:label('Destino: '+target.display_name)
            else:label('Fechar esta janela')
            if block['op'] in {'go_state','open_window'}:action('Editar transição…',lambda:self.edit_edge(edge))
            action('Ver na Lógica',lambda:self.window.navigate_to_item('flow',edge['flow']));action('Ver Python gerado',lambda:self.open_edge_code(edge));action('Remover transição',lambda:self.remove_edge(edge))

    def filter_outline(self,_text=None):
        """Busca por janela/estado com ancestrais visíveis e identidade preservada."""
        query=self.search.text().casefold()
        for index in range(self.outline.topLevelItemCount()):
            root=self.outline.topLevelItem(index);visible=query in root.text(0).casefold()
            for i in range(root.childCount()):child=root.child(i);match=query in child.text(0).casefold() or query in root.text(0).casefold();child.setHidden(not match);visible=visible or match
            root.setHidden(not visible)

    def outline_selected(self):
        """A lista nativa também seleciona cartões recolhidos, sem exigir arraste."""
        if self._syncing:return
        item=self.outline.currentItem();key=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        if key:
            owner,state=key.split('|',1);node=self.node_for(owner,state)
            if node:self.view.scene().clearSelection();node.setSelected(True);self.view.ensureVisible(node)

    def outline_open(self,item,_column=0):
        """Enter ou ativação abre exatamente a composição selecionada."""
        key=item.data(0,Qt.ItemDataRole.UserRole)
        if key:self.activate(key)

    def outline_menu(self,point):
        """Alternativa por teclado/mouse aos gestos do espaço gráfico."""
        item=self.outline.itemAt(point);key=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        if key:menu=QMenu(self);self.populate_context(menu,key);menu.exec(self.outline.viewport().mapToGlobal(point))

    def populate_context(self,menu,key):
        """Ações contextuais preservam o escopo da janela sob o cursor."""
        owner,state=key.split('|',1);menu.addAction('Abrir Designer',lambda:self.activate(key));menu.addAction('Editar ao iniciar',lambda:self.open_logic_for_node(key));menu.addAction('Definir como inicial',lambda:self.set_initial(key));menu.addSeparator();menu.addAction('Atualizar prévia',lambda:self.refresh_thumbnail(key));menu.addAction('Expandir/recolher estados',lambda:self.toggle_group(owner));menu.addAction('Criar estado…',lambda:self.create_state(key));menu.addAction('Duplicar interface…',lambda:self.duplicate_interface(owner))

    def create_state(self,key):
        """Seleciona o dono antes de usar o mesmo comando de criação do editor."""
        self.window.activate_window(*key.split('|',1));self.window.new_state_dialog()

    def duplicate_interface(self,owner):
        """Duplicação usa remapeamento existente de componentes, estados e fluxos."""
        from PySide6.QtWidgets import QInputDialog
        from makebench.core.navigation import add_window
        title,ok=QInputDialog.getText(self,'Duplicar interface','Nome',text=self.window.project.find(owner).properties.get('title','Interface')+' — cópia')
        if ok and title.strip():self.window._edit(lambda:add_window(self.window.project,title,owner))

    def set_initial(self,key):
        """Janela e estado iniciais mudam juntos em uma única entrada de histórico."""
        owner,state=key.split('|',1)
        def change():
            """Persiste o destino real de inicialização, sem tabela paralela do mapa."""
            self.window.project.entry_window=owner;self.window.project.find(owner).properties['initial_state']=state
        self.window._edit(change)

    def toggle_group(self,owner):
        """Recolher altera só a preferência visual deste projeto."""
        if owner in self.collapsed:self.collapsed.remove(owner)
        else:self.collapsed.add(owner)
        self.window.settings.setValue('map/collapsed/'+self.window.project.id,sorted(self.collapsed));self.sync()

    def activate(self,key):
        """Duplo clique entra no estado exato do cartão."""
        owner,state=key.split('|',1);self.window.activate_window(owner,state);self.window.set_mode('Design')

    def open_logic_for_node(self,key):
        """A programação de abertura é ligada à janela correta."""
        owner,state=key.split('|',1);self.window.activate_window(owner,state);self.window.edit_logic(owner)

    def open_edge_code(self,edge):
        """Linha gerada aponta ao bloco que produz esta conexão."""
        line=self.window.logic.generated.lines.get((edge['flow'],edge['block']),1);self.window.show_generated_line(line)

    def connect_dialog(self):
        """Uma única janela substitui escolhas soltas de origem e destino."""
        if self.nodes:self.connect_nodes(self.selected_key or next(iter(self.nodes)),None)

    def connect_nodes(self,source,target):
        """Arraste e botão usam o mesmo editor de navegação e a mesma semântica."""
        dialog=ConnectionDialog(self,source,target)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.window._edit(lambda:connect_navigation(self.window.project,dialog.source.currentData(),dialog.event.currentData(),dialog.target.currentData(),dialog.closing.isChecked()))

    def edit_edge(self,edge):
        """Editar uma ligação altera o bloco original, inclusive dentro de uma condição."""
        flow,block=find_navigation_block(self.window.project,edge['flow'],edge['block'])
        if not block:return
        block={**block,**block.get('parameters',{})}
        state=(edge['states'] or ['@default'])[0];source=edge['source']+'|'+state;target=(edge['source']+'|'+block['state']) if block['op']=='go_state' else block['window']+'|'+self.window.project.find(block['window']).properties.get('initial_state','@default');dialog=ConnectionDialog(self,source,target,edge)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.window._edit(lambda:connect_navigation(self.window.project,dialog.source.currentData(),dialog.event.currentData(),dialog.target.currentData(),dialog.closing.isChecked(),(edge['flow'],edge['block'])))

    def remove_edge(self,edge):
        """Remove somente a ação de navegação, com suporte a desfazer/refazer."""
        self.window._edit(lambda:remove_navigation_block(self.window.project,edge['flow'],edge['block']))

    def organize(self):
        """Reposiciona cartões em linhas por janela, preservando todas as ligações."""
        positions={}
        for row,root in enumerate(self.window.project.roots):
            for col,state in enumerate(['@default',*[s['id'] for s in self.window.project.states.get(root.id,[])]]):positions[root.id+'|'+state]=[col*(CARD_WIDTH+70),row*(CARD_HEIGHT+135)]
        self.window._edit(lambda:self.window.project.map_layout.update(positions),refresh=False);self.sync();self.fit()

    def fit(self):
        """Enquadra todos os cartões sem tornar miniaturas desproporcionalmente grandes."""
        if not self.nodes:self.view.resetTransform();self.view.centerOn(self.view.sceneRect().center())
        else:
            self.view.fitInView(self.view.scene().itemsBoundingRect().adjusted(-24,-24,24,24),Qt.AspectRatioMode.KeepAspectRatio);scale=self.view.transform().m11()
            if scale>1.15:self.view.scale(1.15/scale,1.15/scale)
        self.view.zoom_changed.emit(self.view.transform().m11())

    def showEvent(self,event):
        """O primeiro enquadramento espera os painéis obterem dimensões reais."""
        super().showEvent(event)
        if self._fit_project!=self.window.project.id:self._fit_project=self.window.project.id;QTimer.singleShot(0,self.fit)

    def refresh_edges(self):
        """Reposiciona ligações durante o arraste sem reconstruir os cartões nativos."""
        for line in self.edges:self.view.scene().removeItem(line)
        self.edges=[]
        for edge in navigation_edges(self.window.project):self.add_edge(edge)

    def refresh_thumbnail(self,key):
        """Atualização manual só invalida esta composição, sem executar o aplicativo."""
        self.previews.invalidate(key);self.sync()
