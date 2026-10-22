"""Diálogos controlados pelo editor, com ações explícitas em português."""
from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QFileDialog, QMessageBox

BUTTONS = {'Save':'Salvar','Discard':'Descartar','Cancel':'Cancelar','Open':'Abrir',
    'Close':'Fechar','Ok':'Continuar','Yes':'Confirmar','No':'Recusar','Apply':'Aplicar',
    'Reset':'Restaurar','RestoreDefaults':'Restaurar padrões','Help':'Ajuda'}


def translate_buttons(dialog):
    """Traduz botões padrão preservando seus papéis e códigos de retorno."""
    for box in [dialog, *dialog.findChildren(QDialogButtonBox)]:
        if not isinstance(box, (QMessageBox, QDialogButtonBox)):
            continue
        for name, text in BUTTONS.items():
            enum = getattr(type(box).StandardButton, name, None)
            if enum is not None and box.button(enum):
                box.button(enum).setText(text)
    if isinstance(dialog, QFileDialog):
        for role, text in [('LookIn','Procurar em:'),('FileName','Nome do arquivo:'),
                           ('FileType','Tipo de arquivo:'),('Accept','Salvar' if dialog.acceptMode()==QFileDialog.AcceptMode.AcceptSave else 'Abrir'),('Reject','Cancelar')]:
            dialog.setLabelText(getattr(QFileDialog.DialogLabel, role), text)


def install_translation(app):
    """Instala catálogos e uma reserva textual, sem filtro global de eventos Qt.

    Um filtro Python global pode receber objetos privados de WebEngine ainda
    em construção. Tradução por catálogo evita envolver esses objetos.
    """
    catalog=QTranslator(app)
    catalog.load('qtbase_pt_BR',QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    app.installTranslator(catalog)
    class PortugueseFallback(QTranslator):
        """Traduz ações padrão mesmo quando o catálogo não está instalado."""
        def translate(self,context,source,disambiguation=None,n=-1):
            """Mantém textos desconhecidos com o catálogo anterior do Qt."""
            labels={'Save':'Salvar','&Save':'&Salvar','Discard':'Descartar','Cancel':'Cancelar',
                '&Cancel':'&Cancelar','Open':'Abrir','&Open':'&Abrir','Close':'Fechar',
                '&Close':'&Fechar','Yes':'Confirmar','&Yes':'&Confirmar','No':'Recusar',
                '&No':'&Recusar','OK':'Continuar','Apply':'Aplicar','Look in:':'Procurar em:',
                'File name:':'Nome do arquivo:','Files of type:':'Tipo de arquivo:',
                'Name':'Nome','Size':'Tamanho','Type':'Tipo','Date Modified':'Modificado em',
                'Cut':'Recortar','Copy':'Copiar','Paste':'Colar','Select All':'Selecionar tudo',
                'Undo':'Desfazer','Redo':'Refazer','Delete':'Remover','New Folder':'Nova pasta',
                'Folder':'Pasta','Show hidden files':'Mostrar arquivos ocultos','Detailed View':'Detalhes',
                'List View':'Lista','Back':'Voltar','Forward':'Avançar','Parent Directory':'Pasta acima',
                'Create New Folder':'Criar pasta','Rename':'Renomear','Show Details...':'Mostrar detalhes…',
                'Hide Details...':'Ocultar detalhes…'}
            if context in {'QPlatformTheme','QFileDialog','QDialogButtonBox','QMessageBox','QFileSystemModel','QLineEdit','QWidgetTextControl'}:
                return labels.get(source) or labels.get(source.replace('&',''))
            return None
    fallback=PortugueseFallback(app);app.installTranslator(fallback)
    app._makebench_translator=catalog;app._makebench_translation_fallback=fallback
    app._makebench_dialog_filter=True
