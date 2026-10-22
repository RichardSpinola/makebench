"""Aplicativo GTK real, worker Python e tarefas supervisionadas sem dependência Qt."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
from makebench.core.codegen import generate
from makebench.core.project import ComponentKind,ProjectError
from .renderer import GtkView


def terminate_group(process,force=False):
    """Sinaliza só grupos criados pelo runtime; nunca um processo administrativo."""
    if process:
        try:os.killpg(process.pid,signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:pass


class GtkRuntime:
    """Compartilha o protocolo ctx do runtime Qt e mantém o ciclo GTK responsivo."""
    def __init__(self,project,source,read_asset,root,source_filename,observer=None):
        """Prepara o snapshot; construir a instância não executa código próprio."""
        import gi
        gi.require_version('Gtk','4.0')
        from gi.repository import Gtk,GLib,Gio
        if not Gtk.init_check():raise ProjectError('Não foi possível abrir GTK4: nenhum display gráfico está disponível.')
        self.Gtk,self.GLib=Gtk,GLib;self.Adw=None
        try:
            gi.require_version('Adw','1');from gi.repository import Adw
            self.Adw=Adw
        except (ValueError,ImportError):pass
        self.project=project;self.source=source;self.read_asset=read_asset;self.root=Path(root).resolve();self.source_filename=source_filename
        diagnostics=generate(project,source).diagnostics
        if diagnostics:raise ProjectError('\n'.join(diagnostics))
        self.observer=observer or (lambda value:None);self.windows={};self.views={};self.open_windows=set();self.states={};self.pending=[];self.current=project.entry_window or project.root.id
        self.process=None;self.task=None;self.admin=False;self.active=False;self.busy=True;self.stopping=False;self.lock=threading.Lock();self.dialogs=set()
        self.event_buttons={f['event']['component'] for f in project.editable_flows if f['event']['kind']=='click'}
        cls=self.Adw.Application if self.Adw else Gtk.Application
        self.app=cls(application_id=project.application.get('id') or 'org.makebench.Generated',flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.app.connect('activate',self.activate)

    def emit(self,kind,**values):
        """Encaminha observação à bancada ou ao console do aplicativo independente."""
        self.observer({'type':kind,**values})

    def run(self):
        """Entrada explícita da execução GTK; iniciar é a única ação que roda código."""
        return self.app.run([])

    def activate(self,_app):
        """Abre a janela inicial e inicia o mesmo worker neutro usado por Qt."""
        if self.process:
            for identifier in self.open_windows:self.windows[identifier].present()
            return
        self.app.hold();self.open_window(self.current,queue_start=False)
        environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
        package_root=str(Path(__file__).resolve().parents[2]);environment['PYTHONPATH']=package_root+os.pathsep+environment.get('PYTHONPATH','')
        self.process=subprocess.Popen([sys.executable,'-u','-m','makebench.runtime.worker'],cwd=self.root,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,bufsize=0)
        self.send({'project':self.project.to_dict(),'source':self.source,'root':str(self.root),'source_filename':str(self.source_filename or '<makebench-actions>')})
        threading.Thread(target=self.read_worker,daemon=True).start()
        threading.Thread(target=self.read_channel,args=(self.process.stderr,'stderr'),daemon=True).start()
        self.emit('status',text='Iniciando GTK…')

    def send(self,value):
        """Serializa respostas ao worker; falhas de pipe são tratadas no encerramento."""
        if self.process and self.process.poll() is None:
            try:
                with self.lock:self.process.stdin.write((json.dumps(value,ensure_ascii=True)+'\n').encode());self.process.stdin.flush()
            except (BrokenPipeError,OSError):pass

    def reply(self,identifier,value=None,ok=True,cancelled=False,error=''):
        """Mantém o contrato de resposta idêntico nos dois toolkits."""
        self.send({'type':'response','id':identifier,'value':value,'ok':ok,'cancelled':cancelled,'error':error})

    def read_worker(self):
        """Lê em thread e entrega ao GTK somente por idle_add, sem bloquear desenho."""
        try:
            while True:
                line=self.process.stdout.readline(2_000_001)
                if not line:break
                if len(line)>2_000_000:raise ValueError('Resposta do worker excedeu o limite.')
                self.GLib.idle_add(self.message,json.loads(line))
        except (ValueError,OSError) as exc:self.GLib.idle_add(lambda message=str(exc):self.emit('error',message=message))
        finally:self.GLib.idle_add(self.worker_finished)

    def read_channel(self,pipe,channel):
        """Mantém UTF-8 incremental e saída ao vivo inclusive sem quebras de linha."""
        import codecs
        decoder=codecs.getincrementaldecoder('utf-8')('replace')
        while True:
            data=pipe.read(8192)
            if not data:break
            text=decoder.decode(data)
            if text:self.GLib.idle_add(self.output,channel,text)
        tail=decoder.decode(b'',final=True)
        if tail:self.GLib.idle_add(self.output,channel,tail)

    def output(self,channel,text):
        """Registra canais sem interpretar stderr como falha."""
        self.emit('log',channel=channel,text=text)

    def message(self,message):
        """Atende eventos neutros do worker exclusivamente na thread GTK."""
        if self.stopping:return
        kind=message.get('type')
        if kind=='ready':self.active=True;self.set_busy(False);self.queue_event(self.current,'start');self.emit('ready')
        elif kind=='busy':self.set_busy(True)
        elif kind=='done':self.set_busy(False);self.emit('done',**{k:v for k,v in message.items() if k!='type'});self.dispatch()
        elif kind=='log':self.output(message['channel'],message['text'])
        elif kind=='error':self.emit('error',**{k:v for k,v in message.items() if k!='type'})
        elif kind=='request':self.request(message)

    def set_busy(self,busy):
        """Atualiza sensibilidade de eventos e observação de estado na bancada."""
        self.busy=busy
        for view in self.views.values():view.busy(busy,self.event_buttons)
        self.emit('busy',value=busy);self.emit('status',text='Executando fluxo' if busy else 'Aplicativo GTK em execução')

    def queue_event(self,identifier,kind='click'):
        """Seleciona fluxos específicos do estado antes dos fluxos genéricos."""
        if kind=='click' and self.busy:return
        owner=self.project.window_of(identifier)
        if owner is None:return
        matches=[f for f in self.project.editable_flows if f['event']=={'component':identifier,'kind':kind}]
        specific=[f for f in matches if self.states[owner.id] in f.get('states',[])]
        self.pending.extend(f['id'] for f in (specific or [f for f in matches if not f.get('states')]))
        self.dispatch()

    def dispatch(self):
        """Executa um único handler por vez; variáveis de janela seguem o evento."""
        if self.pending and self.active and not self.busy and not self.stopping:
            identifier=self.pending.pop(0);flow=next(f for f in self.project.editable_flows if f['id']==identifier)
            self.current=self.project.window_of(flow['event']['component']).id;self.set_busy(True)
            self.send({'type':'event','flow':identifier,'window':self.current})

    def open_window(self,identifier,close_current=False,queue_start=True):
        """Abre janela GTK real; reabertura reinicializa controles, estado e escopo."""
        root=next((r for r in self.project.roots if r.id==identifier),None)
        if root is None:raise ValueError('A janela não existe.')
        reset=identifier not in self.open_windows
        if reset:
            if identifier in self.windows:self.windows[identifier].destroy()
            view=GtkView(root,self.read_asset,self.queue_event);self.views[identifier]=view
            if self.Adw:
                window=self.Adw.ApplicationWindow(application=self.app);box=self.Gtk.Box(orientation=self.Gtk.Orientation.VERTICAL);box.append(self.Adw.HeaderBar());box.append(view.widget);view.widget.set_vexpand(True);window.set_content(box)
            else:
                window=self.Gtk.ApplicationWindow(application=self.app);window.set_child(view.widget)
            icon=root.properties.get('icon') or self.project.application.get('icon')
            if icon:
                self.Gtk.IconTheme.get_for_display(window.get_display()).add_search_path(str(self.root/Path(icon).parent));window.set_icon_name(Path(icon).stem)
            window.set_title(root.properties.get('title',self.project.name));window.set_default_size(root.properties.get('width',640),root.properties.get('height',480));window.set_resizable(root.properties.get('resizable',True))
            window.connect('close-request',lambda _window:self.window_close(identifier));self.windows[identifier]=window
            self.states[identifier]=root.properties.get('initial_state','@default');self.apply_state(identifier,self.states[identifier]);view.busy(self.busy,self.event_buttons)
        self.open_windows.add(identifier);self.windows[identifier].present()
        if close_current and self.current!=identifier:self.close_window(self.current,check_last=False)
        if reset and queue_start:self.queue_event(identifier,'start')
        self.emit('navigation',windows=sorted(self.open_windows),states=dict(self.states));return reset

    def apply_state(self,identifier,state):
        """Aplica apenas diferenças de conteúdo, preservando IDs e a estrutura base."""
        root=self.project.effective_root(identifier,state);view=self.views[identifier];self.states[identifier]=state
        for node in root.walk():
            p=node.properties;widget=view.widgets[node.id]
            if node.kind in {ComponentKind.LABEL,ComponentKind.BUTTON,ComponentKind.TEXT_INPUT,ComponentKind.CHECKBOX,ComponentKind.OUTPUT}:view.set_text(node.id,p.get('text',''))
            if node.kind==ComponentKind.CHECKBOX:widget.set_active(p.get('checked',False))
            if node.kind==ComponentKind.PROGRESS:widget.set_fraction(p.get('value',0)/100)
            if node.kind==ComponentKind.IMAGE:
                paintable=view.Gdk.Texture.new_from_bytes(view.GLib.Bytes.new(self.read_asset(p['source']))) if p.get('source') else None;widget.set_paintable(paintable)
            view.frames[node.id].set_visible(p.get('visible',True));view.enabled[node.id]=p.get('enabled',True);widget.set_sensitive(view.enabled[node.id])
            if node.kind==ComponentKind.PAGES:view.show_page(self.project,p['initial_page'])
        if identifier in self.windows:self.windows[identifier].set_title(root.properties.get('title',self.project.name))
        self.emit('navigation',windows=sorted(self.open_windows),states=dict(self.states))

    def window_close(self,identifier):
        """Não permite fechar ou interromper uma ação administrativa em andamento."""
        if self.admin:self.emit('status',text='Aguarde a tarefa administrativa terminar.');return True
        self.close_window(identifier);return True

    def close_window(self,identifier,check_last=True):
        """Fecha uma interface e encerra o aplicativo quando não resta outra."""
        if self.admin:raise ValueError('Aguarde a tarefa administrativa terminar.')
        self.open_windows.discard(identifier)
        if identifier in self.windows:self.windows[identifier].set_visible(False)
        if check_last and not self.open_windows:self.GLib.idle_add(self.stop)
        self.emit('navigation',windows=sorted(self.open_windows),states=dict(self.states))

    def locate(self,identifier):
        """Resolve ID estável ou nome legível em qualquer janela aberta."""
        node=self.project.find(identifier) or next((n for n in self.project.walk() if n.properties.get('code_name')==identifier),None)
        if node is None:raise ValueError('O componente não existe.')
        owner=self.project.window_of(node.id);view=self.views.get(owner.id)
        if view is None:raise ValueError('A janela do componente não está aberta.')
        return view,node.id

    def request(self,r):
        """Traduz a mesma API ctx para GTK, tarefas e diálogos declarados."""
        identifier=r['id'];method=r['method']
        try:
            if method=='run':self.run_task(r);return
            if method in {'ask','confirm','message'}:self.dialog(r);return
            result=None
            if method=='go_state':self.apply_state(self.current,r['state'])
            elif method=='open_window':result={'reset':self.open_window(r['window'],r.get('close_current',False))}
            elif method=='close_window':self.close_window(self.current)
            else:
                view,key=self.locate(r.get('component'));widget=view.widgets[key]
                if method=='read':result=view.read(key,r['attribute'])
                elif method=='set_text':view.set_text(key,r['value'])
                elif method=='set_enabled':view.enabled[key]=r['value'];widget.set_sensitive(r['value'])
                elif method=='set_value':
                    if not 0<=r['value']<=100:raise ValueError('Progresso deve estar entre 0 e 100.')
                    widget.set_fraction(r['value']/100)
                elif method=='show_page':view.show_page(self.project,key)
                else:raise ValueError('Operação desconhecida.')
            self.reply(identifier,result)
        except (ValueError,TypeError,AttributeError,KeyError,OSError) as exc:self.reply(identifier,ok=False,error=str(exc))

    def dialog(self,r):
        """Diálogos GTK explícitos, sem senha própria e sem ler prompts do terminal."""
        Gtk=self.Gtk;parent=self.windows[self.current];method=r['method'];kind=r.get('kind');prompt=str(r.get('prompt',''))
        if method=='ask' and kind in {'file','directory'}:
            dialog=Gtk.FileChooserNative(title=prompt,transient_for=parent,action=Gtk.FileChooserAction.SELECT_FOLDER if kind=='directory' else Gtk.FileChooserAction.OPEN,accept_label='Selecionar',cancel_label='Cancelar')
            def selected(_dialog,response):
                """Retorna apenas arquivo/pasta local escolhido ou cancelamento."""
                file=dialog.get_file();accepted=response==Gtk.ResponseType.ACCEPT and file is not None and file.get_path() is not None
                self.reply(r['id'],file.get_path() if accepted else None,ok=accepted,cancelled=not accepted);self.dialogs.discard(dialog);dialog.destroy()
            dialog.connect('response',selected);self.dialogs.add(dialog);dialog.show();return
        dialog=Gtk.Dialog(title=self.project.name,transient_for=parent,modal=True);dialog.set_default_size(420,180)
        box=dialog.get_content_area();box.set_spacing(12)
        for side in ('top','bottom','start','end'):getattr(box,'set_margin_'+side)(18)
        box.append(Gtk.Label(label=prompt,wrap=True,xalign=0));field=None
        if method=='ask':
            if kind=='text':field=Gtk.Entry();box.append(field)
            elif kind=='choice':
                if not r.get('options') or any(not isinstance(v,str) for v in r['options']):raise ValueError('Informe opções de texto.')
                field=Gtk.DropDown.new_from_strings(r['options']);box.append(field)
            else:raise ValueError('Tipo de pergunta desconhecido.')
        if method!='message':dialog.add_button('Não' if method=='confirm' else 'Cancelar',Gtk.ResponseType.CANCEL)
        dialog.add_button('Sim' if method=='confirm' else 'Continuar' if method=='ask' else 'OK',Gtk.ResponseType.OK)
        def finished(_dialog,response):
            """Desbloqueia o worker somente após resposta explícita do usuário."""
            accepted=response==Gtk.ResponseType.OK;value=None
            if accepted and method=='ask':value=field.get_text() if kind=='text' else r['options'][field.get_selected()]
            elif method=='confirm':value=accepted
            self.reply(r['id'],value,ok=accepted,cancelled=not accepted);self.dialogs.discard(dialog);dialog.destroy()
        dialog.connect('response',finished);self.dialogs.add(dialog);dialog.present();self.emit('status',text='Aguardando resposta')

    def run_task(self,r):
        """Executa argv sem shell implícito, com Polkit opcional e saída incremental."""
        if self.task:raise ValueError('Já existe uma tarefa em execução.')
        program=r['program'];args=r['arguments'];admin=r.get('admin',False)
        if not isinstance(program,str) or not program.strip() or '\0' in program or not isinstance(args,list) or len(args)>256 or any(not isinstance(v,str) or '\0' in v for v in args):raise ValueError('Programa/argumentos inválidos.')
        executable=str((self.root/program).resolve()) if '/' in program else shutil.which(program)
        if not executable:raise ValueError('Programa não encontrado: '+program)
        if admin:
            pkexec=shutil.which('pkexec')
            if not pkexec:raise ValueError('pkexec não está disponível no sistema de destino.')
            args=['--disable-internal-agent',executable,*args];executable=pkexec
        task=subprocess.Popen([executable,*args],cwd=self.root,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,bufsize=0)
        self.task=task;self.admin=admin;started=time.monotonic();self.emit('admin',value=admin)
        self.emit('task',id=r['id'],program=program,admin=admin,state='Executando',duration=0)
        def wait():
            """Espera a tarefa em thread e mantém os dois canais fluindo até EOF."""
            readers=[threading.Thread(target=self.read_channel,args=(pipe,ch),daemon=True) for pipe,ch in ((task.stdout,'stdout'),(task.stderr,'stderr'))]
            for reader in readers:reader.start()
            code=task.wait()
            for reader in readers:reader.join()
            self.GLib.idle_add(self.task_done,r,code,started)
        threading.Thread(target=wait,daemon=True).start()

    def task_done(self,r,code,started):
        """Código determina sucesso; 126/127 administrativos não prometem conclusão."""
        self.task=None;self.admin=False;self.emit('admin',value=False)
        self.emit('task',id=r['id'],program=r['program'],admin=r.get('admin',False),state='Concluído' if code==0 else 'Não concluído',duration=time.monotonic()-started)
        if not self.stopping:
            if r.get('admin') and code in (126,127):self.reply(r['id'],ok=False,cancelled=code==126,error=f'Tarefa administrativa não concluída (código {code}).')
            else:self.reply(r['id'],{'code':code,'crashed':code<0})
        if self.process and self.process.poll() is not None:self.stop()

    def worker_finished(self):
        """Não abandona tarefa administrativa se o worker terminar inesperadamente."""
        if not self.stopping:self.emit('error',message='O processo Python foi encerrado.')
        if not self.admin:self.stop()

    def stop(self):
        """Cancela grupos comuns e aguarda limpeza; tarefa administrativa bloqueia."""
        if self.admin:self.emit('status',text='Aguarde a tarefa administrativa terminar.');return False
        if self.stopping:return False
        self.stopping=True;self.active=False
        for dialog in list(self.dialogs):dialog.destroy()
        self.dialogs.clear();terminate_group(self.process);terminate_group(self.task)
        self.GLib.timeout_add(700,self.finish_stop);return False

    def finish_stop(self):
        """Força somente grupos de usuário comum e encerra após recolher os filhos."""
        terminate_group(self.process,True);terminate_group(self.task,True)
        if self.process:
            try:self.process.wait(timeout=.1)
            except subprocess.TimeoutExpired:return True
        if self.task and self.task.poll() is None:return True
        for window in self.windows.values():window.destroy()
        self.emit('stopped');self.app.release();self.app.quit();return False
