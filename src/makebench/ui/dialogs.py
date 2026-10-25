# SPDX-License-Identifier: GPL-3.0-or-later
"""Editor-controlled dialogs, with explicit actions in the active language."""

from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtWidgets import QDialogButtonBox, QFileDialog, QMessageBox

from makebench.i18n import language, tr


def button_labels():
    """Standard button labels in the active language, keyed by QDialogButtonBox name."""
    return {
        "Save": tr("Save"),
        "Discard": tr("Discard"),
        "Cancel": tr("Cancel"),
        "Open": tr("Open"),
        "Close": tr("Close"),
        "Ok": tr("Continue"),
        "Yes": tr("Confirm"),
        "No": tr("Decline"),
        "Apply": tr("Apply"),
        "Reset": tr("Restore"),
        "RestoreDefaults": tr("Restore defaults"),
        "Help": tr("Help"),
    }


def translate_buttons(dialog):
    """Label standard buttons in the active language, keeping their roles and return codes."""
    for box in [dialog, *dialog.findChildren(QDialogButtonBox)]:
        if not isinstance(box, (QMessageBox, QDialogButtonBox)):
            continue
        for name, text in button_labels().items():
            enum = getattr(type(box).StandardButton, name, None)
            if enum is not None and box.button(enum):
                box.button(enum).setText(text)
    if isinstance(dialog, QFileDialog):
        for role, text in [
            ("LookIn", tr("Look in:")),
            ("FileName", tr("File name:")),
            ("FileType", tr("File type:")),
            (
                "Accept",
                tr("Save")
                if dialog.acceptMode() == QFileDialog.AcceptMode.AcceptSave
                else tr("Open"),
            ),
            ("Reject", tr("Cancel")),
        ]:
            dialog.setLabelText(getattr(QFileDialog.DialogLabel, role), text)


# Qt's own strings (file dialogs, text menus) that the Brazilian Portuguese
# fallback covers when the system has no qtbase_pt_BR catalog installed.
PORTUGUESE_QT_LABELS = {
    "Save": "Salvar",
    "&Save": "&Salvar",
    "Discard": "Descartar",
    "Cancel": "Cancelar",
    "&Cancel": "&Cancelar",
    "Open": "Abrir",
    "&Open": "&Abrir",
    "Close": "Fechar",
    "&Close": "&Fechar",
    "Yes": "Confirmar",
    "&Yes": "&Confirmar",
    "No": "Recusar",
    "&No": "&Recusar",
    "OK": "Continuar",
    "Apply": "Aplicar",
    "Look in:": "Procurar em:",
    "File name:": "Nome do arquivo:",
    "Files of type:": "Tipo de arquivo:",
    "Name": "Nome",
    "Size": "Tamanho",
    "Type": "Tipo",
    "Date Modified": "Modificado em",
    "Cut": "Recortar",
    "Copy": "Copiar",
    "Paste": "Colar",
    "Select All": "Selecionar tudo",
    "Undo": "Desfazer",
    "Redo": "Refazer",
    "Delete": "Remover",
    "New Folder": "Nova pasta",
    "Folder": "Pasta",
    "Show hidden files": "Mostrar arquivos ocultos",
    "Detailed View": "Detalhes",
    "List View": "Lista",
    "Back": "Voltar",
    "Forward": "Avançar",
    "Parent Directory": "Pasta acima",
    "Create New Folder": "Criar pasta",
    "Rename": "Renomear",
    "Show Details...": "Mostrar detalhes…",
    "Hide Details...": "Ocultar detalhes…",
}
QT_CONTEXTS = {
    "QPlatformTheme",
    "QFileDialog",
    "QDialogButtonBox",
    "QMessageBox",
    "QFileSystemModel",
    "QLineEdit",
    "QWidgetTextControl",
}


def install_translation(app):
    """Install Qt's catalog for the active language, with no global Qt event filter.

    English needs nothing: Qt's built-in strings are already English. For
    Brazilian Portuguese, Qt's own catalog is loaded plus a small fallback for
    systems without it. A global Python filter could receive private WebEngine
    objects still under construction; catalog-based translation avoids that.
    """
    app._makebench_dialog_filter = True
    if language() != "pt_BR":
        return
    catalog = QTranslator(app)
    catalog.load("qtbase_pt_BR", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    app.installTranslator(catalog)

    class PortugueseFallback(QTranslator):
        """Translate standard actions even when the Qt catalog is not installed."""

        def translate(self, context, source, disambiguation=None, n=-1):
            """Leave unknown texts to the previous Qt catalog."""
            if context in QT_CONTEXTS:
                return PORTUGUESE_QT_LABELS.get(source) or PORTUGUESE_QT_LABELS.get(
                    source.replace("&", "")
                )
            return None

    fallback = PortugueseFallback(app)
    app.installTranslator(fallback)
    app._makebench_translator = catalog
    app._makebench_translation_fallback = fallback
