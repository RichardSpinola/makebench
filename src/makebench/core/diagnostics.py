"""Relatório de ambiente somente leitura, sem subprocessos nem instalação."""
import importlib.metadata
import locale
import os
import platform
from .environment import gtk_support,build_tools
from makebench import __version__


def environment_report(desktop=None):
    """Gera texto copiável; dados gráficos podem ser acrescentados pela UI GTK."""
    try:qt=importlib.metadata.version('PySide6')
    except importlib.metadata.PackageNotFoundError:qt='Não instalado (opcional para aplicativos Qt)'
    gtk=gtk_support();lines=[f'Makebench {__version__}',f'Python {platform.python_version()}',f'Sistema {platform.system()} {platform.machine()}',
        'Editor: Qt Widgets',f'PySide6: {qt}',f'Locale: {locale.getlocale()}','LANG: '+os.environ.get('LANG','Não informado'),
        'PyGObject: '+('Detectado' if gtk['pygobject'] else 'Ausente'),'GTK4: '+('Detectado' if gtk['gtk4'] else 'Ausente'),
        'libadwaita: '+('Detectado' if gtk['adwaita'] else 'Ausente')]
    try:
        import gi;gi.require_version('WebKit','6.0');webkit=True
    except (ImportError,ValueError):webkit=False
    lines.append('WebKitGTK 6 (Blockly): '+('Detectado' if webkit else 'Ausente — edição nativa de ações disponível'))
    lines.extend(f'{key}: {value}' for key,value in (desktop or {}).items())
    lines.extend(f'{key}: {value or "Ausente"}' for key,value in build_tools().items())
    lines.append('Detectar pkexec não valida o agente Polkit nem a autenticação real.')
    return '\n'.join(lines)
