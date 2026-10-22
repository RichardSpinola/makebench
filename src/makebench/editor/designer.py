"""Ferramentas de composição, conversão reversível e enquadramento do canvas."""
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QAction,QKeySequence
from PySide6.QtWidgets import (QGraphicsScene,QGraphicsView,QHBoxLayout,QInputDialog,
    QLabel,QMenu,QPushButton,QScrollArea,QToolBar,QWidget)
from makebench.core.project import ComponentKind,LayoutKind,ProjectError


class ZoomView(QGraphicsView):
    """Hospeda widgets reais em proxy Qt; gestos continuam usando o mesmo canvas."""
    def __init__(self,canvas,parent=None):
        """Mantém a árvore editável e transforma somente sua apresentação."""
        super().__init__(parent)
        self.canvas=canvas;self.graph_scene=QGraphicsScene(self);self.setScene(self.graph_scene)
        self.proxy=self.graph_scene.addWidget(canvas);self.zoom=1
        self.setObjectName('pasteboard')
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._pan=False

    def update_bounds(self):
        """Inclui controles distantes no alcance da rolagem do designer."""
        project=self.canvas._project
        if project is None:return
        root=project.root
        size=self.canvas.minimumSizeHint()
        width=max(root.properties.get('width',640)+40,size.width())
        height=max(root.properties.get('height',480)+78,size.height())
        native=getattr(self.canvas,'native_size',None)
        if native and project.application.get('backend','qt')=='gtk':width,height=native.width(),native.height()
        self.canvas.resize(width,height)
        self.graph_scene.setSceneRect(QRectF(-48,-48,width+96,height+96))

    def set_zoom(self,value):
        """Aplica zoom limitado e informa a escala aos gestos de geometria."""
        self.zoom=max(.25,min(4,value));self.resetTransform();self.scale(self.zoom,self.zoom)
        self.canvas.view_scale=self.zoom

    def fit(self):
        """Enquadra a composição, preservando suas coordenadas no documento."""
        self.update_bounds();self.fitInView(self.proxy.sceneBoundingRect().adjusted(-20,-20,20,20),Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom=self.transform().m11();self.canvas.view_scale=self.zoom

    def wheelEvent(self,event):
        """Usa Ctrl+roda para zoom; rolagem normal não modifica a composição."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_zoom(self.zoom*(1.15 if event.angleDelta().y()>0 else 1/1.15));event.accept()
        else:super().wheelEvent(event)

    def keyPressEvent(self,event):
        """Espaço ativa pan enquanto estiver pressionado."""
        if event.key()==Qt.Key.Key_Space and not event.isAutoRepeat():
            self._pan=True;self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag);event.accept()
        else:super().keyPressEvent(event)

    def keyReleaseEvent(self,event):
        """Restaura seleção depois do gesto de pan."""
        if event.key()==Qt.Key.Key_Space:
            self._pan=False;self.setDragMode(QGraphicsView.DragMode.NoDrag);event.accept()
        else:super().keyReleaseEvent(event)


class DesignerMixin:
    """Coordena inserção, organização, seleção e propriedades com um só histórico."""
    def install_designer(self):
        """Acrescenta zoom e navegação de teclado sobre o canvas existente."""
        scroll=self.design_splitter.widget(1).findChild(QScrollArea)
        if scroll:
            scroll.takeWidget();parent=scroll.parentWidget();layout=parent.layout();position=layout.indexOf(scroll)
            layout.removeWidget(scroll);scroll.deleteLater();self.zoom_view=ZoomView(self.canvas)
            layout.insertWidget(position,self.zoom_view,1)
            def native_ready():
                """A primeira imagem GTK enquadra a janela; próximas edições preservam o zoom."""
                self.zoom_view.update_bounds()
                key=(self.project.id,self.active_window)
                if getattr(self,'_gtk_fitted',None)!=key:
                    self._gtk_fitted=key;self.zoom_view.fit()
            self.canvas.native_preview_ready.connect(native_ready)
            self.context_bar.addSeparator()
            self.zoom_actions=[]
            for label,callback in [('−',lambda:self.zoom_current(1/1.15)),('100%',lambda:self.zoom_current(absolute=1)),('+',lambda:self.zoom_current(1.15)),('Ajustar',self.fit_current_canvas)]:
                button=QPushButton(label if label=='100%' else '');button.setToolTip({'−':'Reduzir zoom','+':'Ampliar zoom','Ajustar':'Enquadrar interface'}.get(label,'Tamanho real'));button.setAccessibleName('Zoom '+label);button.setIcon(__import__('makebench.editor.theme',fromlist=['icon']).icon({'−':'zoom-out','+':'zoom-in','Ajustar':'fit'}.get(label,'actual')));button.setProperty('makebenchIcon',{'−':'zoom-out','+':'zoom-in','Ajustar':'fit'}.get(label,'actual'));button.clicked.connect(callback);self.zoom_actions.append(self.context_bar.addWidget(button))
            action=QAction('Ajustar composição',self);action.setShortcut(QKeySequence('Ctrl+0'));action.triggered.connect(self.fit_current_canvas);self.addAction(action)
            actual=QAction('Tamanho real',self);actual.setShortcut(QKeySequence('Ctrl+Alt+0'));actual.triggered.connect(lambda:self.zoom_current(absolute=1));self.addAction(actual)
        rename=QAction('Renomear seleção',self);rename.setShortcut(QKeySequence('F2'));rename.triggered.connect(self.rename_selected);self.addAction(rename)
        self.canvas.inline_edit_requested.connect(self.rename_selected)
        self.canvas.image_dropped.connect(self.import_image_drop)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.tree_menu)
        self.canvas.context_requested.connect(self.canvas_menu)
        self.selected_ids={self.selected_id};self._multi_syncing=False
        self.tree.setSelectionMode(self.tree.SelectionMode.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self.tree_multi_selected)
        self.canvas.components_selected.connect(self.select_multiple)
        self.inspector.selection_command.connect(self.selection_command)
        self.inspector.layout_preview_requested.connect(self.preview_layout)
        self.canvas.layout_requested.connect(self._change_property)
        self.inspector.restore_requested.connect(self.restore_state_property)

    def rename_selected(self):
        """Edita texto da seleção mantendo a mesma validação e histórico do inspetor."""
        node=self.project.find(self.selected_id)
        if not node:return
        if 'text' in node.properties and node.id in self.canvas._frames:
            from .inline import InlineText,InlineParagraph
            shown=self.canvas._project.find(node.id) or node
            parent=self.canvas._frames[node.id]
            surface=getattr(self.canvas,'gtk_surface',None)
            if surface and surface.isVisible() and node.id in surface.rectangles:parent=surface
            editor=(InlineParagraph if '\n' in shown.properties.get('text','') or node.kind==ComponentKind.OUTPUT else InlineText)(shown.properties.get('text',''),parent)
            editor.setAccessibleName('Editar texto do componente');editor.setGeometry((surface.rectangles[node.id] if parent is surface else parent.rect()).adjusted(4,4,-4,-4))
            def finish(text,accept):
                """Finaliza a edição antes de atualizar a vista, preservando cancelamento."""
                editor.hide();editor.setParent(None);editor.deleteLater()
                if accept:self._change_property(node.id,'text',text)
                self.canvas.setFocus()
            editor.finished.connect(finish);editor.show();editor.raise_();editor.setFocus();return
        key='text' if 'text' in node.properties else 'title' if 'title' in node.properties else 'code_name'
        value,ok=QInputDialog.getText(self,'Editar '+node.display_name,'Texto' if key=='text' else 'Nome',text=node.properties.get(key,''))
        if ok:self._change_property(node.id,key,value)

    def tree_menu(self,point):
        """Expõe comandos reais no contexto da seleção, com os mesmos estados."""
        menu=QMenu(self)
        self.insertion_menu(menu)
        menu.addSeparator()
        for action in [self.duplicate_action,self.remove_action,self.up_action,self.down_action,self.page_action]:menu.addAction(action)
        action=menu.addAction('Editar lógica…');action.triggered.connect(lambda:self.edit_logic(self.selected_id))
        menu.exec(self.tree.viewport().mapToGlobal(point))

    def insertion_menu(self,menu):
        """Elementos completos ficam numa área de inserir, separada de seleção/pan."""
        from makebench.core.project import KIND_LABELS
        from .theme import icon
        insert=menu.addMenu('Inserir elemento')
        for kind,label in KIND_LABELS.items():
            if kind==ComponentKind.WINDOW:continue
            action=insert.addAction(icon(kind.value),label)
            action.setEnabled(self.active_state=='@default')
            action.triggered.connect(lambda _,kind=kind:self.insert_kind(kind))
        return insert

    def canvas_menu(self,identifier,position):
        """Menu contextual do canvas usa os mesmos comandos e histórico do editor."""
        self._select(identifier);menu=QMenu(self);self.insertion_menu(menu);menu.addSeparator()
        menu.addAction(self.duplicate_action);menu.addAction(self.remove_action)
        menu.addAction('Editar texto',self.rename_selected)
        if self.project.find(identifier).kind in {ComponentKind.BUTTON,ComponentKind.WINDOW}:menu.addAction('Editar lógica',lambda:self.edit_logic(identifier))
        menu.exec(position)

    def convert_layout(self,node,mode):
        """Captura/restaura geometria livre sem descartar filhos, IDs ou comentários."""
        mode=LayoutKind(mode)
        if node.layout==mode:return False
        if node.layout==LayoutKind.FREE and mode==LayoutKind.GRID:
            raise ProjectError('A conversão de Livre para Grade ainda não é suportada. Use Coluna ou Linha primeiro.')
        if mode==LayoutKind.FREE:
            for child in node.children:
                saved=child.properties.get('free_geometry')
                if saved:
                    child.geometry=dict(saved)
                elif child.id in self.canvas._frames:
                    frame=self.canvas._frames[child.id];parent=self.canvas._frames[node.id]
                    point=frame.mapTo(parent,frame.rect().topLeft())
                    child.geometry=dict(x=max(0,point.x()),y=max(0,point.y()),width=max(1,frame.width()),height=max(1,frame.height()))
                    child.properties['free_geometry']=dict(child.geometry)
        elif node.layout==LayoutKind.FREE:
            for child in node.children:child.properties['free_geometry']=dict(child.geometry)
            node.children.sort(key=lambda child:(child.geometry['y'],child.geometry['x']) if mode==LayoutKind.VERTICAL else (child.geometry['x'],child.geometry['y']))
        node.layout=mode;return True

    def tree_multi_selected(self):
        """Sincroniza seleção múltipla nativa sem confundir itens de estado com controles."""
        if self._refreshing or self._multi_syncing:return
        ids=[item.data(0,Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()]
        ids=[identifier for identifier in ids if self.project.find(identifier)]
        if ids:self.select_multiple(ids)

    def select_multiple(self,identifiers):
        """Mantém uma única seleção compartilhada entre árvore, canvas e inspetor."""
        ids={identifier for identifier in identifiers if self.project.find(identifier) and self.project.window_of(identifier).id==self.active_window}
        if not ids:return
        self.selected_ids=ids
        if self.selected_id not in ids:self.selected_id=next(iter(ids))
        self._multi_syncing=True;self.tree.blockSignals(True)
        for identifier,item in self._tree_items.items():item.setSelected(identifier in ids)
        self.tree.blockSignals(False);self._multi_syncing=False
        self.canvas.select_many(ids)
        if len(ids)>1:self.inspector.set_multiple([self.project.find(identifier) for identifier in ids])
        else:
            node=self.canvas._project.find(self.selected_id)
            if node:
                overrides={}
                if self.active_state!='@default':
                    state=next(s for s in self.project.states[self.active_window] if s['id']==self.active_state)
                    overrides=state.get('overrides',{}).get(node.id,{})
                self.inspector.set_component(self.project,node,overrides,self.active_state!='@default')

    def selection_command(self,mode):
        """Alinha, distribui ou iguala dimensões em uma única entrada do histórico."""
        nodes=[self.project.find(identifier) for identifier in self.selected_ids]
        parents={self.project.parent_of(n.id).id if self.project.parent_of(n.id) else None for n in nodes}
        if len(nodes)<2 or len(parents)!=1 or None in parents:return
        parent=self.project.find(next(iter(parents)))
        if parent.layout!=LayoutKind.FREE or self.active_state!='@default':
            self.statusBar().showMessage('Alinhamento de grupo exige irmãos em um contêiner Livre no Padrão.',6000);return
        def apply():
            """Aplica a operação completa à seleção em uma entrada do histórico."""
            boxes=[n.geometry for n in nodes]
            left=min(g['x'] for g in boxes);right=max(g['x']+g['width'] for g in boxes)
            top=min(g['y'] for g in boxes);bottom=max(g['y']+g['height'] for g in boxes)
            for node in nodes:
                g=node.geometry
                if mode=='left':g['x']=left
                elif mode=='right':g['x']=right-g['width']
                elif mode=='center_x':g['x']=round((left+right-g['width'])/2)
                elif mode=='top':g['y']=top
                elif mode=='bottom':g['y']=bottom-g['height']
                elif mode=='center_y':g['y']=round((top+bottom-g['height'])/2)
                elif mode=='same_width':g['width']=max(b['width'] for b in boxes)
                elif mode=='same_height':g['height']=max(b['height'] for b in boxes)
            if mode in {'distribute_x','distribute_y'} and len(nodes)>=3:
                axis,size=('x','width') if mode=='distribute_x' else ('y','height')
                ordered=sorted(nodes,key=lambda n:n.geometry[axis]);start=ordered[0].geometry[axis]
                end=ordered[-1].geometry[axis]+ordered[-1].geometry[size]
                gap=(end-start-sum(n.geometry[size] for n in ordered))/(len(ordered)-1)
                position=start
                for node in ordered:node.geometry[axis]=round(position);position+=node.geometry[size]+gap
        self._edit(apply)

    def preview_layout(self,node_id,mode):
        """Mostra uma simulação em cópia; somente clicar confirma e gera histórico."""
        from dataclasses import replace
        root=self.project.effective_root(self.active_window,self.active_state)
        if mode:
            node=next((n for n in root.walk() if n.id==node_id),None)
            if node:node.layout=LayoutKind(mode)
        view=replace(self.project,root=root,windows=[])
        self.canvas.set_project(view);self.canvas.select(self.selected_id)
        self.canvas.select_many(getattr(self,'selected_ids',{self.selected_id}))
        self.zoom_view.update_bounds()

    def restore_state_property(self,node_id,key):
        """Retira uma diferença individual, preservando as outras variações."""
        if self.active_state=='@default':return
        def restore():
            """Remove as diferenças escolhidas, preservando os demais dados."""
            state=next(s for s in self.project.states[self.active_window] if s['id']==self.active_state)
            state.get('overrides',{}).get(node_id,{}).pop(key,None)
        self._edit(restore)

    def import_image_drop(self,filename,parent_id,index,geometry):
        """Importa a imagem escolhida por arraste como uma edição reversível."""
        from pathlib import Path
        def insert():
            """Importa e insere um recurso validado no destino escolhido."""
            source=self.assets.import_image(Path(filename))
            node=self.project.add(parent_id,ComponentKind.IMAGE);node.properties.update(source=source,image_name=Path(filename).name)
            self.project.move(node.id,parent_id,index)
            if geometry and self.project.find(parent_id).layout==LayoutKind.FREE:
                self.project.set_geometry(node.id,{key:max(0,min(20000,round(value/self.canvas.snap)*self.canvas.snap)) for key,value in geometry.items()})
            self.selected_id=node.id
        self._edit(insert)

    def fit_current_canvas(self):
        """Enquadra a área de criação ativa em vez de mover um painel oculto."""
        if self._mode=='Mapa':self.map_panel.fit()
        elif self._mode=='Design':self.zoom_view.fit()
        elif self._mode=='Lógica' and self.logic.ready:self.logic.page.runJavaScript('window.makebench.workspace.zoomToFit()')

    def zoom_current(self,factor=1,absolute=None):
        """Mantém zoom do mapa independente do zoom de composição."""
        if self._mode=='Mapa':
            view=self.map_panel.view;scale=absolute if absolute is not None else view.transform().m11()*factor
            view.resetTransform();view.scale(max(.25,min(4,scale)),max(.25,min(4,scale)))
        elif self._mode=='Design':self.zoom_view.set_zoom(absolute if absolute is not None else self.zoom_view.zoom*factor)

    def top_level_selection(self):
        """Evita duplicar ou remover descendentes duas vezes na mesma operação de grupo."""
        selected=getattr(self,'selected_ids',{self.selected_id});result=[]
        for node in self.project.walk():
            if node.id not in selected:continue
            parent=self.project.parent_of(node.id);nested=False
            while parent:
                if parent.id in selected:nested=True;break
                parent=self.project.parent_of(parent.id)
            if not nested:result.append(node.id)
        return result or [self.selected_id]
