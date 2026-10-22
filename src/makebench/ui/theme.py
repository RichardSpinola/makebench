"""Tokens derivados do desktop e estilo discreto inspirado na GNOME HIG."""
from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

ACCENTS = {'system':None,'blue':'#3584e4','green':'#26a269','yellow':'#e5a50a',
           'red':'#c01c28','purple':'#9141ac','pink':'#d56199','gray':'#77767b'}
PALETTES = {
    'light': dict(canvas='#ebebeb', panel='#fafafa', raised='#ffffff', header='#ebebeb', sidebar='#ebebeb',
        border='#d9d9d9', control='#858585', text='#2e3436', muted='#5e5c64',
        accent='#2874ce', fill='#2874ce', on_accent='#ffffff', success='#187346',
        warning='#805b00', error='#c01c28', info='#2265b3', guide='#9141ac', hover='#e5e5e5', selection='#dfebfa'),
    'dark': dict(canvas='#1e1e1e', panel='#242424', raised='#363636', header='#303030', sidebar='#2e2e2e',
        border='#3d3d3d', control='#858585', text='#ffffff', muted='#c0bfbc',
        accent='#78aeef', fill='#78aeef', on_accent='#161616', success='#8ff0a4',
        warning='#f8e45c', error='#ff7b63', info='#78aeef', guide='#dc8add', hover='#414141', selection='#374453'),
}


def contrast(first, second):
    """Razão WCAG de duas cores sRGB para texto e limites interativos."""
    def luminance(value):
        """Lineariza os canais sRGB antes da combinação por luminância."""
        c=QColor(value);channels=[c.redF(),c.greenF(),c.blueF()]
        return sum((v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)*w for v,w in zip(channels,(.2126,.7152,.0722)))
    a,b=sorted((luminance(first),luminance(second)));return (b+.05)/(a+.05)


def blend(first, second, amount):
    """Mistura cores sem transparência dependente do compositor."""
    a,b=QColor(first),QColor(second)
    return QColor(*[round(x*(1-amount)+y*amount) for x,y in zip(a.getRgb()[:3],b.getRgb()[:3])]).name()


def legible(color, backgrounds, ratio):
    """Ajusta luminosidade minimamente até atingir o contraste requerido."""
    if all(contrast(color,b)>=ratio for b in backgrounds):return QColor(color).name()
    target=max(('#000000','#ffffff'),key=lambda c:min(contrast(c,b) for b in backgrounds))
    for step in range(1,101):
        candidate=blend(color,target,step/100)
        if all(contrast(candidate,b)>=ratio for b in backgrounds):return candidate
    return target


def derive_tokens(palette, dark=False, accent='system', system_surfaces=True):
    """Produz tokens testáveis sem alterar QPalette do desktop ou o documento."""
    t=dict(PALETTES['dark' if dark else 'light'],dark=dark)
    if system_surfaces:
        window=palette.color(QPalette.ColorRole.Window).name();text=palette.color(QPalette.ColorRole.WindowText).name()
        is_dark=QColor(window).lightnessF()<.45
        if is_dark==dark and contrast(text,window)>=4.5:
            base=palette.color(QPalette.ColorRole.Base).name()
            t.update(panel=window,text=text,raised=base if contrast(text,base)>=4.5 else t['raised'])
    raw=ACCENTS.get(accent)
    if raw is None:
        for role in (getattr(QPalette.ColorRole,'Accent',QPalette.ColorRole.Highlight),QPalette.ColorRole.Highlight):
            value=palette.color(role)
            if value.isValid() and contrast(value.name(),t['panel'])>1.1:
                raw=value.name();break
    raw=raw or ACCENTS['blue'];t['system_accent']=raw
    t['accent']=legible(raw,[t['panel'],t['raised']],3)
    t['accent_adjusted']=QColor(raw).name()!=t['accent']
    t['fill']=t['accent'];t['on_accent']=max(('#ffffff','#000000'),key=lambda c:contrast(c,t['fill']))
    for key in ('muted','success','warning','error','info','guide'):
        t[key]=legible(t['accent'] if key=='info' else t[key],[t['panel'],t['raised'],t['canvas']],4.5)
    t['control']=legible(t['control'],[t['panel'],t['raised']],3)
    t['hover']=blend(t['panel'],t['text'],.07)
    t['selection']=blend(t['panel'],t['accent'],.15)
    t['pressed']=blend(t['accent'],t['on_accent'],.15)
    return t


class ThemeManager(QObject):
    """Segue esquema e paleta do desktop e persiste escolhas do editor."""
    changed=Signal(dict)

    def __init__(self,app):
        """Captura a paleta antes de aplicar estilo; não a substitui globalmente."""
        super().__init__(app);self.app=app;self.system_palette=QPalette(app.palette());self._applying=False
        self.settings=QSettings('Makebench','Makebench');self.base_font=QFont(app.font())
        value=self.settings.value('v1/appearance/theme',self.settings.value('appearance/theme','system'))
        self.mode=value if value in {'system','light','dark'} else 'system'
        try:self.scale=int(self.settings.value('v1/appearance/scale',self.settings.value('appearance/scale',100)))
        except (TypeError,ValueError):self.scale=100
        if self.scale not in {90,100,115,130}:self.scale=100
        self.accent=self.settings.value('v1/appearance/accent','system');self.reduce_motion=self.settings.value('v1/appearance/reduce_motion',False,type=bool)
        self._applying=True;app.setStyle(QStyleFactory.create('Fusion'));self._applying=False
        app.styleHints().colorSchemeChanged.connect(lambda _:self.apply())
        app.paletteChanged.connect(self.palette_changed);self.apply()

    def palette_changed(self,palette):
        """Atualiza cores vindas do sistema sem confundir QSS com nova paleta."""
        if self._applying:return
        self.system_palette=QPalette(palette);self.apply()

    def set_mode(self,mode):
        """Aplica imediatamente uma escolha validada de esquema."""
        if mode not in {'system','light','dark'}:raise ValueError('Tema desconhecido')
        self.mode=mode;self.settings.setValue('v1/appearance/theme',mode);self.settings.setValue('appearance/theme',mode);self.apply()

    def set_accent(self,value):
        """Escolhe destaque local ou volta a acompanhar o desktop."""
        self.accent=value if value in ACCENTS else 'system';self.settings.setValue('v1/appearance/accent',self.accent);self.apply()

    def apply(self):
        """Estiliza vistas via tokens mantendo intacta a paleta global do sistema."""
        if self._applying:return
        self._applying=True
        dark=self.mode=='dark' or self.mode=='system' and (self.app.styleHints().colorScheme()==Qt.ColorScheme.Dark or self.app.styleHints().colorScheme()==Qt.ColorScheme.Unknown and self.system_palette.color(QPalette.ColorRole.Window).lightnessF()<.45)
        self.tokens=t=derive_tokens(self.system_palette,dark,self.accent,self.mode=='system')
        for effect in (Qt.UIEffect.UI_AnimateMenu,Qt.UIEffect.UI_FadeMenu,Qt.UIEffect.UI_AnimateCombo,Qt.UIEffect.UI_AnimateTooltip,Qt.UIEffect.UI_FadeTooltip):self.app.setEffectEnabled(effect,not self.reduce_motion)
        font=QFont(self.base_font);font.setPointSizeF(max(8,font.pointSizeF())*self.scale/100);self.app.setFont(font)
        self.app.setStyleSheet(f'''
          QWidget {{ color:{t['text']}; background:{t['panel']}; }}
          QMainWindow,QDialog,QWidget#home {{ background:{t['panel']}; }}
          QMenu,QToolTip {{ background:{t['raised']}; color:{t['text']}; border:1px solid {t['border']}; padding:6px; }}
          QMenu::item {{ padding:7px 18px; border-radius:6px; }}
          QMenu::item:selected {{ background:{t['selection']}; }}
          QMenuBar {{ background:{t['header']}; }}
          QToolBar {{ border:0; spacing:6px; padding:6px; background:{t['header']}; }}
          QToolBar#workspace_toolbar {{ min-height:34px; }}
          QToolButton,QPushButton {{ min-height:26px; padding:3px 10px; border:1px solid transparent; border-radius:6px; background:transparent; }}
          QToolButton:hover,QPushButton:hover {{ background:{t['hover']}; }}
          QToolButton:pressed,QPushButton:pressed {{ background:{t['selection']}; }}
          QToolButton:checked {{ background:{t['selection']}; color:{t['text']}; }}
          QPushButton[primary="true"],QToolButton[primary="true"] {{ background:{t['fill']}; color:{t['on_accent']}; }}
          QPushButton[primary="true"]:pressed {{ background:{t['pressed']}; }}
          QPushButton[destructive="true"] {{ color:{t['error']}; }}
          QToolButton:focus,QPushButton:focus,QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QCheckBox:focus {{ border:2px solid {t['accent']}; }}
          QLineEdit,QComboBox,QSpinBox {{ background:{t['raised']}; min-height:26px; padding:3px 8px; border:1px solid {t['control']}; border-radius:6px; selection-background-color:{t['fill']}; selection-color:{t['on_accent']}; }}
          QTreeWidget,QListWidget,QPlainTextEdit,QTextEdit {{ background:{t['panel']}; border:0; selection-background-color:{t['selection']}; selection-color:{t['text']}; }}
          QTreeWidget::item,QListWidget::item {{ min-height:34px; padding:3px; border-radius:6px; }}
          QTreeWidget::item:selected,QListWidget::item:selected {{ background:{t['selection']}; color:{t['text']}; }}
          QListWidget#recent_list::item {{ min-height:50px; }}
          QScrollArea,QTabWidget::pane {{ border:0; background:transparent; }}
          QSplitter::handle {{ background:{t['border']}; width:1px; height:1px; }}
          QLabel[muted="true"] {{ color:{t['muted']}; }}
          QLabel[section="true"] {{ font-weight:600; padding-top:12px; padding-bottom:6px; }}
          QLabel[title="true"] {{ font-size:24px; font-weight:700; }}
          QWidget#pasteboard {{ background:{t['canvas']}; }}
          QWidget[card="true"],QFrame[card="true"] {{ background:{t['raised']}; border:1px solid {t['border']}; border-radius:12px; }}
          QWidget[card="true"] QWidget {{ border:0; background:transparent; }}
          QWidget#app_window_titlebar {{ background:{t['header']}; border-radius:12px; }}
          QTabBar::tab {{ padding:8px 12px; margin:2px; border-radius:6px; background:transparent; }}
          QTabBar::tab:selected {{ background:{t['selection']}; }}
          QTabBar::tab:focus,QTreeWidget:focus,QListWidget:focus,QPlainTextEdit:focus {{ border:1px solid {t['accent']}; }}
          QGroupBox {{ border:0; margin-top:18px; padding-top:12px; }}
          QGroupBox::title {{ subcontrol-origin:margin; left:0; font-weight:600; }}
          QWidget:disabled {{ color:{t['muted']}; }}
        ''')
        self._applying=False;self.changed.emit(t)


def manager():
    """Serviço único também disponível em testes diretos dos widgets."""
    app=QApplication.instance()
    if not hasattr(app,'makebench_theme'):app.makebench_theme=ThemeManager(app)
    return app.makebench_theme


def icon(name):
    """Prefere símbolos do sistema e usa vetores próprios como reserva recolorida."""
    aliases={'new':'document-new-symbolic','open':'document-open-symbolic','save':'document-save-symbolic','undo':'edit-undo-symbolic','redo':'edit-redo-symbolic','run':'media-playback-start-symbolic','stop':'media-playback-stop-symbolic','home':'go-home-symbolic','search':'edit-find-symbolic','add':'list-add-symbolic','remove':'list-remove-symbolic'}
    themed=QIcon.fromTheme(aliases.get(name,name))
    if not themed.isNull():
        from PySide6.QtGui import QPainter,QPixmap
        color=QColor(manager().tokens['text']);result=QIcon()
        for size in (16,20,24,32,48,64):
            pix=themed.pixmap(size,size);painter=QPainter(pix);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn);painter.fillRect(pix.rect(),color);painter.end();result.addPixmap(pix)
        return result
    from .icons import vector_icon
    return vector_icon(name)
