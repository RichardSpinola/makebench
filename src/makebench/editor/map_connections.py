"""Editor único de transições reais, compartilhado por arraste, teclado e inspeção."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QFormLayout,QComboBox,QLabel,QCheckBox,QDialogButtonBox
from makebench.core.project import ComponentKind
from makebench.core.navigation import find_navigation_block
from .controls import reconcile_combo


class ConnectionDialog(QDialog):
    """Origem, evento, destino e comportamento têm nomes humanos e IDs estáveis."""
    def __init__(self,panel,source=None,target=None,edge=None):
        """Todos os destinos são representáveis pelo runtime, sem ligações ilustrativas."""
        super().__init__(panel);self.panel=panel;self.project=panel.window.project;self.edge=edge;self.setWindowTitle('Editar transição' if edge else 'Conectar interfaces');self.resize(570,270);self.setMinimumWidth(500)
        form=QFormLayout(self);form.setContentsMargins(12,12,12,12);form.setSpacing(8)
        self.source=QComboBox();self.source.setObjectName('transition_source');self.event=QComboBox();self.event.setObjectName('transition_event');self.target=QComboBox();self.target.setObjectName('transition_target')
        self.closing=QCheckBox('Fechar a janela de origem ao abrir o destino')
        self.notice=QLabel();self.notice.setWordWrap(True)
        entries=[]
        for root in self.project.roots:
            for state in [{'id':'@default','name':'Padrão'},*self.project.states.get(root.id,[])]:entries.append((root.properties.get('title','Interface')+' › '+state['name'],root.id+'|'+state['id']))
        for label,key in entries:self.source.addItem(label,key)
        self.source.setCurrentIndex(max(0,self.source.findData(source or self.project.root.id+'|@default')))
        form.addRow('Interface de origem',self.source);form.addRow('Quando acontecer',self.event);form.addRow('Destino',self.target);form.addRow('Comportamento',self.closing);form.addRow(self.notice)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);self.buttons.button(QDialogButtonBox.StandardButton.Save).setText('Aplicar' if edge else 'Conectar');self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);form.addRow(self.buttons)
        self.source.currentIndexChanged.connect(self.sync);self.target.currentIndexChanged.connect(self.describe);self.event.currentIndexChanged.connect(self.describe);self.sync()
        if target:self.target.setCurrentIndex(max(0,self.target.findData(target)))
        if edge:
            flow,block=find_navigation_block(self.project,edge['flow'],edge['block'])
            if flow:self.event.setCurrentIndex(max(0,self.event.findData(flow['event']['component'])))
            if block:self.closing.setChecked(block.get('parameters',block).get('close_current',False))
        self.describe()

    def sync(self):
        """Estados de outra janela não são oferecidos como se fossem páginas navegáveis."""
        owner=self.source.currentData().split('|')[0];root=self.project.find(owner);selected=self.panel.window.selected_id
        if self.project.find(selected).kind!=ComponentKind.BUTTON:selected=None
        events=[('Clique em '+(n.properties.get('text') or n.display_name),n.id) for n in root.walk() if n.kind==ComponentKind.BUTTON]
        events.append(('A janela '+root.properties.get('title','Interface')+' abrir',root.id))
        current=self.event.currentData();reconcile_combo(self.event,events,current if current in [value for _,value in events] else selected if selected in [value for _,value in events] else events[0][1])
        targets=[]
        for destination in self.project.roots:
            states=[{'id':'@default','name':'Padrão'},*self.project.states.get(destination.id,[])]
            for state in states:
                if destination.id==owner or state['id']==destination.properties.get('initial_state','@default'):targets.append((destination.properties.get('title','Interface')+' › '+state['name'],destination.id+'|'+state['id']))
        current=self.target.currentData();reconcile_combo(self.target,targets,current if current in [value for _,value in targets] else targets[0][1]);self.describe()

    def describe(self):
        """O texto descreve a operação que realmente será adicionada ao evento."""
        same=bool(self.target.currentData()) and self.source.currentData().split('|')[0]==self.target.currentData().split('|')[0]
        self.closing.setEnabled(not same);self.notice.setText('Mudar o estado da mesma janela, preservando sua estrutura.' if same else 'Abrir outra janela real do sistema em seu estado inicial.')

        flow=next(iter(sorted((f for f in self.project.editable_flows if f['event']['component']==self.event.currentData() and (not f.get('states') or self.source.currentData().split('|')[1] in f['states'])),key=lambda f:not bool(f.get('states')))),None)
        if flow and not flow.get('states'):self.notice.setText(self.notice.text()+' O evento existente é executado em qualquer estado.')
        elif flow and len(flow.get('states',[]))>1:self.notice.setText(self.notice.text()+' A ação compartilha o filtro de estados do evento existente.')
