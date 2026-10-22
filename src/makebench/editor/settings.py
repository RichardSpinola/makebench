"""Centrais de configuração Qt: editor global e aplicativo do projeto."""
import json
from pathlib import Path
from PySide6.QtCore import Qt,QSettings,QUrl
from PySide6.QtGui import QDesktopServices,QFont,QFontDatabase
from PySide6.QtWidgets import (QApplication,QCheckBox,QComboBox,QDialog,QFileDialog,QFormLayout,QHBoxLayout,
    QLabel,QLineEdit,QListWidget,QPlainTextEdit,QPushButton,QScrollArea,QSpinBox,QStackedWidget,QVBoxLayout,QWidget)
from makebench.core.environment import gtk_support,build_tools
from makebench.core.diagnostics import environment_report
from makebench.core.exporter import effects
from makebench import __version__
from .theme import manager,icon

DEFAULTS={'appearance/theme':'system','appearance/accent':'system','appearance/scale':100,'appearance/reduce_motion':False,
    'projects/folder':str(Path.home()/'Makebench'/'Projetos'),'projects/trust':True,'projects/backend':'gtk','projects/startup':True,
    'editor/code_font':'Monospace','editor/code_size':11,'editor/wrap':False,'editor/recovery':30,'editor/grid':True,
    'test/clear':True,'test/confirm_restart':True,'test/duration':True}
CHOICES={'appearance/theme':['system','light','dark'],'appearance/accent':['system'],
    'appearance/scale':[90,100,115,130],'projects/backend':['gtk','qt'],'editor/recovery':[0,15,30,60]}


def preference(key,settings=None):
    """Valores inválidos são ignorados; booleanos QSettings têm conversão explícita."""
    settings=settings or QSettings('Makebench','Makebench');default=DEFAULTS[key]
    value=settings.value('v1/'+key,default)
    if isinstance(default,bool):return value if isinstance(value,bool) else str(value).lower()=='true' if str(value).lower() in {'true','false'} else default
    if isinstance(default,int):
        try:value=int(value)
        except (ValueError,TypeError):return default
    if type(value) is not type(default) or key in CHOICES and value not in CHOICES[key]:return default
    if isinstance(value,str) and ('\0' in value or len(value)>4096):return default
    if key=='editor/code_size' and not 8<=value<=32:return default
    return value


class SettingsShell(QDialog):
    """Janela com navegação, busca de opções e grupos de cartões Qt."""
    def __init__(self,parent,title):
        """A busca filtra linhas em todas as páginas e mantém foco de teclado."""
        super().__init__(parent);self.setWindowTitle(title);self.resize(940,680);self.setMinimumSize(720,480)
        outer=QVBoxLayout(self);outer.setContentsMargins(10,10,10,10);outer.setSpacing(8)
        self.search=QLineEdit();self.search.setPlaceholderText('Buscar configurações…');self.search.setClearButtonEnabled(True);outer.addWidget(self.search)
        body=QHBoxLayout();self.sections=QListWidget();self.sections.setMaximumWidth(200);self.sections.setMinimumWidth(170);body.addWidget(self.sections)
        self.pages=QStackedWidget();body.addWidget(self.pages,1);outer.addLayout(body,1);self.sections.currentRowChanged.connect(self.pages.setCurrentIndex);self.search.textChanged.connect(self.filter_rows)
        close=QPushButton('Fechar');close.clicked.connect(self.close);outer.addWidget(close,0,Qt.AlignmentFlag.AlignRight)
        self.rows=[];self.page_layouts=[]

    def add_page(self,title):
        """Página rolável funciona também com fontes ampliadas e janela menor."""
        self.sections.addItem(title);page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(8,4,8,8);layout.setSpacing(10);layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);self.pages.addWidget(scroll);self.page_layouts.append(layout)
        if self.sections.count()==1:self.sections.setCurrentRow(0)
        return layout

    def group(self,page,title,description=''):
        """Título fica fora do cartão e a descrição explica a consequência da opção."""
        heading=QLabel(title);heading.setProperty('section',True);page.addWidget(heading)
        if description:
            label=QLabel(description);label.setWordWrap(True);label.setProperty('muted',True);page.addWidget(label)
        from PySide6.QtWidgets import QFrame
        card=QFrame();card.setFrameShape(QFrame.Shape.StyledPanel);layout=QVBoxLayout(card);layout.setContentsMargins(10,10,10,10);layout.setSpacing(8);page.addWidget(card);return layout

    def row(self,group,label,control,description=''):
        """Uma linha de opção tem título/descrição e controle alinhado à direita."""
        widget=QWidget();layout=QHBoxLayout(widget);layout.setContentsMargins(0,0,0,0);text=QVBoxLayout();title=QLabel(label);title.setTextFormat(Qt.TextFormat.PlainText);text.addWidget(title)
        if description:
            subtitle=QLabel(description);subtitle.setTextFormat(Qt.TextFormat.PlainText);subtitle.setWordWrap(True);subtitle.setProperty('muted',True);text.addWidget(subtitle)
        layout.addLayout(text,1);layout.addWidget(control);group.addWidget(widget);self.rows.append((widget,(label+' '+description).casefold(),self.pages.count()-1));control.setAccessibleName(label);return control

    def filter_rows(self,text):
        """Busca muda para a primeira página com resultados sem alterar valores."""
        query=text.casefold();matches=[]
        for widget,label,page in self.rows:
            visible=query in label;widget.setVisible(visible)
            if visible:matches.append(page)
        if query and matches:self.sections.setCurrentRow(matches[0])


class EditorPreferences(SettingsShell):
    """Preferências imediatas em QSettings, independentes do histórico dos projetos."""
    def __init__(self,window):
        """Monta sete páginas e mantém cada opção com uma única fonte de verdade."""
        super().__init__(window,'Preferências do Makebench');self.window=window;self.settings=window.settings
        self.controls={}
        for prefix,title in [('appearance','Aparência'),('projects','Projetos'),('editor','Editor'),('test','Teste')]:
            page=self.add_page(title);group=self.group(page,title,'As alterações são aplicadas imediatamente.');self.populate(group,prefix)
            if prefix=='projects':
                clear=QPushButton('Limpar projetos recentes');clear.clicked.connect(lambda:(self.settings.remove('projects/recent'),window.refresh_recents()));group.addWidget(clear)
            reset=QPushButton('Restaurar padrões desta página');reset.clicked.connect(lambda _,prefix=prefix:self.reset_page(prefix));page.addWidget(reset,0,Qt.AlignmentFlag.AlignRight)
        page=self.add_page('Atalhos');group=self.group(page,'Comandos','Atalhos somente leitura nesta versão. A busca também encontra os nomes dos comandos.')
        from .commands import register
        register(window)
        for action in window.commands:
            shortcut=QLabel(action.shortcut().toString() or 'Sem atalho');self.row(group,action.text().replace('&','').replace('…',''),shortcut)
        page=self.add_page('Ambiente');group=self.group(page,'Diagnóstico do ambiente');self.report=QPlainTextEdit(diagnostic(window));self.report.setReadOnly(True);self.report.setMinimumHeight(300);group.addWidget(self.report)
        copy=QPushButton('Copiar relatório');copy.clicked.connect(lambda:QApplication.clipboard().setText(self.report.toPlainText()));group.addWidget(copy)
        page=self.add_page('Sobre');group=self.group(page,'Makebench '+__version__)
        label=QLabel('Editor visual de aplicativos Linux. Sem conta, servidor ou IA em execução.\n\nPySide6/Qt: LGPL/GPL/comercial. Blockly 13.4.0: Apache-2.0. Backend GTK opcional: GTK4 e PyGObject (LGPL), libadwaita opcional (LGPL). Símbolos de reserva são vetores próprios.\n\nA licença do Makebench ainda precisa ser definida pelo autor.');label.setWordWrap(True);group.addWidget(label)
        documentation=QPushButton('Abrir checklist de validação');documentation.clicked.connect(lambda:open_checklist(window));group.addWidget(documentation)

    def populate(self,group,prefix):
        """Cria controles vinculados a chaves versionadas e opções validadas."""
        labels={'appearance/theme':'Tema','appearance/accent':'Cor de destaque','appearance/scale':'Tamanho do texto','appearance/reduce_motion':'Reduzir movimento','projects/folder':'Pasta dos novos projetos','projects/trust':'Avisar sobre projeto não confiável','projects/backend':'Backend padrão','projects/startup':'Mostrar a janela inicial ao abrir','editor/code_font':'Fonte do código','editor/code_size':'Tamanho do código','editor/wrap':'Quebrar linhas do código','editor/recovery':'Recuperação automática','editor/grid':'Encaixar na grade por padrão','test/clear':'Limpar saída ao iniciar','test/confirm_restart':'Confirmar reinício durante uma tarefa','test/duration':'Mostrar tempo de execução'}
        option_labels={'appearance/theme':['Sistema','Claro','Escuro'],'appearance/accent':['Do sistema'],'appearance/scale':['90%','100%','115%','130%'],'projects/backend':['GTK','Qt'],'editor/recovery':['Desligada','15 segundos','30 segundos','60 segundos']}
        for key,label in labels.items():
            if not key.startswith(prefix+'/'):continue
            value=preference(key,self.settings)
            if key in CHOICES:
                field=QComboBox()
                for text,item in zip(option_labels[key],CHOICES[key]):field.addItem(text,item)
                field.setCurrentIndex(field.findData(value));field.currentIndexChanged.connect(lambda _,key=key,field=field:self.changed(key,field.currentData()))
            elif isinstance(value,bool):field=QCheckBox();field.setChecked(value);field.toggled.connect(lambda value,key=key:self.changed(key,value))
            elif isinstance(value,int):field=QSpinBox();field.setRange(8,32);field.setValue(value);field.valueChanged.connect(lambda value,key=key:self.changed(key,value))
            else:field=QLineEdit(value);field.setMinimumWidth(180);field.textChanged.connect(lambda value,key=key:self.changed(key,value))
            self.controls[key]=field;self.row(group,label,field,'Recuo fixo de 4 espaços.' if key=='editor/code_font' else '')

    def changed(self,key,value):
        """Persiste somente preferências, aplica sem reiniciar nem marcar o projeto."""
        self.settings.setValue('v1/'+key,value);apply_preferences(self.window)

    def reset_page(self,prefix):
        """Restaura só uma página e atualiza seus controles sem recursão de sinais."""
        for key,field in self.controls.items():
            if not key.startswith(prefix+'/'):continue
            self.settings.remove('v1/'+key);value=preference(key,self.settings);field.blockSignals(True)
            if isinstance(field,QComboBox):field.setCurrentIndex(field.findData(value))
            elif isinstance(field,QCheckBox):field.setChecked(value)
            elif isinstance(field,QSpinBox):field.setValue(value)
            else:field.setText(value)
            field.blockSignals(False)
        apply_preferences(self.window)


def apply_preferences(window):
    """Aplica tema, código, recuperação e comportamento aos widgets existentes."""
    theme=manager();theme.mode=preference('appearance/theme');theme.accent='system';theme.scale=preference('appearance/scale');theme.reduce_motion=preference('appearance/reduce_motion');theme.apply()
    font=QFont(preference('editor/code_font'),preference('editor/code_size'));font.setStyleHint(QFont.StyleHint.Monospace)
    for editor in (window.source_editor,window.generated_editor,window.logic.code,window.script_editor):
        editor.setFont(font);editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(' ')*4);editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if preference('editor/wrap') else QPlainTextEdit.LineWrapMode.NoWrap)
    interval=preference('editor/recovery')
    if interval:window.recovery_timer.setInterval(interval*1000);window.recovery_timer.start()
    else:window.recovery_timer.stop()
    window.snap_check.setChecked(preference('editor/grid'));window.refresh_trust_banner()


def diagnostic(window=None):
    """Coleta estado Qt real sem executar ferramentas nem código do projeto."""
    app=QApplication.instance();theme=manager();screen=window.screen() if window else app.primaryScreen()
    return environment_report({'Qt':__import__('PySide6.QtCore',fromlist=['qVersion']).qVersion(),'Plugin de plataforma':app.platformName(),'Tema':'Escuro' if theme.tokens['dark'] else 'Claro','Destaque do sistema':theme.tokens.get('system_accent','Indisponível'),'Destaque ajustado para contraste':str(theme.tokens.get('accent_adjusted',False)),'Escala da tela':str(screen.devicePixelRatio()) if screen else 'Indisponível'})


def show_diagnostic(window):
    """Janela própria oferece relatório completo e ação de copiar."""
    dialog=QDialog(window);dialog.setWindowTitle('Diagnóstico do ambiente');dialog.resize(760,580);layout=QVBoxLayout(dialog);report=QPlainTextEdit(diagnostic(window));report.setReadOnly(True);layout.addWidget(report)
    copy=QPushButton('Copiar relatório');copy.clicked.connect(lambda:QApplication.clipboard().setText(report.toPlainText()));layout.addWidget(copy);close=QPushButton('Fechar');close.clicked.connect(dialog.close);layout.addWidget(close);dialog.show();window.diagnostic_dialog=dialog;return dialog


def open_checklist(window):
    """Abre o arquivo local, que acompanha o fonte e o pacote do editor."""
    path=Path(__file__).resolve().parents[3]/'docs'/'validacao-desktop.md'
    if path.exists():QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    else:window._show_error('Consulte docs/validacao-desktop.md na pasta do Makebench.')


class ApplicationSettings(SettingsShell):
    """Configuração por projeto, com alterações reversíveis e busca de campos."""
    def __init__(self,window):
        """Identidade, ícone, backend, dependências, permissões, janelas, dados e destinos."""
        super().__init__(window,'Configurações do aplicativo');self.window=window;self.fields={};app=window.project.application
        page=self.add_page('Identidade');group=self.group(page,'Identidade','Estas informações acompanham o aplicativo exportado.')
        for key,label in [('name','Nome público'),('id','Identificador'),('version','Versão'),('description','Descrição'),('author','Autor'),('license','Licença'),('category','Categorias')]:
            field=QLineEdit(str(app.get(key,'')));field.setMinimumWidth(230);field.editingFinished.connect(lambda key=key,field=field:self.change(key,field.text()));self.row(group,label,field);self.fields[key]=field
        page=self.add_page('Ícone');group=self.group(page,'Ícone do aplicativo','PNG com pelo menos 256 pixels ou SVG.');self.icon_preview=QLabel();self.icon_preview.setFixedSize(128,128);group.addWidget(self.icon_preview)
        choose=QPushButton('Escolher ícone…');choose.clicked.connect(self.choose_icon);group.addWidget(choose);self.update_icon()
        page=self.add_page('Aparência');group=self.group(page,'Backend do aplicativo','O editor é Qt. Esta escolha define os controles do aplicativo que você está criando.')
        backend=QComboBox();backend.addItem('GTK4 / Adwaita','gtk');backend.addItem('Qt / PySide6','qt');backend.setCurrentIndex(backend.findData(app.get('backend','qt')));backend.currentIndexChanged.connect(lambda _:self.change('backend',backend.currentData()));self.row(group,'Aparência e execução',backend)
        if not gtk_support()['gtk4']:
            notice=QLabel('GTK4 ausente neste Python. O teste GTK informa os pacotes necessários, sem instalar automaticamente.');notice.setWordWrap(True);group.addWidget(notice)
        page=self.add_page('Dependências');group=self.group(page,'Dependências','Python mínimo 3.13. GTK exige PyGObject/GTK4; Qt exige PySide6 6.11.2.')
        packages=QLineEdit('; '.join(app.get('packages',[])));packages.editingFinished.connect(lambda:self.change('packages',[v.strip() for v in packages.text().split(';') if v.strip()]));self.row(group,'Pacotes Python',packages,'Separe por ponto e vírgula.');self.fields['packages']=packages
        programs,admin=effects(window.project);label=QLabel('Programas detectados: '+(', '.join(programs) or 'nenhum')+'. Funções próprias podem exigir outros programas.');label.setWordWrap(True);group.addWidget(label)
        page=self.add_page('Permissões');group=self.group(page,'Acesso ao sistema')
        text=QLabel('Fonte Python, DEB, RPM e AppImage executam com as permissões do usuário. O teste não é uma sandbox.\n\n'+('Há ações administrativas declaradas: Polkit/pkexec e agente do sistema são necessários. O Makebench não pede senhas.' if admin else 'Nenhuma ação administrativa declarada nos blocos.')+'\n\nFlatpak isolado bloqueia programas do host e administração. Dependências adicionais devem existir dentro do pacote.');text.setWordWrap(True);group.addWidget(text)
        page=self.add_page('Janelas');group=self.group(page,'Janelas do aplicativo');initial=QComboBox()
        for root in window.project.roots:initial.addItem(root.properties.get('title','Interface'),root.id)
        initial.setCurrentIndex(initial.findData(window.project.entry_window or window.project.root.id));initial.currentIndexChanged.connect(lambda _:window._edit(lambda:setattr(window.project,'entry_window',initial.currentData())));self.row(group,'Janela inicial',initial)
        for root in window.project.roots:
            field=QLineEdit(root.properties.get('title','Interface'));field.editingFinished.connect(lambda identifier=root.id,field=field:window._edit(lambda:window.project.find(identifier).properties.update(title=field.text())));self.row(group,'Título da interface',field)
            for key,label,default in [('width','Largura',640),('height','Altura',480)]:
                spin=QSpinBox();spin.setRange(100,20000);spin.setValue(root.properties.get(key,default));spin.editingFinished.connect(lambda identifier=root.id,key=key,spin=spin:window._edit(lambda:window.project.find(identifier).properties.update({key:spin.value()})));self.row(group,label,spin)
            choose=QPushButton('Escolher ícone desta janela…');choose.clicked.connect(lambda _,identifier=root.id:self.choose_window_icon(identifier));group.addWidget(choose)
        page=self.add_page('Dados');group=self.group(page,'Variáveis e valores iniciais');add=QPushButton('Adicionar variável…');add.clicked.connect(window.variable_dialog);group.addWidget(add)
        for index,variable in enumerate(window.project.variables):
            edit=QPushButton('Editar…');edit.clicked.connect(lambda _,index=index:window.variable_dialog(index=index));self.row(group,variable['name'],edit,repr(variable.get('initial')))
        page=self.add_page('Destinos');group=self.group(page,'Exportadores','O resultado só é marcado como construído depois de passar pela ferramenta e pela verificação.')
        for name,tool in [('Fonte Python',None),('DEB','dpkg-deb'),('AppImage','appimagetool'),('Flatpak','flatpak-builder'),('RPM','rpmbuild')]:
            status=QLabel('Construção pela tela Publicar' if not tool or build_tools().get(tool) else 'Gerar receita · falta '+tool);self.row(group,name,status)
        self.finished.connect(lambda _:window._refresh())

    def change(self,key,value):
        """Grava apenas o campo alterado, sem regenerar nem executar fontes próprias."""
        if self.window.project.application.get(key)!=value:self.window._edit(lambda:self.window.project.application.update({key:value}))

    def choose_icon(self):
        """Importa recurso no cache portátil do projeto e mostra sua aparência real."""
        path,_=QFileDialog.getOpenFileName(self,'Ícone do aplicativo','','Ícones (*.png *.svg)')
        if path:
            try:self.change('icon',self.window.assets.import_image(Path(path)));self.update_icon()
            except Exception as exc:self.window._show_error(str(exc))

    def choose_window_icon(self,identifier):
        """Cada janela pode ter um ícone próprio sem depender do caminho original."""
        path,_=QFileDialog.getOpenFileName(self,'Ícone da janela','','Ícones (*.png *.svg)')
        if path:
            try:
                name=self.window.assets.import_image(Path(path));self.window._edit(lambda:self.window.project.find(identifier).properties.update(icon=name))
            except Exception as exc:self.window._show_error(str(exc))

    def update_icon(self):
        """A imagem usa o mesmo recurso que acompanhará o aplicativo exportado."""
        from PySide6.QtGui import QPixmap
        name=self.window.project.application.get('icon')
        if name:
            try:
                pixmap=QPixmap();pixmap.loadFromData(self.window.assets.read(name));self.icon_preview.setPixmap(pixmap.scaled(128,128,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            except Exception:self.icon_preview.clear()
