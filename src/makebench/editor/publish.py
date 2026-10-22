"""Configuração e construção do aplicativo criado, separadas do pacote do editor."""
from pathlib import Path
import threading
from PySide6.QtCore import QThread,QUrl,Signal,Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox,QFileDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,
    QListWidget,QPlainTextEdit,QProgressBar,QPushButton,QScrollArea,QSplitter,QStackedWidget,QVBoxLayout,QWidget)
from makebench.core.exporter import effects,export_source,verify


class BuildJob(QThread):
    """Constrói em pasta temporária fora do ciclo de eventos, sem rodar o projeto."""
    progress=Signal(int,str);completed=Signal(dict);failed=Signal(str)
    def __init__(self,project,source,read_asset,destination,parent):
        """Guarda snapshot independente e um cancelamento cooperativo de construção."""
        super().__init__(parent);self.project=project;self.source=source;self.read_asset=read_asset;self.destination=destination;self.cancel=threading.Event()

    def run(self):
        """Publica somente resultado completo; erros preservam o destino anterior."""
        try:self.completed.emit(export_source(self.project,self.source,self.read_asset,self.destination,self.progress.emit,self.cancel.is_set))
        except Exception as exc:self.failed.emit(str(exc))


class PublishPanel(QWidget):
    """Implementa Identidade, Ícone, Dependências, Permissões e Fonte Python."""
    def __init__(self,window):
        """Monta campos de metadados e uma jornada verificável de construção."""
        super().__init__();self.window=window;self.job=None;self.fields={};self._syncing=False
        layout=QVBoxLayout(self)
        intro=QLabel('Exporte o aplicativo que você criou. O pacote do próprio Makebench é produzido separadamente.');intro.setWordWrap(True);layout.addWidget(intro)
        split=QSplitter();self.sections=QListWidget();self.sections.addItems(['Identidade','Ícone','Dependências','Permissões','Destinos']);self.sections.setMaximumWidth(220)
        self.pages=QStackedWidget();split.addWidget(self.sections);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.pages);split.addWidget(scroll);layout.addWidget(split,1)
        identity=QWidget();form=QFormLayout(identity)
        for key,label,placeholder in [('name','Nome público','Meu aplicativo'),('id','Identificador','br.exemplo.meuapp'),('version','Versão','0.1.0'),('description','Descrição','O que o aplicativo faz'),('author','Autor',''),('license','Licença','Ainda não definida'),('category','Categoria','Utility')]:
            field=QLineEdit();field.setPlaceholderText(placeholder);field.editingFinished.connect(lambda key=key,field=field:self.change(key,field.text()));form.addRow(label,field);self.fields[key]=field
        self.pages.addWidget(identity)
        icons=QWidget();il=QVBoxLayout(icons);self.icon_label=QLabel('Escolha PNG de 256 px ou mais, ou SVG.');il.addWidget(self.icon_label)
        self.icon_preview=QLabel();self.icon_preview.setMinimumSize(256,256);il.addWidget(self.icon_preview)
        choose=QPushButton('Escolher ícone…');choose.clicked.connect(self.choose_icon);il.addWidget(choose);il.addStretch();self.pages.addWidget(icons)
        dependencies=QWidget();df=QFormLayout(dependencies)
        df.addRow('Python mínimo',QLabel('3.13'));df.addRow('Qt',QLabel('PySide6 6.11.2'))
        self.packages=QLineEdit();self.packages.setPlaceholderText('Ex.: requests>=2.32; Pillow>=11')
        self.packages.editingFinished.connect(lambda:self.change('packages',[v.strip() for v in self.packages.text().split(';') if v.strip()]))
        df.addRow('Pacotes Python',self.packages);self.programs=QLabel();self.programs.setWordWrap(True);df.addRow('Programas detectados',self.programs);self.pages.addWidget(dependencies)
        self.permissions=QLabel();self.permissions.setWordWrap(True);self.permissions.setAlignment(Qt.AlignmentFlag.AlignTop);self.pages.addWidget(self.permissions)
        destinations=QWidget();dest=QVBoxLayout(destinations)
        dest.addWidget(QLabel('Fonte Python executável · Disponível'))
        desc=QLabel('Código, funções próprias, imagens e runtime do aplicativo. O resultado roda fora do Makebench com Python e PySide6.');desc.setWordWrap(True);dest.addWidget(desc)
        for label in ('AppImage','Flatpak','DEB','RPM'):
            button=QPushButton(label+' · Em breve');button.setEnabled(False);dest.addWidget(button)
        dest.addStretch();self.pages.addWidget(destinations)
        self.sections.currentRowChanged.connect(self.pages.setCurrentIndex);self.sections.setCurrentRow(0)
        self.checks=QListWidget();self.checks.setMaximumHeight(150);self.checks.itemActivated.connect(self.fix_issue);layout.addWidget(self.checks);self.checks.hide()
        row=QHBoxLayout();check=QPushButton('Verificar');check.clicked.connect(self.check);row.addWidget(check)
        self.build=QPushButton('Construir fonte Python…');self.build.setProperty('primary',True);self.build.clicked.connect(self.build_source);row.addWidget(self.build)
        self.cancel_button=QPushButton('Cancelar construção');self.cancel_button.setEnabled(False);self.cancel_button.clicked.connect(self.cancel_build);row.addWidget(self.cancel_button)
        layout.addLayout(row);self.progress_bar=QProgressBar();self.progress_bar.setValue(0);layout.addWidget(self.progress_bar);self.progress_bar.hide()
        self.build_log=QPlainTextEdit();self.build_log.setReadOnly(True);self.build_log.setMaximumHeight(100);layout.addWidget(self.build_log);self.build_log.hide()
        self.result=QLabel();self.result.setWordWrap(True);self.result.setTextFormat(Qt.TextFormat.PlainText);self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(self.result)
        self.open_folder=QPushButton('Abrir pasta do resultado');self.open_folder.hide();self.open_folder.clicked.connect(self.show_result_folder);layout.addWidget(self.open_folder)
        self.sync()

    def change(self,key,value):
        """Grava metadados no histórico sem tocar em fontes próprias ou executar código."""
        if self._syncing:return
        if self.window.project.application.get(key)==value:return
        self.window._edit(lambda:self.window.project.application.update({key:value}))

    def sync(self):
        """Atualiza campos sem sobrescrever uma edição ainda focada."""
        self._syncing=True;app=self.window.project.application
        for key,field in self.fields.items():
            if not field.hasFocus():field.setText(str(app.get(key,'')))
        if not self.packages.hasFocus():self.packages.setText('; '.join(app.get('packages',[])))
        self.icon_label.setText(app.get('icon') or 'Escolha PNG de 256 px ou mais, ou SVG.')
        programs,admin=effects(self.window.project)
        self.programs.setText('\n'.join(programs) or 'Nenhum programa literal declarado nos blocos. Funções Python podem exigir outros programas.')
        self.permissions.setText('Fonte Python roda com as permissões de quem executa.\n\n'+('Há ações administrativas declaradas: o destino precisa de Polkit/pkexec, agente de autenticação e programas instalados. A senha é solicitada pelo sistema.' if admin else 'Nenhuma ação administrativa declarada nos blocos. Funções Python próprias também podem acessar o sistema.')+'\n\nFlatpak será um destino separado; programas do host e ações administrativas não são prometidos nesse formato.')
        if app.get('icon'):
            from PySide6.QtGui import QPixmap
            try:
                pixmap=QPixmap();pixmap.loadFromData(self.window.assets.read(app['icon']));self.icon_preview.setPixmap(pixmap.scaled(256,256,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            except Exception:self.icon_preview.clear()
        self._syncing=False

    def choose_icon(self):
        """Importa o ícone no conjunto de recursos preservado no Salvar como."""
        filename,_=QFileDialog.getOpenFileName(self,'Ícone do aplicativo','','Ícones (*.png *.svg)')
        if filename:
            try:self.change('icon',self.window.assets.import_image(Path(filename)))
            except Exception as exc:self.window._show_error(str(exc))

    def check(self):
        """Lista pré-requisitos com campo de origem para correção direta."""
        self.window._finish_field_edit();self.checks.clear();self.checks.show()
        issues=verify(self.window.project,self.window.source.text,self.window.assets.read)
        from PySide6.QtWidgets import QListWidgetItem
        for issue in issues:
            prefix={'error':'Erro','warning':'Aviso','success':'Pronto'}[issue['level']]
            item=QListWidgetItem(prefix+' · '+issue['message']);item.setData(Qt.ItemDataRole.UserRole,issue['field']);self.checks.addItem(item)
        return not any(issue['level']=='error' for issue in issues)

    def fix_issue(self,item):
        """Leva ao campo ou fluxo que impede a exportação."""
        field=item.data(Qt.ItemDataRole.UserRole)
        if field in self.fields:self.sections.setCurrentRow(0);self.fields[field].setFocus()
        elif field=='icon':self.sections.setCurrentRow(1)
        elif field in {'packages','dependencies'}:self.sections.setCurrentRow(2)
        elif field=='permissions':self.sections.setCurrentRow(3)
        elif field=='logic':self.window.set_mode('Lógica');self.window.drawer.show();self.window.drawer.setCurrentIndex(1)

    def build_source(self):
        """Inicia construção explícita de um snapshot, sem executar seu Python."""
        if self.job and self.job.isRunning():return
        if not self.check():return
        filename,_=QFileDialog.getSaveFileName(self,'Exportar fonte Python',self.window.project.name+'.zip','Fonte Python (*.zip)')
        if not filename:return
        from makebench.core.project import Project
        project=Project.from_dict(self.window.project.to_dict());source=self.window.source.text
        assets={name:self.window.assets.read(name) for name in project.asset_paths()}
        self.job=BuildJob(project,source,assets.__getitem__,filename,self)
        self.build.setEnabled(False);self.cancel_button.setEnabled(True);self.result.clear();self.open_folder.hide();self.build_log.clear();self.progress_bar.show();self.build_log.show()
        self.job.progress.connect(lambda number,text:(self.progress_bar.setValue(number),self.build_log.appendPlainText(text)))
        self.job.completed.connect(self.completed);self.job.failed.connect(self.failed);self.job.finished.connect(self.build_finished);self.job.start()

    def cancel_build(self):
        """Solicita cancelamento antes da publicação atômica do resultado."""
        if self.job:self.job.cancel.set()

    def completed(self,result):
        """Apresenta o arquivo real, tamanho e hash, sem inventar um sucesso."""
        self.output_path=Path(result['path']);self.result.setText(f"Exportado: {result['path']}\n{result['size']} bytes\nSHA-256: {result['sha256']}");self.open_folder.show()

    def failed(self,message):
        """Mantém o log e a causa visíveis, sem deixar pacote incompleto."""
        self.result.setText(message);self.build_log.appendPlainText(message)

    def build_finished(self):
        """Libera controles quando a thread terminou sua limpeza."""
        self.build.setEnabled(True);self.cancel_button.setEnabled(False)

    def show_result_folder(self):
        """Abre apenas a pasta do artefato construído pelo usuário."""
        if hasattr(self,'output_path'):QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_path.parent)))
