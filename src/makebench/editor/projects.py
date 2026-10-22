"""Início, projetos locais, recentes, recuperação e compartilhamento portátil."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import unicodedata

from PySide6.QtCore import Qt, QStandardPaths
from PySide6.QtWidgets import (QDialog,QDialogButtonBox,QFileDialog,QFormLayout,QHBoxLayout,
    QLabel,QLineEdit,QListWidget,QListWidgetItem,QMessageBox,QPushButton,QVBoxLayout,QWidget,QComboBox)
from makebench.core.project import Project,ProjectError
from makebench.core.storage import load_project,save_project
from makebench.core.source import SourceBuffer
from makebench.core.bundle import read_bundle,write_bundle
from .assets import AssetStore


def slug(text):
    """Produz nome de pasta simples, sem usar texto como caminho arbitrário."""
    clean=unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','-',clean).strip('-') or 'meu-aplicativo'


class ProjectMixin:
    """Mantém operações de arquivo independentes da execução do aplicativo."""

    def install_projects(self):
        """Monta a entrada e comandos sem substituir um projeto aberto por argumento."""
        home=QWidget();home.setObjectName('home');outer=QVBoxLayout(home);outer.setContentsMargins(48,32,48,32)
        title=QLabel('Makebench');font=title.font();font.setPointSize(24);title.setFont(font);outer.addWidget(title)
        subtitle=QLabel('Sua bancada para criar aplicativos Linux.');subtitle.setProperty('muted',True);outer.addWidget(subtitle)
        self.recovery_row=QWidget();rr=QHBoxLayout(self.recovery_row)
        rr.addWidget(QLabel('Há alterações de uma sessão anterior para recuperar.'),1)
        recover=QPushButton('Recuperar');recover.clicked.connect(self.recover_latest);rr.addWidget(recover)
        discard=QPushButton('Descartar recuperação');discard.clicked.connect(self.discard_recovery);rr.addWidget(discard)
        outer.addWidget(self.recovery_row)
        columns=QHBoxLayout();start=QVBoxLayout();start.addWidget(QLabel('Começar um projeto'))
        for key,title,description in [('blank','Em branco','Uma janela para começar do seu jeito.'),('welcome','Assistente de boas-vindas','Etapas, navegação e uma janela principal.'),('tasks','Central de tarefas','Perguntas, scripts, progresso e resultados.')]:
            button=QPushButton(title+'\n'+description);button.setMinimumHeight(76)
            button.clicked.connect(lambda _,key=key:self.new_project_dialog(key));start.addWidget(button)
        opening=QPushButton('Abrir projeto…');opening.clicked.connect(self.open_project);start.addWidget(opening)
        start.addStretch();columns.addLayout(start,1)
        recent_box=QVBoxLayout();recent_box.addWidget(QLabel('Projetos recentes'))
        self.recent_list=QListWidget();self.recent_list.setObjectName('recent_list');self.recent_list.setAccessibleName('Projetos recentes')
        self.recent_list.itemActivated.connect(self.open_recent)
        recent_box.addWidget(self.recent_list)
        actions=QHBoxLayout()
        for label,callback in [('Abrir selecionado',lambda:self.open_recent(self.recent_list.currentItem())),('Localizar…',self.locate_recent),('Remover da lista',self.remove_recent)]:
            button=QPushButton(label);button.clicked.connect(callback);actions.addWidget(button)
        recent_box.addLayout(actions);columns.addLayout(recent_box,2);outer.addLayout(columns,1)
        back=QPushButton('Voltar ao projeto aberto');back.clicked.connect(lambda:self.set_mode(self._mode));outer.addWidget(back,0,Qt.AlignmentFlag.AlignLeft)
        self.home_page=home;self.pages.addWidget(home)
        self.new_action.triggered.disconnect();self.new_action.triggered.connect(lambda:self.new_project_dialog('blank'))
        menu=self.menuBar().actions()[0].menu()
        menu.addSeparator();share=menu.addAction('Compartilhar projeto…');share.triggered.connect(self.share_project)
        self.refresh_recents();self.refresh_recovery()
        from PySide6.QtCore import QFileSystemWatcher
        self.source_watcher=QFileSystemWatcher(self);self.source_watcher.fileChanged.connect(self.source_changed_externally)
        self.watch_source()
        self.pages.currentChanged.connect(lambda _:self._update_actions())
        self.external_change_row=QWidget();row=QHBoxLayout(self.external_change_row)
        row.addWidget(QLabel('Funções alteradas fora do Makebench.'),1)
        reload=QPushButton('Recarregar arquivo');reload.clicked.connect(self.reload_source);row.addWidget(reload)
        keep=QPushButton('Manter minha versão');keep.clicked.connect(self.keep_source);row.addWidget(keep)
        self.editor_page.layout().insertWidget(1,self.external_change_row);self.external_change_row.hide()
        self.trust_row=QWidget();tr=QHBoxLayout(self.trust_row);self.trust_label=QLabel();self.trust_label.setWordWrap(True);tr.addWidget(self.trust_label,1)
        review=QPushButton('Revisar código');review.clicked.connect(lambda:self.set_mode('Código'));tr.addWidget(review)
        trust=QPushButton('Confiar e continuar');trust.clicked.connect(lambda:(self.trust_project(),self.refresh_trust_banner()));tr.addWidget(trust)
        self.editor_page.layout().insertWidget(1,self.trust_row);self.trust_row.hide()
        self.refresh_trust_banner()

    def reload_source(self):
        """Recarrega por escolha explícita, sem importar o arquivo Python."""
        if not self.path:return
        if self.source.path and not self.source.path.exists():
            self.statusBar().showMessage('O arquivo foi removido. Sua edição permanece aqui; use Manter minha versão ou Salvar como.',10000);return
        try:
            self._trusted_session=False
            self.source=SourceBuffer.load(self.path)
            self.source_editor.blockSignals(True);self.source_editor.setPlainText(self.source.text);self.source_editor.blockSignals(False)
            self.external_change_row.hide();self._update_code();self._update_actions();self.watch_source()
        except (OSError,ProjectError) as exc:self._show_error(str(exc))

    def keep_source(self):
        """Autoriza preservar o buffer atual; a próxima gravação continua explícita."""
        if self.source.path:
            try:self.source.original=self.source.path.read_bytes() if self.source.path.exists() else None
            except OSError as exc:self._show_error(str(exc));return
        self.external_change_row.hide();self.watch_source();self.refresh_trust_banner()

    def show_home(self):
        """Mostra a entrada sem descartar ou executar o documento em edição."""
        if not self._finish_field_edit():return
        self.refresh_recents();self.refresh_recovery();self.pages.setCurrentWidget(self.home_page);self.workspace_toolbar.hide()

    def refresh_recents(self):
        """Apresenta caminhos reais e indica documentos movidos ou removidos."""
        self.recent_list.clear()
        paths=self.settings.value('projects/recent',[],type=list)
        for value in paths[:20]:
            path=Path(value);text=path.parent.name+'\n'+str(path)
            if not path.is_file():text+=' · Não encontrado'
            item=QListWidgetItem(text);item.setData(Qt.ItemDataRole.UserRole,str(path));self.recent_list.addItem(item)

    def remember_project(self):
        """Adiciona o caminho ao topo dos recentes após abertura ou gravação bem-sucedida."""
        if self.path:
            paths=self.settings.value('projects/recent',[],type=list)
            paths=[str(self.path),*[p for p in paths if p!=str(self.path)]]
            self.settings.setValue('projects/recent',paths[:20]);self.refresh_recents()
            if getattr(self,'_trusted_session',False):self.trust_project()
        self.watch_source()
        self.refresh_trust_banner()

    def open_recent(self,item):
        """Abre um recente existente sem destruir o projeto atual em caso de erro."""
        if not item:return
        path=Path(item.data(Qt.ItemDataRole.UserRole))
        if not path.is_file():self.statusBar().showMessage('Projeto não encontrado. Use Localizar ou remova da lista.',6000);return
        if not self._confirm_discard():return
        try:self._replace_project(load_project(path),path);self.pages.setCurrentWidget(self.editor_page);self.workspace_toolbar.show()
        except (OSError,ProjectError) as exc:self._show_error(str(exc))

    def locate_recent(self):
        """Substitui somente a entrada selecionada; não movimenta arquivos do usuário."""
        item=self.recent_list.currentItem()
        if not item:return
        filename,_=QFileDialog.getOpenFileName(self,'Localizar projeto','','Projetos Makebench (*.makebench.json)')
        if not filename:return
        try:load_project(filename)
        except ProjectError as exc:self._show_error(str(exc));return
        paths=self.settings.value('projects/recent',[],type=list)
        old=item.data(Qt.ItemDataRole.UserRole)
        self.settings.setValue('projects/recent',[filename if p==old else p for p in paths]);self.refresh_recents()

    def remove_recent(self):
        """Remove o atalho sem excluir o projeto em disco."""
        item=self.recent_list.currentItem()
        if item:
            self.settings.setValue('projects/recent',[p for p in self.settings.value('projects/recent',[],type=list) if p!=item.data(Qt.ItemDataRole.UserRole)])
            self.refresh_recents()

    def new_project_dialog(self,template='blank'):
        """Cria uma pasta somente após validar nome, destino e alterações pendentes."""
        from makebench.core.templates import MODELS
        from makebench.core.environment import gtk_support
        from .theme import manager
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QPixmap,QPainter,QPen,QColor,QIcon
        dialog=QDialog(self);dialog.setWindowTitle('O que você quer criar?');dialog.resize(760,660);form=QFormLayout(dialog)
        title=QLabel('O que você quer criar?');title.setProperty('title',True);form.addRow(title)
        cards=QListWidget();cards.setViewMode(QListWidget.ViewMode.IconMode);cards.setIconSize(QSize(112,68));cards.setGridSize(QSize(140,126));cards.setMinimumHeight(260);cards.setResizeMode(QListWidget.ResizeMode.Adjust)
        model=QComboBox();model.hide()
        for key,label,description in MODELS:
            model.addItem(label,key)
            pix=QPixmap(112,68);t=manager().tokens;pix.fill(QColor(t['canvas']));paint=QPainter(pix);paint.setRenderHint(QPainter.RenderHint.Antialiasing);paint.setBrush(QColor(t['raised']));paint.setPen(QPen(QColor(t['control']),1));paint.drawRoundedRect(4,3,104,62,6,6);paint.drawLine(4,15,108,15)
            if key=='multi':paint.drawLine(35,16,35,63)
            if key=='tasks':
                for y in (25,38,51):paint.drawRoundedRect(12,y,88,6,3,3)
            elif key!='blank':
                paint.drawLine(44 if key=='multi' else 14,27,94,27);paint.setBrush(QColor(t['accent']));paint.setPen(Qt.PenStyle.NoPen);paint.drawRoundedRect(66,46,30,10,4,4)
            paint.end();item=QListWidgetItem(QIcon(pix),label);item.setToolTip(description);item.setData(Qt.ItemDataRole.UserRole,key);cards.addItem(item)
        model.setCurrentIndex(max(0,model.findData(template)));cards.setCurrentRow(model.currentIndex());cards.currentRowChanged.connect(model.setCurrentIndex);form.addRow(cards)
        backend=QComboBox();backend.addItem('GTK — aparência Adwaita','gtk');backend.addItem('Qt — controles do desktop','qt')
        supported=gtk_support()['gtk4'];preferred=self.settings.value('v1/projects/backend','gtk' if supported else 'qt');backend.setCurrentIndex(backend.findData(preferred if supported else 'qt'))
        form.addRow('Aparência do aplicativo',backend)
        note=QLabel('GTK4 detectado. Testar abre controles GTK reais.' if supported else 'GTK4 não encontrado neste Python. Qt foi selecionado; GTK exige PyGObject e GTK4 no sistema.');note.setWordWrap(True);note.setProperty('muted',True);form.addRow(note)
        name=QLineEdit('Meu aplicativo');form.addRow('Nome',name)
        folder=QLineEdit(str(Path(self.settings.value('v1/projects/folder',str(Path.home()/'Makebench'/'Projetos')))/'meu-aplicativo'))
        folder_row=QWidget();row=QHBoxLayout(folder_row);row.setContentsMargins(0,0,0,0);row.addWidget(folder)
        choose=QPushButton('Escolher…');row.addWidget(choose)
        def choose_folder():
            """Recebe uma escolha de pasta sem criar ou modificar arquivos."""
            value=QFileDialog.getExistingDirectory(dialog,'Pasta do novo projeto',folder.text())
            if value:folder.setText(value)
        choose.clicked.connect(choose_folder);form.addRow('Pasta',folder_row)
        name.textEdited.connect(lambda text:folder.setText(str(Path(folder.text()).parent/slug(text))))
        info=QLabel('Será criada uma pasta com o projeto, suas funções e imagens.');info.setWordWrap(True);form.addRow(info)
        from PySide6.QtWidgets import QGroupBox
        advanced=QGroupBox('Avançado');advanced.setCheckable(True);advanced.setChecked(False);af=QFormLayout(advanced);identifier=QLineEdit();identifier.setPlaceholderText('br.exemplo.meuapp');identifier.setEnabled(False);advanced.toggled.connect(identifier.setEnabled);af.addRow('Identificador',identifier);form.addRow(advanced)
        error=QLabel();error.setWordWrap(True);form.addRow(error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Criar projeto')
        buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        def create():
            """Cria o item solicitado com os valores validados do diálogo."""
            destination=Path(folder.text()).expanduser()
            if not name.text().strip():error.setText('Informe um nome para o projeto.');return
            if destination.exists() and any(destination.iterdir()):error.setText('Escolha uma pasta nova ou vazia.');return
            if not self._confirm_discard():return
            try:
                project,source,assets=self.project_template(model.currentData(),name.text().strip())
                project.application['backend']=backend.currentData()
                if identifier.text().strip():project.application['id']=identifier.text().strip()
                destination.mkdir(parents=True,exist_ok=True)
                self._replace_project(project,None);self.source.text=source;self.source_editor.setPlainText(source);self.assets=assets
                if not self.save_to(destination/'project.makebench.json'):return
                self._created_here=True;self.trust_project();self.pages.setCurrentWidget(self.editor_page);dialog.accept()
            except (OSError,ProjectError) as exc:error.setText(str(exc))
        buttons.accepted.connect(create);dialog.exec()

    def project_template(self,key,name):
        """Copia modelos distribuídos, mantendo os exemplos originais intactos."""
        if key!='tasks':
            from makebench.core.templates import make_template
            return make_template(key,name),SourceBuffer().text,AssetStore()
        root=Path(__file__).resolve().parents[3]/'examples'/'script-center'
        if not (root/'app.makebench.json').is_file():
            root=Path(__file__).resolve().parent.parent/'templates'/'script-center'
        project=load_project(root/'app.makebench.json')
        from makebench.core.project import new_id
        project.id=new_id('project');project.name=name;project.root.properties['title']=name
        return project,SourceBuffer.load(root/'app.makebench.json').text,AssetStore(root)

    def share_project(self):
        """Exporta o documento editável e recursos; não é o exportador de aplicativo."""
        if not self._finish_field_edit():return
        filename,_=QFileDialog.getSaveFileName(self,'Compartilhar projeto',slug(self.project.name)+'.zip','Projeto compartilhado (*.zip)')
        if not filename:return
        try:write_bundle(self.project,self.source.text,self.assets.read,filename);self.statusBar().showMessage('Projeto compartilhado em '+filename,7000)
        except (OSError,ProjectError) as exc:self._show_error(str(exc))

    def recovery_root(self):
        """Resolve estado XDG; não usa a pasta original do projeto para snapshots."""
        base=os.environ.get('XDG_STATE_HOME') or str(Path.home()/'.local'/'state')
        return Path(base)/'makebench'/'recovery'

    def snapshot_recovery(self):
        """Grava cópia completa, inclusive recursos ainda não salvos; nunca executa código."""
        if not (self.history.dirty or self.source.dirty or self.logic.pending or self.script_dirty()):return
        if not self.prepare_script_change() or not self.logic.flush():return
        root=self.recovery_root();root.mkdir(parents=True,exist_ok=True)
        target=root/self.project.id
        temporary=Path(tempfile.mkdtemp(prefix='.snapshot-',dir=root))
        try:
            write_bundle(self.project,self.source.text,self.assets.read,temporary/'project.zip')
            (temporary/'session.json').write_text(json.dumps({'path':str(self.path) if self.path else None,'time':time.time(),'name':self.project.name}),encoding='utf-8')
            previous=target.with_name(target.name+'.previous')
            if previous.exists():shutil.rmtree(previous)
            if target.exists():target.rename(previous)
            temporary.rename(target)
            if previous.exists():shutil.rmtree(previous)
        except (OSError,ProjectError) as exc:self.statusBar().showMessage('Não foi possível criar recuperação: '+str(exc),6000)
        finally:
            if temporary.exists():shutil.rmtree(temporary)

    def clear_recovery(self,project_id=None):
        """Apaga apenas o snapshot do projeto confirmado como salvo ou descartado."""
        for suffix in ('','.previous'):
            path=self.recovery_root()/((project_id or self.project.id)+suffix)
            if path.exists():shutil.rmtree(path)

    def refresh_recovery(self):
        """Detecta snapshots válidos de sessões anteriores sem carregar código."""
        root=self.recovery_root()
        self.recoveries=sorted([p for p in root.glob('*') if (p/'session.json').is_file() and (p/'project.zip').is_file()],key=lambda p:p.stat().st_mtime,reverse=True) if root.exists() else []
        self.recovery_row.setVisible(bool(self.recoveries))

    def recover_latest(self):
        """Recupera em uma pasta de sessão isolada, deixando o original intocado."""
        if not self.recoveries or not self._confirm_discard():return
        snapshot=self.recoveries[0]
        try:
            self._recovery_temp=tempfile.TemporaryDirectory(prefix='makebench-recovered-')
            path=read_bundle(snapshot/'project.zip',Path(self._recovery_temp.name))
            project=load_project(path);source=SourceBuffer.load(path)
            self._replace_project(project,None);self.source.text=source.text;self.source_editor.setPlainText(source.text)
            self.assets=AssetStore(path.parent)
            # Recuperação precisa de Salvar como; não associa fingerprints ao original.
            self.history.push(project);self.source.saved_text=source.text+chr(0);self._recovered=True
            self._refresh();self.pages.setCurrentWidget(self.editor_page);self.workspace_toolbar.show()
            self.statusBar().showMessage('Alterações recuperadas. Salve em uma pasta para continuar.',10000)
        except (OSError,ProjectError,ValueError) as exc:self._show_error(str(exc))

    def discard_recovery(self):
        """Descarta só a recuperação selecionada, preservando o projeto original."""
        if self.recoveries:shutil.rmtree(self.recoveries[0]);self.refresh_recovery()

    def fingerprint(self):
        """Vincula confiança ao conteúdo que será executado, não apenas ao caminho."""
        data=json.dumps(self.project.to_dict(),sort_keys=True,ensure_ascii=True)+self.source.text
        return hashlib.sha256(data.encode()).hexdigest()

    def trust_project(self):
        """Registra consentimento para o snapshot atual do projeto."""
        self._trusted_session=True
        self._trusted=self.fingerprint()
        if self.path:self.settings.setValue('trust/'+hashlib.sha256(str(self.path).encode()).hexdigest(),self._trusted)

    def confirm_trust(self):
        """Pede consentimento uma vez por conteúdo importado antes de executar."""
        if not self.path or getattr(self,'_created_here',False) or getattr(self,'_trusted_session',False):return True
        key='trust/'+hashlib.sha256(str(self.path).encode()).hexdigest()
        if getattr(self,'_trusted',None)==self.fingerprint() or self.settings.value(key)==self.fingerprint():return True
        dialog=QMessageBox(self);dialog.setWindowTitle('Testar este projeto?')
        dialog.setText('Testar executará funções Python e scripts com suas permissões. O processo separado não é uma sandbox. Abra Código para revisar o projeto antes de continuar.')
        run=dialog.addButton('Confiar e testar',QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton('Revisar código',QMessageBox.ButtonRole.RejectRole);dialog.exec()
        if dialog.clickedButton() is run:self.trust_project();return True
        self.set_mode('Código');return False

    def watch_source(self):
        """Acompanha o arquivo próprio sem substituir uma edição automaticamente."""
        if not hasattr(self,'source_watcher'):return
        old=self.source_watcher.files()
        if old:self.source_watcher.removePaths(old)
        if self.source.path and self.source.path.exists():self.source_watcher.addPath(str(self.source.path))

    def source_changed_externally(self,_path):
        """Sinaliza conflito; o fingerprint de SourceBuffer continua protegendo a gravação."""
        try:data=self.source.path.read_bytes() if self.source.path and self.source.path.exists() else None
        except OSError as exc:self.statusBar().showMessage(str(exc),7000);return
        if self.source.path and data!=self.source.original:
            self.external_change_row.show()
            self.statusBar().showMessage('Funções alteradas fora do Makebench. Escolha Recarregar ou Manter minha versão.',15000)
        self.watch_source()

    def save_as_dialog(self):
        """Solicita nome e pasta, copiando funções e recursos pelos mecanismos existentes."""
        if not self._finish_field_edit():return False
        dialog=QDialog(self);dialog.setWindowTitle('Salvar projeto como');dialog.resize(620,210);form=QFormLayout(dialog)
        name=QLineEdit(self.path.name[:-len('.makebench.json')] if self.path else slug(self.project.name))
        folder=QLineEdit(str(self.path.parent) if self.path else str(Path.home()/'Makebench'/'Projetos'/slug(self.project.name)))
        form.addRow('Nome do arquivo',name);row=QWidget();rl=QHBoxLayout(row);rl.setContentsMargins(0,0,0,0);rl.addWidget(folder)
        choose=QPushButton('Escolher…');rl.addWidget(choose)
        def choose_folder():
            """Recebe uma escolha de pasta sem criar ou modificar arquivos."""
            path=QFileDialog.getExistingDirectory(dialog,'Pasta do projeto',folder.text())
            if path:folder.setText(path)
        choose.clicked.connect(choose_folder);form.addRow('Pasta',row)
        note=QLabel('Inclui o arquivo de funções e os recursos do projeto. Fontes diferentes no destino são preservadas.');note.setWordWrap(True);form.addRow(note)
        error=QLabel();error.setWordWrap(True);form.addRow(error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons);buttons.rejected.connect(dialog.reject)
        saved=[]
        def save():
            """Valida os campos e só confirma depois de salvar com sucesso."""
            filename=name.text().strip()
            if not filename or Path(filename).name!=filename or filename in {'.','..'}:error.setText('Informe um nome de arquivo, sem pastas.');return
            if not filename.endswith('.makebench.json'):filename+='.makebench.json'
            destination=Path(folder.text()).expanduser()/filename
            if destination.exists() and destination!=self.path:
                if QMessageBox.warning(dialog,'Substituir projeto?','O destino já contém um projeto. Suas funções e recursos ainda serão verificados antes de salvar.',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Save:return
            try:destination.parent.mkdir(parents=True,exist_ok=True)
            except OSError as exc:error.setText(str(exc));return
            if self.save_to(destination):saved.append(True);dialog.accept()
        buttons.accepted.connect(save);dialog.exec();return bool(saved)

    def refresh_trust_banner(self):
        """Explica execução futura sem bloquear a leitura e a edição do projeto."""
        if not hasattr(self,'trust_row'):return
        trusted=not self.path or getattr(self,'_created_here',False) or getattr(self,'_trusted_session',False)
        if self.path and not trusted:
            key='trust/'+hashlib.sha256(str(self.path).encode()).hexdigest()
            if self.settings.value(key)==self.fingerprint():self._trusted_session=True;trusted=True
        self.trust_row.setVisible(not trusted)
        if not trusted:
            from makebench.core.logic import function_names
            count=len(function_names(self.source.text)[0])
            def scripts(value):
                """Conta scripts declarados, sem executar seus textos."""
                if isinstance(value,dict):return int(value.get('op')=='script')+sum(scripts(v) for v in value.values())
                if isinstance(value,list):return sum(scripts(v) for v in value)
                return 0
            script_count=sum(scripts(f.get('body')) for f in self.project.workflows)
            self.trust_label.setText(f'Projeto ainda não revisado: {count} função(ões) Python e {script_count} script(s). Nada foi executado. Testar executa esse código com suas permissões.')
