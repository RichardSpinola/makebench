"""Coordenação de janelas reais e estados sobre uma única sessão de execução."""
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QMainWindow,QScrollArea
from makebench.core.project import ComponentKind,ProjectError
from .view import RuntimeView


class AppWindow(QMainWindow):
    """Janela adicional do aplicativo; o supervisor permanece no controlador."""
    def __init__(self,owner,root,view):
        """Mantém referência ao controlador até o fechamento da última janela."""
        super().__init__()
        self.owner=owner;self.identifier=root.id
        self.setWindowIcon(owner.windowIcon())
        if root.properties.get('icon'):
            from PySide6.QtGui import QIcon,QPixmap
            pixmap=QPixmap();pixmap.loadFromData(owner.read_asset(root.properties['icon']));self.setWindowIcon(QIcon(pixmap))
        self.setWindowTitle(root.properties.get('title',owner.project.name))
        self.resize(root.properties.get('width',640),root.properties.get('height',480))
        if not root.properties.get('resizable',True):self.setFixedSize(self.size())
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(view);self.setCentralWidget(scroll)

    def closeEvent(self,event):
        """Remove a janela sem abandonar tarefas administrativas ou processos comuns."""
        if self.owner.session.closed:event.accept();return
        if self.owner.session.admin_active:
            self.owner.state.setText('Aguarde a tarefa administrativa terminar.');event.ignore();return
        self.owner.open_windows.discard(self.identifier)
        self.hide();event.ignore()
        self.owner.stop_if_last()


class RuntimeNavigation:
    """Aplica navegação declarada; todas as operações recebem IDs já validados."""

    def install_navigation(self,read_asset):
        """Registra a janela inicial e prepara escopos sem iniciar o worker."""
        self.read_asset=read_asset
        self.views={self.root_window_id:self.view};self.app_windows={self.root_window_id:self}
        self.open_windows={self.root_window_id};self.active_states={}
        self.current_window=self.root_window_id;self._queued_flows=[]
        self.view.window_id=self.root_window_id
        for root in self.project.roots:
            self.active_states[root.id]=root.properties.get('initial_state','@default')
        self.apply_state(self.root_window_id,self.active_states[self.root_window_id])

    def apply_state(self,window_id,state):
        """Restaura propriedades padrão e aplica diferenças sem duplicar componentes."""
        effective=self.project.effective_root(window_id,state)
        self.active_states[window_id]=state
        view=self.views.get(window_id)
        if view:
            for node in effective.walk():
                widget=view.widgets[node.id];p=node.properties
                if node.kind in {ComponentKind.LABEL,ComponentKind.BUTTON,ComponentKind.TEXT_INPUT,ComponentKind.CHECKBOX,ComponentKind.OUTPUT}:
                    if hasattr(widget,'setPlainText'):widget.setPlainText(p.get('text',''))
                    else:widget.setText(p.get('text',''))
                if node.kind==ComponentKind.CHECKBOX:widget.setChecked(p.get('checked',False))
                if node.kind==ComponentKind.PROGRESS:widget.setValue(p.get('value',0))
                if node.kind==ComponentKind.IMAGE:
                    from PySide6.QtGui import QPixmap
                    pixmap=QPixmap()
                    if p.get('source'):pixmap.loadFromData(self.read_asset(p['source']))
                    widget.image=pixmap;widget.setAccessibleName(p.get('alt_text','Imagem'));widget.update()
                view.set_enabled(node.id,p.get('enabled',True))
                view.frames[node.id].setVisible(p.get('visible',True))
                if node.kind==ComponentKind.PAGES:view.show_page(p['initial_page'])
            window=self.app_windows.get(window_id)
            if window:window.setWindowTitle(('[Teste] ' if self.supervision else '')+effective.properties.get('title',self.project.name))

    def open_app_window(self,identifier,close_current=False):
        """Cria ou reapresenta uma janela real; não duplica uma instância aberta."""
        root=next((r for r in self.project.roots if r.id==identifier),None)
        if root is None:raise ValueError('A janela não existe.')
        was_open=identifier in self.open_windows
        if identifier not in self.views:
            view=RuntimeView(self.project,self.read_asset,window_root=root)
            view.window_id=identifier;view.clicked.connect(self._clicked)
            window=AppWindow(self,root,view)
            self.views[identifier]=view;self.app_windows[identifier]=window
        elif not was_open:self.views[identifier].reset()
        if not was_open:
            self.active_states[identifier]=root.properties.get('initial_state','@default')
            self.apply_state(identifier,self.active_states[identifier])
        self.views[identifier].set_busy(self.session.busy)
        self.open_windows.add(identifier);window=self.app_windows[identifier];window.show();window.raise_()
        if close_current and self.current_window!=identifier:self.close_app_window(self.current_window,check_last=False)
        if not was_open:self.queue_event(identifier,'start')
        return not was_open

    def close_app_window(self,identifier,check_last=True):
        """Fecha uma interface mantendo o controlador vivo até limpar a sessão."""
        if self.session.admin_active:raise ValueError('Aguarde a tarefa administrativa terminar.')
        self.open_windows.discard(identifier)
        if identifier in self.app_windows:self.app_windows[identifier].hide()
        if check_last:self.stop_if_last()

    def stop_if_last(self):
        """Encerra após responder ao worker, quando não há janelas do app abertas."""
        if not self.open_windows:
            self.close_pending=True;QTimer.singleShot(0,self.stop)

    def widget_for(self,identifier):
        """Localiza controles em qualquer janela já criada."""
        if identifier not in {n.id for n in self.project.walk()}:
            node=next((n for n in self.project.walk() if n.properties.get('code_name')==identifier),None)
            if node:identifier=node.id
        for view in self.views.values():
            if identifier in view.widgets:return view,view.widgets[identifier]
        return None,None

    def queue_event(self,component,kind):
        """Escolhe filtro específico antes do genérico; preserva ordem do documento."""
        owner=self.project.window_of(component)
        if owner is None:return
        state=self.active_states[owner.id]
        matches=[f for f in self.project.workflows if f['event']=={'kind':kind,'component':component}]
        specific=[f for f in matches if state in f.get('states',[])]
        flows=specific or [f for f in matches if not f.get('states')]
        self._queued_flows.extend(f['id'] for f in flows)
        self.dispatch_next()

    def dispatch_next(self):
        """Dispara um fluxo pendente apenas depois da resposta do anterior."""
        if self._queued_flows and self.session.active and not self.session.busy:
            flow_id=self._queued_flows.pop(0)
            flow=next(f for f in self.project.workflows if f['id']==flow_id)
            self.current_window=self.project.window_of(flow['event']['component']).id
            self.session.dispatch(flow_id)
