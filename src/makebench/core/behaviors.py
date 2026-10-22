"""Modelos de comportamento: dados neutros reais, sem execução nem dependência Qt."""
from .project import ComponentKind, ProjectError, new_id
from .logic_defaults import default_block, literal

TEMPLATES = [('open_window','Abrir janela'),('go_state','Mudar estado'),
    ('message','Mostrar mensagem'),('read_field','Ler campo'),('set_text','Alterar texto'),
    ('save_value','Guardar valor em variável'),('validate_input','Validar entrada'),
    ('run','Executar tarefa'),('confirm','Solicitar confirmação')]


def behavior_template(kind, project, window):
    """Retorna blocos válidos para a janela informada ou explica a pré-condição ausente.

    Referências são componentes reais. Guardar valor mantém memória da execução,
    não grava arquivos. Criar estes dados não inicia código ou processos.
    """
    root=project.find(window)
    if root is None or root.kind!=ComponentKind.WINDOW:raise ProjectError('Selecione uma interface.')
    fields=[n for n in root.walk() if n.kind==ComponentKind.TEXT_INPUT]
    def read():
        """Constrói uma leitura do primeiro campo desta interface."""
        if not fields:raise ProjectError('Adicione um campo de texto a esta interface primeiro.')
        return {'id':new_id('value'),'op':'read','component':fields[0].id,'attribute':'text'}
    if kind=='open_window' and len(project.roots)<2:raise ProjectError('Crie outra interface no Mapa antes de abrir uma janela.')
    if kind=='go_state' and not project.states.get(window):raise ProjectError('Crie um estado no Mapa antes de usar este modelo.')
    if kind in {'open_window','go_state','message','set_text','run'}:
        try:return [default_block(kind,project,window)]
        except ValueError as exc:raise ProjectError(str(exc)) from exc
    if kind in {'read_field','save_value'}:
        node=default_block('assign',project,window)
        node['value']=read() if kind=='read_field' else literal('Novo valor')
        return [node]
    if kind=='validate_input':
        node=default_block('if',project,window)
        node['condition']={'id':new_id('value'),'op':'binary','operator':'!=','left':read(),'right':literal('')}
        success=default_block('message',project,window);success['value']=literal('Entrada preenchida.')
        failure=default_block('message',project,window);failure['value']=literal('Preencha o campo antes de continuar.')
        node.update(then=[success],**{'else':[failure]});return [node]
    if kind=='confirm':
        confirm=default_block('confirm',project,window)
        return [confirm]
    raise ProjectError('Modelo de comportamento desconhecido.')


def append_behavior(flow, blocks):
    """Acrescenta ações mantendo IDs/comentários anteriores, invalida só a vista derivada."""
    if flow.get('body') is None:raise ProjectError('Complete os blocos soltos antes de inserir um modelo.')
    from copy import deepcopy
    flow['body'].extend(deepcopy(blocks))
    flow['workspace']={'workspaceComments':deepcopy(flow.get('workspace',{}).get('workspaceComments',[]))}
