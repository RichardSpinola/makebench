"""Tokens semânticos e aparência compartilhada, sem alterar o documento do app."""
from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPalette, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyleFactory

PALETTES = {
    'dark': dict(canvas='#14161a', panel='#1c1f24', raised='#252a31', hover='#2c323a',
        border='#353b44', control='#74808f', text='#e8eaed', muted='#a5adb7',
        accent='#e58a4c', fill='#e58a4c', on_accent='#14161a', success='#4cb782',
        warning='#e0a93b', error='#ef6b63', info='#79b1ed', guide='#df81d5'),
    'light': dict(canvas='#dfe2e6', panel='#f3f4f6', raised='#ffffff', hover='#e7eaee',
        border='#c9ced5', control='#77818d', text='#1a1d21', muted='#565f6b',
        accent='#a34916', fill='#a34916', on_accent='#ffffff', success='#17683e',
        warning='#825300', error='#b23226', info='#1f5fa8', guide='#953b8d'),
}


def contrast(first, second):
    """Retorna razão WCAG entre duas cores sRGB hexadecimais."""
    def luminance(value):
        """Converte sRGB em luminância relativa para calcular contraste."""
        rgb = [int(value[n:n+2], 16) / 255 for n in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
        return sum(c * w for c, w in zip(linear, (.2126, .7152, .0722)))
    a, b = sorted((luminance(first), luminance(second)))
    return (b + .05) / (a + .05)


class ThemeManager(QObject):
    """Aplica Sistema/Claro/Escuro sem reiniciar; avisa vistas web existentes."""
    changed = Signal(dict)

    def __init__(self, app):
        """Lê preferências do editor e acompanha mudanças do sistema."""
        super().__init__(app)
        self.app = app
        self.settings = QSettings('Makebench', 'Makebench')
        self.mode = self.settings.value('appearance/theme', 'system')
        self.scale = int(self.settings.value('appearance/scale', 100))
        self.reduce_motion=self.settings.value('appearance/reduce_motion',False,type=bool)
        self.base_font = app.font()
        app.styleHints().colorSchemeChanged.connect(lambda _: self.apply())
        self.apply()

    def set_mode(self, mode):
        """Persiste uma escolha válida e atualiza os controles existentes."""
        if mode not in {'system', 'light', 'dark'}:
            raise ValueError('Tema desconhecido')
        self.mode = mode
        self.settings.setValue('appearance/theme', mode)
        self.apply()

    def apply(self):
        """Gera QPalette/QSS exclusivamente a partir dos tokens semânticos."""
        dark = self.mode == 'dark' or (self.mode == 'system' and self.app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
        self.tokens = t = dict(PALETTES['dark' if dark else 'light'], dark=dark)
        self.app.setStyle(QStyleFactory.create('Fusion'))
        for effect in (Qt.UIEffect.UI_AnimateMenu,Qt.UIEffect.UI_FadeMenu,Qt.UIEffect.UI_AnimateCombo,Qt.UIEffect.UI_AnimateTooltip,Qt.UIEffect.UI_FadeTooltip):
            self.app.setEffectEnabled(effect,not self.reduce_motion)
        palette = QPalette()
        for role, key in {
            'Window':'panel', 'WindowText':'text', 'Base':'raised', 'AlternateBase':'panel',
            'Text':'text', 'Button':'raised', 'ButtonText':'text', 'Highlight':'fill',
            'HighlightedText':'on_accent', 'ToolTipBase':'raised', 'ToolTipText':'text',
            'PlaceholderText':'muted', 'Link':'accent', 'Light':'raised', 'Mid':'border', 'Dark':'border',
        }.items():
            palette.setColor(getattr(QPalette.ColorRole, role), QColor(t[key]))
        for role in (QPalette.ColorRole.Text,QPalette.ColorRole.WindowText,QPalette.ColorRole.ButtonText):
            palette.setColor(QPalette.ColorGroup.Disabled,role,QColor(t['muted']))
        self.app.setPalette(palette)
        font = QFont(self.base_font)
        font.setPointSizeF(max(8, font.pointSizeF()) * self.scale / 100)
        self.app.setFont(font)
        self.app.setStyleSheet(f'''
            QMainWindow, QDialog {{ background: {t['panel']}; }}
            QToolBar {{ border: 0; spacing: 4px; padding: 6px; }}
            QToolButton, QPushButton {{ min-height: 26px; padding: 2px 8px; border: 1px solid {t['control']}; border-radius: 4px; }}
            QToolButton:disabled, QPushButton:disabled {{ color: {t['muted']}; border-color: {t['border']}; }}
            QToolButton:hover, QPushButton:hover {{ background: {t['hover']}; }}
            QToolButton:checked, QPushButton[primary="true"] {{ background: {t['fill']}; color: {t['on_accent']}; }}
            QToolButton:focus, QPushButton:focus, QLineEdit:focus, QComboBox:focus {{ border: 2px solid {t['accent']}; }}
            QLineEdit, QComboBox, QSpinBox {{ min-height: 26px; padding: 0px 5px; border: 1px solid {t['control']}; border-radius: 4px; }}
            QTreeWidget, QListWidget, QPlainTextEdit, QScrollArea {{ border: 0; }}
            QTreeWidget::item, QListWidget::item {{ min-height: 26px; }}
            QSplitter::handle {{ background: {t['border']}; width: 3px; height: 3px; }}
            QLabel[muted="true"] {{ color: {t['muted']}; }}
            QLabel[section="true"] {{ font-weight: 600; padding-top: 10px; padding-bottom: 4px; }}
            QWidget#pasteboard {{ background: {t['canvas']}; }}
            QTabBar::tab {{ padding: 7px 12px; }}
            QTabBar::tab:selected {{ border-bottom: 2px solid {t['accent']}; }}
            QGroupBox {{ border: 1px solid {t['border']}; border-radius: 4px; margin-top: 12px; padding-top: 12px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; }}
        ''')
        self.changed.emit(t)


def manager():
    """Obtém o serviço único da aplicação, inclusive durante testes diretos de widgets."""
    app = QApplication.instance()
    if not hasattr(app, 'makebench_theme'):
        app.makebench_theme = ThemeManager(app)
    return app.makebench_theme


def icon(name):
    """Desenha símbolos geométricos próprios; usa ícones do sistema se disponíveis."""
    aliases = {'new':'document-new', 'open':'document-open', 'save':'document-save',
        'undo':'edit-undo', 'redo':'edit-redo', 'run':'media-playback-start', 'stop':'media-playback-stop',
        'home':'go-home', 'search':'edit-find', 'add':'list-add', 'remove':'list-remove'}
    themed = QIcon.fromTheme(aliases.get(name, name))
    dark=getattr(QApplication.instance(),'makebench_theme',None)
    if not themed.isNull() and not (dark and dark.tokens.get('dark')):
        return themed
    from .icons import vector_icon
    return vector_icon(name)
