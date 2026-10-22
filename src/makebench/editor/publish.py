"""Jornada de exportação Qt: verificar, construir e conferir o resultado real."""
from pathlib import Path
import threading
from PySide6.QtCore import QThread,QUrl,Signal,Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox,QComboBox,QFileDialog,QHBoxLayout,QLabel,QListWidget,
    QListWidgetItem,QPlainTextEdit,QProgressBar,QPushButton,QVBoxLayout,QWidget)
from makebench.core.packages import FORMATS,preflight,build_package
from makebench.core.environment import build_tools


class BuildJob(QThread):
    """Constrói artefatos em staging fora da UI, sem executar o código do projeto."""
    progress=Signal(int,str);completed=Signal(dict);failed=Signal(str)
    def __init__(self,project,source,read_asset,destination,parent,format='source',recipe_only=False):
        """Guarda snapshot e cancelamento cooperativo da ferramenta de construção."""
        super().__init__(parent);self.project=project;self.source=source;self.read_asset=read_asset;self.destination=destination;self.format=format;self.recipe_only=recipe_only;self.cancel=threading.Event()

    def run(self):
        """Publica apenas pacote ou receita completa; falhas deixam o destino intacto."""
        try:self.completed.emit(build_package(self.project,self.source,self.read_asset,self.destination,self.format,self.progress.emit,self.cancel.is_set,self.recipe_only))
        except Exception as exc:self.failed.emit(str(exc))


class PublishPanel(QWidget):
    """Configurações pertencem à central própria; este modo trata da exportação."""
    def __init__(self,window):
        """Separa resumo, destino, verificação, construção e resultado verificável."""
        super().__init__();self.window=window;self.job=None;layout=QVBoxLayout(self);layout.setContentsMargins(32,24,32,24);layout.setSpacing(18)
        title=QLabel('Publicar aplicativo');title.setProperty('title',True);layout.addWidget(title)
        self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        edit=QPushButton('Editar configurações do aplicativo…');edit.clicked.connect(window.application_settings);layout.addWidget(edit,0,Qt.AlignmentFlag.AlignLeft)
        destination=QWidget();destination.setProperty('card',True);form=QVBoxLayout(destination);form.setContentsMargins(18,18,18,18)
        self.format=QComboBox()
        for key,(name,_,_) in FORMATS.items():self.format.addItem(name,key)
        form.addWidget(QLabel('1  Escolha o destino'));form.addWidget(self.format)
        self.description=QLabel();self.description.setWordWrap(True);self.description.setProperty('muted',True);form.addWidget(self.description)
        self.recipe_only=QCheckBox('Somente gerar receita (sem chamar ferramentas de construção)');form.addWidget(self.recipe_only);layout.addWidget(destination)
        self.format.currentIndexChanged.connect(self.sync)
        self.checks=QListWidget();self.checks.setMinimumHeight(110);self.checks.setMaximumHeight(200);self.checks.itemActivated.connect(self.fix_issue);layout.addWidget(self.checks)
        row=QHBoxLayout();check=QPushButton('2  Verificar');check.clicked.connect(self.check);row.addWidget(check)
        self.build=QPushButton('3  Construir…');self.build.setProperty('primary',True);self.build.clicked.connect(self.build_source);row.addWidget(self.build)
        self.cancel_button=QPushButton('Cancelar construção');self.cancel_button.setEnabled(False);self.cancel_button.clicked.connect(self.cancel_build);row.addWidget(self.cancel_button);row.addStretch();layout.addLayout(row)
        self.progress_bar=QProgressBar();self.progress_bar.setValue(0);layout.addWidget(self.progress_bar);self.progress_bar.hide()
        self.build_log=QPlainTextEdit();self.build_log.setReadOnly(True);self.build_log.setMinimumHeight(110);self.build_log.setMaximumHeight(200);layout.addWidget(self.build_log);self.build_log.hide()
        self.result=QLabel();self.result.setWordWrap(True);self.result.setTextFormat(Qt.TextFormat.PlainText);self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(self.result)
        self.open_folder=QPushButton('Abrir pasta do resultado');self.open_folder.hide();self.open_folder.clicked.connect(self.show_result_folder);layout.addWidget(self.open_folder,0,Qt.AlignmentFlag.AlignLeft);layout.addStretch();self.sync()

    def change(self,key,value):
        """Compatibilidade interna: metadados continuam sendo um comando reversível."""
        if self.window.project.application.get(key)!=value:self.window._edit(lambda:self.window.project.application.update({key:value}))

    def sync(self):
        """Não confunde ferramenta detectada com um artefato construído e validado."""
        app=self.window.project.application;self.summary.setText((app.get('name') or self.window.project.name)+'  ·  '+(app.get('version') or 'Defina a versão')+'  ·  '+app.get('backend','qt').upper())
        key=self.format.currentData();name,tool,_=FORMATS[key];available=build_tools().get(tool) if tool else True
        text='Código, funções, imagens e runtime correspondente ao backend. Requer Python 3.13+ e as bibliotecas indicadas em requirements.txt.' if key=='source' else ('Ferramenta detectada. O resultado será conferido após construir.' if available else 'Gerado, não construído (falta '+tool+'). A saída será uma receita ZIP.')
        if key=='appimage':text+=' Inclui aplicativo e runtime Makebench; Python e GTK/PyGObject ou PySide6 dependem do sistema.'
        if key=='flatpak':text+=' Isolado; programas do host e ações administrativas não são aceitos. O SDK do runtime precisa estar instalado.'
        if key=='deb':text+=' Ubuntu 24.04 fornece Python 3.12: este aplicativo exige Python 3.13+ adicional. A compatibilidade de instalação precisa ser conferida na VM.'
        self.description.setText(text);self.recipe_only.setEnabled(key!='source');self.build.setText('3  Exportar fonte Python…' if key=='source' else '3  Construir '+name+'…')

    def check(self):
        """Lista falhas e avisos com link para o campo correspondente em Configurações."""
        if not self.window._finish_field_edit():return False
        self.checks.clear();issues=preflight(self.window.project,self.window.source.text,self.window.assets.read,self.format.currentData())
        for issue in issues:
            prefix={'error':'✕','warning':'!','success':'✓'}[issue['level']];item=QListWidgetItem(prefix+'  '+issue['message']+('   · Corrigir' if issue.get('field') else ''));item.setData(Qt.ItemDataRole.UserRole,issue['field']);self.checks.addItem(item)
        return not any(issue['level']=='error' for issue in issues)

    def fix_issue(self,item):
        """Abre a central única ou a origem estática do problema na lógica."""
        field=item.data(Qt.ItemDataRole.UserRole)
        if field=='logic':self.window.set_mode('Lógica');self.window.drawer.show();self.window.drawer.setCurrentIndex(1)
        else:self.window.application_settings(field)

    def build_source(self):
        """Constrói o destino selecionado a partir de snapshot estável e explícito."""
        if self.job and self.job.isRunning():return
        if not self.check():return
        key=self.format.currentData();_,tool,suffix=FORMATS[key];recipe=key!='source' and (self.recipe_only.isChecked() or not build_tools().get(tool));suffix='-receita.zip' if recipe else suffix
        filename,_=QFileDialog.getSaveFileName(self,'Exportar '+FORMATS[key][0],self.window.project.name+suffix,'Arquivos (*'+suffix+')')
        if not filename:return
        from makebench.core.project import Project
        project=Project.from_dict(self.window.project.to_dict());assets={name:self.window.assets.read(name) for name in project.asset_paths()}
        self.job=BuildJob(project,self.window.source.text,assets.__getitem__,filename,self,key,recipe)
        self.build.setEnabled(False);self.cancel_button.setEnabled(True);self.result.clear();self.open_folder.hide();self.build_log.clear();self.progress_bar.show();self.build_log.show()
        self.job.progress.connect(lambda number,text:(self.progress_bar.setValue(number),self.build_log.appendPlainText(text)))
        self.job.completed.connect(self.completed);self.job.failed.connect(self.failed);self.job.finished.connect(self.build_finished);self.job.start()

    def cancel_build(self):
        """Solicita interromper ferramentas e limpar staging antes da publicação."""
        if self.job:self.job.cancel.set()

    def completed(self,result):
        """Só mostra sucesso para arquivo existente, com tamanho, estado e SHA-256."""
        self.output_path=Path(result['path']);self.result.setText(f"{result.get('status','Exportado')}\n{result['path']}\n{result['size']} bytes\nSHA-256: {result['sha256']}");self.open_folder.show()

    def failed(self,message):
        """Causa fica visível e nenhum pacote parcial é publicado."""
        self.result.setText(message);self.build_log.appendPlainText(message)

    def build_finished(self):
        """Libera as ações somente após a limpeza da thread de construção."""
        self.build.setEnabled(True);self.cancel_button.setEnabled(False)

    def show_result_folder(self):
        """Abre a pasta do artefato real, sem executar o aplicativo exportado."""
        if hasattr(self,'output_path'):QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_path.parent)))
