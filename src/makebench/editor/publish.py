"""Distribuição com preparação explícita das ferramentas e artefatos verificáveis."""
from pathlib import Path
import threading
from PySide6.QtCore import QThread,QUrl,Signal,Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication,QDialog,QDialogButtonBox,QLayout,QCheckBox,QComboBox,QFileDialog,QFormLayout,QHBoxLayout,QLabel,QListWidget,
    QListWidgetItem,QPlainTextEdit,QFrame,QProgressBar,QPushButton,QVBoxLayout,QWidget)
from makebench.core.packages import FORMATS,preflight,build_package
from makebench.core.environment import build_tools
from makebench.core.build_environment import prepared,prepare_tools,prepare_flatpak


class BuildJob(QThread):
    """Constrói o snapshot em staging fora da UI, sem executar o projeto."""
    progress=Signal(int,str);completed=Signal(dict);failed=Signal(str)
    def __init__(self,project,source,read_asset,destination,parent,format='source',recipe_only=False,environment='auto'):
        """Recebe dados imutáveis da construção e cancelamento cooperativo."""
        super().__init__(parent);self.project=project;self.source=source;self.read_asset=read_asset;self.destination=destination;self.format=format;self.recipe_only=recipe_only;self.environment=environment;self.cancel=threading.Event()

    def run(self):
        """Publica apenas resultado completo; falhas mantêm o destino intacto."""
        try:self.completed.emit(build_package(self.project,self.source,self.read_asset,self.destination,self.format,self.progress.emit,self.cancel.is_set,self.recipe_only,self.environment))
        except Exception as exc:self.failed.emit(str(exc))


class PrepareJob(QThread):
    """Baixa ferramentas confiáveis sem instalar RPMs no sistema do usuário."""
    progress=Signal(int,str);completed=Signal(dict);failed=Signal(str)
    def __init__(self,project,format,parent):
        """Flatpak prepara SDK no usuário; os demais formatos usam Podman rootless."""
        super().__init__(parent);self.project=project;self.format=format;self.cancel=threading.Event()

    def run(self):
        """A preparação é uma ação explícita com saída e cancelamento visíveis."""
        try:self.completed.emit(prepare_flatpak(self.project,self.progress.emit,self.cancel.is_set) if self.format=='flatpak' else prepare_tools(self.progress.emit,self.cancel.is_set))
        except Exception as exc:self.failed.emit(str(exc))


class PublishPanel(QWidget):
    """Separa configuração do app, ferramentas e resultado real de distribuição."""
    def __init__(self,window):
        """Controles nativos compactos e detalhes expansíveis para logs e diagnóstico."""
        super().__init__();self.window=window;self.job=None;layout=QVBoxLayout(self);layout.setContentsMargins(12,10,12,10);layout.setSpacing(8)
        self.stages=QLabel('1 Formato  →  2 Verificação  →  3 Construção  →  4 Resultado');layout.addWidget(self.stages)
        header=QHBoxLayout();self.summary=QLabel();header.addWidget(self.summary,1)
        edit=QPushButton('Aplicativo…');edit.clicked.connect(window.application_settings);header.addWidget(edit);layout.addLayout(header)
        form=QFormLayout();self.destination_form=form;self.format=QComboBox()
        for key,(name,_,_) in FORMATS.items():self.format.addItem(name,key)
        self.format.setMaximumWidth(360);form.addRow('Formato',self.format)
        self.environment=QComboBox()
        for label,key in [('Automático','auto'),('Ferramentas preparadas pelo Makebench','managed'),('Ferramentas do sistema','system')]:self.environment.addItem(label,key)
        self.environment.setMaximumWidth(360);form.addRow('Construir com',self.environment);layout.addLayout(form)
        tools=QHBoxLayout();self.tool_status=QLabel();tools.addWidget(self.tool_status,1);self.prepare=QPushButton('Preparar ferramentas…');self.prepare.clicked.connect(self.prepare_environment);tools.addWidget(self.prepare);layout.addLayout(tools)
        self.description=QLabel();self.description.setWordWrap(True);self.description.setMaximumWidth(880);layout.addWidget(self.description)
        self.recipe_only=QCheckBox('Exportar somente a receita');self.recipe_only.setToolTip('Gera um ZIP com os arquivos de construção. Não produz um pacote instalável.');layout.addWidget(self.recipe_only)
        self.check_hint=QLabel('Verifique o projeto antes de construir.');layout.addWidget(self.check_hint)
        self.checks=QListWidget();self.checks.setFrameShape(QFrame.Shape.NoFrame);self.checks.setMinimumHeight(60);self.checks.setMaximumHeight(160);self.checks.hide();self.checks.itemActivated.connect(self.fix_issue);layout.addWidget(self.checks)
        row=QHBoxLayout();self.check_button=QPushButton('Verificar');self.check_button.clicked.connect(self.check);row.addWidget(self.check_button)
        self.build=QPushButton('Construir…');self.build.clicked.connect(self.build_source);row.addWidget(self.build)
        self.cancel_button=QPushButton('Cancelar');self.cancel_button.setEnabled(False);self.cancel_button.clicked.connect(self.cancel_build);self.cancel_button.hide();row.addWidget(self.cancel_button);row.addStretch();layout.addLayout(row)
        self.progress_bar=QProgressBar();self.progress_bar.setValue(0);layout.addWidget(self.progress_bar);self.progress_bar.hide()
        self.log_toggle=QCheckBox('Mostrar detalhes');layout.addWidget(self.log_toggle)
        self.build_log=QPlainTextEdit();self.build_log.setReadOnly(True);self.build_log.setMaximumBlockCount(2000);self.build_log.setMinimumHeight(110);layout.addWidget(self.build_log,1);self.build_log.hide();self.log_toggle.toggled.connect(self.build_log.setVisible)
        self.result=QLabel();self.result.setWordWrap(True);self.result.setTextFormat(Qt.TextFormat.PlainText);self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(self.result)
        result_row=QHBoxLayout();self.open_folder=QPushButton('Abrir pasta');self.open_folder.hide();self.open_folder.clicked.connect(self.show_result_folder);result_row.addWidget(self.open_folder)
        self.copy_path=QPushButton('Copiar caminho');self.copy_path.hide();self.copy_path.clicked.connect(lambda:QApplication.clipboard().setText(str(self.output_path)));result_row.addWidget(self.copy_path);result_row.addStretch();layout.addLayout(result_row);layout.addStretch()
        self.format.currentIndexChanged.connect(self.sync);self.environment.currentIndexChanged.connect(self.sync);self.recipe_only.toggled.connect(self.sync);self.sync()

    def change(self,key,value):
        """Metadados continuam sendo um comando reversível da central do aplicativo."""
        self.window.change_application(key,value)

    def sync(self):
        """A falta de ferramentas nunca troca silenciosamente um pacote por uma receita."""
        app=self.window.project.application;self.summary.setText((app.get('name') or self.window.project.name)+' · '+(app.get('version') or 'Sem versão')+' · '+app.get('backend','qt').upper())
        key=self.format.currentData();signature=(self.window.project.id,self.window.history._index,self.window.source.text,key,self.recipe_only.isChecked(),self.environment.currentData())
        if signature!=getattr(self,'_check_signature',None):
            self._check_signature=signature;self.checks.clear();self.checks.hide();self.check_hint.show();self.stages.setText('1 Formato  →  2 Verificação  →  3 Construção  →  4 Resultado');self.result.clear();self.open_folder.hide();self.copy_path.hide()
        name,tool,_=FORMATS[key];available=build_tools().get(tool) if tool else True;managed=prepared();busy=bool(self.job and self.job.isRunning())
        self.destination_form.setRowVisible(self.environment,key not in {'source','flatpak'});self.prepare.setVisible(key!='source');self.recipe_only.setVisible(key!='source')
        self.environment.setEnabled(key not in {'source','flatpak'} and not busy);self.recipe_only.setEnabled(key!='source' and not busy);self.prepare.setEnabled(key!='source' and not busy)
        if key=='source':status='Não precisa de ferramentas de construção.';text='Código Python, recursos e runtime. As dependências constam no arquivo requirements.txt.'
        elif key=='flatpak':status='SDK do '+('GNOME' if app.get('backend')=='gtk' else 'KDE')+' · preparação por usuário';text='Preparar instala o SDK pelo Flathub. A construção usa o SDK local e gera um bundle .flatpak. Ações do host e administração são bloqueadas.'
        else:
            status='Ferramentas Makebench prontas.' if managed else 'Ferramenta do sistema disponível.' if available else 'Prepare as ferramentas para construir.'
            text='Preparar baixa as ferramentas em um ambiente Podman separado e reutilizável. A construção acontece sem rede.'
        if key=='appimage':text+=' Este AppImage ainda requer Python 3.13+ e GTK/PyGObject ou PySide6 no destino.'
        if key=='deb':text+=' Requer Python 3.13+; o Python padrão do Ubuntu 24.04 ainda não é suficiente.'
        self.tool_status.setText(status);self.description.setText(text)
        self.build.setText('Exportar fonte…' if key=='source' else 'Exportar receita…' if self.recipe_only.isChecked() else 'Construir '+name+'…')

    def check(self):
        """Verifica o projeto sem executar código e permite abrir a origem de cada problema."""
        if not self.window._finish_field_edit():return False
        self.stages.setText('1 Formato  →  [2 Verificação]  →  3 Construção  →  4 Resultado')
        self.checks.clear();self.checks.show();self.check_hint.hide();issues=preflight(self.window.project,self.window.source.text,self.window.assets.read,self.format.currentData())
        for issue in issues:
            prefix={'error':'✕','warning':'!','success':'✓'}[issue['level']];item=QListWidgetItem(prefix+'  '+issue['message']);item.setData(Qt.ItemDataRole.UserRole,issue['field']);self.checks.addItem(item)
        row_height=self.checks.sizeHintForRow(0) if self.checks.count() else 24;self.checks.setFixedHeight(min(160,max(32,row_height*self.checks.count()+8)))
        return not any(issue['level']=='error' for issue in issues)

    def fix_issue(self,item):
        """Conduz à configuração ou interface que precisa de correção."""
        field=item.data(Qt.ItemDataRole.UserRole)
        if field=='windows' and self.window.project.metadata.get('empty_map'):self.window.set_mode('Mapa')
        elif field=='logic':self.window.set_mode('Lógica');self.window.drawer.show();self.window.drawer.setCurrentIndex(1)
        elif field:self.window.application_settings(field)

    def start_job(self,job,prepare=False):
        """Uma operação de cada vez, com controles e cancelamento coerentes."""
        self.stages.setText('Preparação das ferramentas' if prepare else '1 Formato  →  2 Verificação  →  [3 Construção]  →  4 Resultado')
        self.job=job;self.build.setEnabled(False);self.prepare.setEnabled(False);self.check_button.setEnabled(False);self.format.setEnabled(False);self.environment.setEnabled(False);self.recipe_only.setEnabled(False);self.cancel_button.setEnabled(True);self.cancel_button.show()
        self.result.clear();self.open_folder.hide();self.copy_path.hide();self.build_log.clear();self.progress_bar.setValue(0);self.progress_bar.show();self.result.setText('Preparando ferramentas…' if prepare else 'Construindo…')
        job.progress.connect(lambda number,text:(self.progress_bar.setValue(number),self.build_log.appendPlainText(text)))
        job.completed.connect(self.prepared if prepare else self.completed);job.failed.connect(self.failed);job.finished.connect(self.build_finished);job.start()

    def prepare_environment(self):
        """Preparação explícita pode baixar ferramentas e SDK, sem tocar no projeto."""
        if self.job and self.job.isRunning():return
        from makebench.core.project import Project
        self.start_job(PrepareJob(Project.from_dict(self.window.project.to_dict()),self.format.currentData(),self),True)

    def build_source(self):
        """Constrói exatamente o formato escolhido a partir de um snapshot do documento."""
        if self.job and self.job.isRunning():return
        if not self.check():return
        key=self.format.currentData();_,tool,suffix=FORMATS[key];recipe=key!='source' and self.recipe_only.isChecked();environment=self.environment.currentData()
        if key not in {'source','flatpak'} and not recipe:
            use_managed=environment=='managed' or environment=='auto' and not build_tools().get(tool)
            if use_managed and not prepared():self.failed('Clique em Preparar ferramentas antes de construir.');return
            if environment=='system' and not build_tools().get(tool):self.failed('Ferramenta ausente no sistema. Use Automático e Preparar ferramentas.');return
        suffix='-receita.zip' if recipe else suffix
        filename,_=QFileDialog.getSaveFileName(self,'Exportar '+FORMATS[key][0],self.window.project.name+suffix,'Arquivos (*'+suffix+')')
        if not filename:return
        from makebench.core.project import Project
        project=Project.from_dict(self.window.project.to_dict());assets={name:self.window.assets.read(name) for name in project.asset_paths()}
        self.start_job(BuildJob(project,self.window.source.text,assets.__getitem__,filename,self,key,recipe,environment))

    def cancel_build(self):
        """Aguarda interrupção e limpeza, sem publicar resultado parcial."""
        if self.job:self.job.cancel.set();self.cancel_button.setEnabled(False);self.result.setText('Cancelando…')

    def prepared(self,result):
        """Confirma apenas o ambiente; nenhum pacote foi construído nesta etapa."""
        self.result.setText(result['status']);self.progress_bar.setValue(100)

    def completed(self,result):
        """Resultado identifica formato, tamanho e pasta; hash permanece nos detalhes."""
        self.stages.setText('1 Formato  →  2 Verificação  →  3 Construção  →  [4 Resultado]')
        self.output_path=Path(result['path']);self.result.setText(f"{result.get('status','Exportado')}\n{self.output_path.name} · {result['size']/1048576:.1f} MB" if result['size']>=1048576 else f"{result.get('status','Exportado')}\n{self.output_path.name} · {result['size']/1024:.0f} KB");self.result.setToolTip(str(self.output_path))
        self.build_log.appendPlainText(str(self.output_path)+'\nSHA-256: '+result['sha256']);self.progress_bar.setValue(100);self.open_folder.show();self.copy_path.show()

    def failed(self,message):
        """Mantém a causa acessível junto da saída da ferramenta."""
        self.stages.setText('Operação interrompida · consulte o diagnóstico')
        self.result.setText(message.splitlines()[0] if message else 'A operação não terminou.');self.build_log.appendPlainText(message);self.log_toggle.setChecked(True)

    def build_finished(self):
        """Libera controles só depois da saída e limpeza da thread."""
        self.build.setEnabled(True);self.check_button.setEnabled(True);self.format.setEnabled(True);self.cancel_button.setEnabled(False);self.cancel_button.hide();self.sync()

    def show_result_folder(self):
        """Abre a pasta, sem executar o pacote exportado."""
        if hasattr(self,'output_path'):QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_path.parent)))


class ExportDialog(QDialog):
    """Exportação em janela compacta; fechar preserva uma construção em andamento."""
    def __init__(self,window):
        """A janela cresce com verificações e detalhes, sem ocupar a bancada principal."""
        super().__init__(window);self.setWindowTitle('Exportar aplicativo');self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint,False)
        layout=QVBoxLayout(self);layout.setContentsMargins(6,6,6,6);layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.panel=PublishPanel(window);self.panel.setFixedWidth(min(680,max(460,window.screen().availableGeometry().width()-60)));layout.addWidget(self.panel)
        row=QHBoxLayout();row.addStretch();close=QPushButton('Fechar');close.clicked.connect(self.hide);row.addWidget(close);layout.addLayout(row)
