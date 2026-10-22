"""Inspetor contextual por escopo, com seções recolhíveis e campos acessíveis."""
from PySide6.QtCore import Qt,Signal,QEvent,QTimer
from PySide6.QtWidgets import (QCheckBox,QComboBox,QFormLayout,QGridLayout,QHBoxLayout,QLabel,QLineEdit,
    QMenu,QPushButton,QSpinBox,QToolButton,QVBoxLayout,QWidget)
from makebench.core.project import KIND_LABELS,LAYOUT_LABELS,ComponentKind,LayoutKind


class Inspector(QWidget):
    """Mostra conteúdo, organização, tamanho e eventos pertinentes à seleção."""
    property_changed=Signal(str,str,object)
    image_requested=Signal(str);image_cleared=Signal(str);logic_requested=Signal(str)
    selection_command=Signal(str);layout_preview_requested=Signal(str,str)
    restore_requested=Signal(str,str)

    def __init__(self,parent=None):
        """Guarda apenas estado de apresentação; o documento continua no projeto."""
        super().__init__(parent)
        self.form=QFormLayout(self);self.form.setContentsMargins(12,12,12,12);self.form.setSpacing(8)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields=self.form;self._expanded={};self._overrides={};self._kind=''
        self.setMinimumWidth(220)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(400)
        self.preview_timer.timeout.connect(self.emit_preview);self._preview=None

    def clear(self):
        """Remove as vistas anteriores, incluindo conexões e campos de outro escopo."""
        self.preview_timer.stop();self._preview=None
        while self.form.rowCount():
            row=self.form.takeRow(0)
            for item in (row.labelItem,row.fieldItem):
                if item and item.widget():
                    widget=item.widget();widget.hide();widget.setParent(None);widget.deleteLater()
        self.fields=self.form

    def section(self,title,expanded=True):
        """Cria uma seção cuja abertura é lembrada por tipo de componente."""
        wrapper=QWidget();layout=QVBoxLayout(wrapper);layout.setContentsMargins(0,0,0,0);layout.setSpacing(6)
        header=QToolButton();header.setText(title);header.setCheckable(True)
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        body=QWidget();body.setProperty('card',True);form=QFormLayout(body);form.setContentsMargins(12,12,12,12);form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        key=(self._kind,title);opened=self._expanded.get(key,expanded)
        header.setChecked(opened);header.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow);body.setVisible(opened)
        def toggle(value):
            """Lembra abertura da seção sem alterar o documento."""
            self._expanded[key]=value;body.setVisible(value);header.setArrowType(Qt.ArrowType.DownArrow if value else Qt.ArrowType.RightArrow)
        header.toggled.connect(toggle);layout.addWidget(header);layout.addWidget(body);self.form.addRow(wrapper)
        self.fields=form

    def set_component(self,project,node,overrides=None,state_mode=False):
        """Renderiza propriedades efetivas; ● identifica diferenças do estado ativo."""
        self.clear();self._kind=node.kind.value;self._overrides=overrides or {};self.state_mode=state_mode
        heading=QLabel(KIND_LABELS[node.kind]);heading.setProperty('section',True);self.form.addRow(heading)
        parent=project.parent_of(node.id)
        if parent:
            caption=QLabel('Dentro de: '+(parent.properties.get('code_name') or parent.display_name));caption.setWordWrap(True);caption.setProperty('muted',True);self.form.addRow(caption)
        if node.kind==ComponentKind.WINDOW and node.id==project.root.id:
            self.section('Projeto');self._text_field('Nome do projeto','@project','name',project.name)
        self.section('Conteúdo')
        for key,label in [('title','Título'),('text','Texto'),('placeholder','Dica do campo')]:
            if key in node.properties:self._text_field(label,node.id,key,node.properties[key])
        if node.kind==ComponentKind.IMAGE:
            filename=QLabel(node.properties.get('image_name') or 'Nenhuma imagem');filename.setWordWrap(True);self.fields.addRow('Arquivo',filename)
            button=QPushButton('Escolher ou substituir imagem…');button.clicked.connect(lambda:self.image_requested.emit(node.id));self.fields.addRow(button)
            clear=QPushButton('Remover imagem');clear.setEnabled(bool(node.properties.get('source')));clear.clicked.connect(lambda:self.image_cleared.emit(node.id));self.fields.addRow(clear)
            self._text_field('Descrição acessível',node.id,'alt_text',node.properties.get('alt_text',''))
        for key,label in [('visible','Visível'),('enabled','Habilitado')]:self._boolean_field(label,node.id,key,node.properties.get(key,True))
        if node.kind==ComponentKind.CHECKBOX:self._boolean_field('Selecionada inicialmente',node.id,'checked',node.properties.get('checked',False))
        if node.kind==ComponentKind.PROGRESS:self._number_field('Progresso (%)',node.id,'value',node.properties.get('value',0),0,100)
        if node.kind==ComponentKind.PAGES:
            pages=QComboBox()
            for child in node.children:pages.addItem(child.properties.get('title','Página'),child.id)
            pages.setCurrentIndex(pages.findData(node.properties['initial_page']))
            pages.currentIndexChanged.connect(lambda _:self.property_changed.emit(node.id,'initial_page',pages.currentData()));self.fields.addRow('Página inicial',pages)
        if node.can_have_children and node.kind!=ComponentKind.PAGES:
            self.section('Organizar')
            segments=QWidget();row=QHBoxLayout(segments);row.setContentsMargins(0,0,0,0);row.setSpacing(2)
            for mode,label in LAYOUT_LABELS.items():
                button=QPushButton(label);button.setCheckable(True);button.setChecked(node.layout==mode)
                button.setEnabled(not self.state_mode);button.setAccessibleName('Organizar em '+label);button.setProperty('layoutNode',node.id);button.setProperty('layoutMode',mode.value);button.installEventFilter(self)
                button.clicked.connect(lambda _,mode=mode:self.property_changed.emit(node.id,'layout',mode.value));row.addWidget(button)
            self.fields.addRow(segments)
            if node.layout!=LayoutKind.FREE:
                self._number_field('Espaçamento',node.id,'spacing',node.properties.get('spacing',6),0,2000)
                self._number_field('Margens internas',node.id,'padding',node.properties.get('padding',8),0,2000)
                pad=QWidget();grid=QGridLayout(pad);grid.setContentsMargins(0,0,0,0);grid.setSpacing(2)
                symbols=['↖','↑','↗','←','·','→','↙','↓','↘']
                for row,y in enumerate(['top','center','bottom']):
                    for column,x in enumerate(['left','center','right']):
                        value=y+'-'+x;button=QToolButton();button.setText(symbols[row*3+column]);button.setFixedSize(28,28)
                        button.setCheckable(True);button.setChecked(node.properties.get('alignment_preset')==value);button.setEnabled(not self.state_mode)
                        button.setAccessibleName('Alinhamento '+{'top':'superior','center':'central','bottom':'inferior'}[y]+' '+{'left':'à esquerda','center':'ao centro','right':'à direita'}[x])
                        button.setToolTip(button.accessibleName());button.clicked.connect(lambda _,value=value:self.property_changed.emit(node.id,'alignment_preset',value));grid.addWidget(button,row,column)
                self.fields.addRow('Alinhamento',pad)
                self._choice_field('Alinhar',node.id,'align',node.properties.get('align','start'),[('Início','start'),('Centro','center'),('Fim','end'),('Preencher','stretch')])
                self._choice_field('Distribuir',node.id,'distribute',node.properties.get('distribute','start'),[('Início','start'),('Centro','center'),('Fim','end'),('Entre elementos','space-between')])
            if node.layout==LayoutKind.GRID:self._number_field('Colunas',node.id,'columns',node.properties.get('columns',2),1,12)
        self.section('Tamanho e posição')
        if node.kind==ComponentKind.WINDOW:
            self._number_field('Largura inicial',node.id,'width',node.properties.get('width',640),200,4000)
            self._number_field('Altura inicial',node.id,'height',node.properties.get('height',480),160,4000)
            self._boolean_field('Redimensionável',node.id,'resizable',node.properties.get('resizable',True))
        elif parent:
            for axis,label in [('width','Largura'),('height','Altura')]:
                field=QComboBox()
                for text,value in [('Ajustar ao conteúdo','content'),('Preencher','fill'),('Fixo','fixed')]:field.addItem(text,value)
                field.setCurrentIndex(field.findData(node.properties.get('size_mode',{}).get(axis,'content')))
                def change_mode(_,axis=axis,field=field):
                    """Atualiza o dimensionamento do eixo escolhido."""
                    modes=dict(node.properties.get('size_mode',{}));modes[axis]=field.currentData();self.property_changed.emit(node.id,'size_mode',modes)
                field.setEnabled(not self.state_mode);field.currentIndexChanged.connect(change_mode);field.setAccessibleName(label);self.fields.addRow(label,field)
                if node.properties.get('size_mode',{}).get(axis)=='fixed':self._number_field(label+' (px)',node.id,'geometry.'+axis,node.geometry[axis],1,20000)
            if parent.layout==LayoutKind.FREE and parent.kind!=ComponentKind.PAGES:
                for key,label in [('x','X'),('y','Y'),('width','Largura (px)'),('height','Altura (px)')]:self._number_field(label,node.id,'geometry.'+key,node.geometry[key],1 if key in {'width','height'} else 0,20000)
            else:
                hint=QLabel('Posição definida pelo contêiner ('+LAYOUT_LABELS[parent.layout]+').');hint.setWordWrap(True);hint.setProperty('muted',True);self.fields.addRow(hint)
        if node.kind in {ComponentKind.WINDOW,ComponentKind.BUTTON}:
            self.section('Eventos')
            count=sum(1 for flow in project.editable_flows if flow.get('event',{}).get('component')==node.id)
            label='Editar lógica' if count else '+ Ao iniciar' if node.kind==ComponentKind.WINDOW else '+ Ao clicar'
            logic=QPushButton(label+(f' · {count} fluxo(s)' if count else ''));logic.clicked.connect(lambda:self.logic_requested.emit(node.id));self.fields.addRow(logic)
        self.section('Avançado',False)
        self._text_field('Nome no código',node.id,'code_name',node.properties.get('code_name',''))
        self.error_label=QLabel();self.error_label.setWordWrap(True);self.error_label.hide();self.form.addRow(self.error_label)

    def _restore_menu(self,field,node_id,key):
        """Expõe restauração por propriedade somente quando há sobrescrita."""
        if key not in self._overrides:return
        field.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        def menu(point):
            """Oferece restauração explícita da propriedade selecionada."""
            popup=QMenu(field);action=popup.addAction('Restaurar do Padrão');action.triggered.connect(lambda:self.restore_requested.emit(node_id,key));popup.exec(field.mapToGlobal(point))
        field.customContextMenuRequested.connect(menu)

    def _label(self,label,key):
        """Relaciona indicação de alteração ao rótulo, sem depender só da cor."""
        return ('● ' if key in self._overrides else '')+label

    def _text_field(self,label,node_id,key,value):
        """Confirma a digitação ao sair do campo como uma única alteração."""
        field=QLineEdit(value)
        if self.state_mode and key=='code_name':field.setReadOnly(True)
        field.setObjectName('property_'+key);field.setAccessibleName(label)
        field.editingFinished.connect(lambda:self.property_changed.emit(node_id,key,field.text()))
        self._restore_menu(field,node_id,key);self.fields.addRow(self._label(label,key),field)

    def _number_field(self,label,node_id,key,value,minimum,maximum):
        """Restringe valores antes de enviar uma edição ao documento."""
        field=QSpinBox();field.setObjectName('property_'+key);field.setRange(minimum,maximum);field.setValue(value);field.setKeyboardTracking(False);field.setAccessibleName(label)
        if self.state_mode and key not in {'value'}:field.setEnabled(False)
        field.valueChanged.connect(lambda value:self.property_changed.emit(node_id,key,value));self._restore_menu(field,node_id,key);self.fields.addRow(self._label(label,key),field)

    def _boolean_field(self,label,node_id,key,value):
        """Mostra condição inicial ou sobrescrita sem disparar evento de execução."""
        field=QCheckBox(self._label(label,key));field.setChecked(value);field.setAccessibleName(label)
        if self.state_mode and key=='resizable':field.setEnabled(False)
        field.toggled.connect(lambda value:self.property_changed.emit(node_id,key,value));self._restore_menu(field,node_id,key);self.fields.addRow(field)

    def _choice_field(self,label,node_id,key,value,options):
        """Usa valores internos estáveis, independentes dos rótulos traduzidos."""
        field=QComboBox()
        for text,data in options:field.addItem(text,data)
        field.setCurrentIndex(field.findData(value));field.setAccessibleName(label)
        field.setEnabled(not self.state_mode)
        field.currentIndexChanged.connect(lambda _:self.property_changed.emit(node_id,key,field.currentData()));self.fields.addRow(label,field)

    def set_multiple(self,nodes):
        """Limita o formulário a comandos comuns a todos os selecionados."""
        self.clear();self.form.addRow(QLabel(f'{len(nodes)} componentes selecionados'))
        for label,mode in [('Alinhar à esquerda','left'),('Centralizar horizontalmente','center_x'),('Alinhar à direita','right'),('Alinhar no topo','top'),('Centralizar verticalmente','center_y'),('Alinhar na base','bottom'),('Mesma largura','same_width'),('Mesma altura','same_height'),('Distribuir horizontalmente','distribute_x'),('Distribuir verticalmente','distribute_y')]:
            button=QPushButton(label);button.setEnabled(not mode.startswith('distribute') or len(nodes)>=3);button.clicked.connect(lambda _,mode=mode:self.selection_command.emit(mode));self.form.addRow(button)

    def emit_preview(self):
        """Entrega a simulação após 400 ms de hover deliberado."""
        if self._preview:self.layout_preview_requested.emit(*self._preview)

    def eventFilter(self,obj,event):
        """Cancela a simulação ao sair do controle sem tocar no projeto."""
        if not getattr(self,'state_mode',False) and obj.property('layoutNode'):
            if event.type()==QEvent.Type.Enter:self._preview=(obj.property('layoutNode'),obj.property('layoutMode'));self.preview_timer.start()
            elif event.type()==QEvent.Type.Leave:
                self.preview_timer.stop();self._preview=None;self.layout_preview_requested.emit(obj.property('layoutNode'),'')
        return super().eventFilter(obj,event)
