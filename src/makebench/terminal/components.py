"""Ciclo de vida de terminais de componentes sem importar Qt ou GTK."""
from pathlib import Path
from makebench.core.project import ComponentKind


def start_components(root, widgets, directory):
    """Inicia os terminais configurados somente no runtime explicitamente iniciado."""
    for node in root.walk():
        if node.kind != ComponentKind.TERMINAL:
            continue
        widget = widgets[node.id]
        widget.terminal.root = Path(directory).resolve()
        if node.properties.get('terminal_autostart', False) and not widget.terminal.running:
            widget.start_terminal(node.properties.get('terminal_program') or None, node.properties.get('terminal_arguments', []))


def stop_components(widgets):
    """Encerra sessões possuídas pelos widgets antes de fechar a execução."""
    for widget in widgets.values():
        if hasattr(widget, 'stop_terminal'):
            widget.stop_terminal()


def terminal_request(widget, method, request):
    """Atende a API declarada sem encaminhar operações a controles incompatíveis."""
    if not hasattr(widget, 'terminal'):
        raise ValueError('Selecione um componente Terminal de uma janela aberta.')
    if method == 'terminal_start':
        return widget.start_terminal(request.get('program') or None, request.get('arguments', []))
    if method == 'terminal_send':
        return widget.send_terminal(str(request['value']))
    if method == 'terminal_stop':
        widget.stop_terminal()
        return None
    raise ValueError('Operação de terminal desconhecida.')
