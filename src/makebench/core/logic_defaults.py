"""Ações e valores iniciais do modelo, sem dependência gráfica."""
from .project import new_id

OPS=[('terminal_start','Iniciar terminal'),('terminal_send','Enviar ao terminal'),('terminal_stop','Encerrar terminal'),('log','Registrar na saída'),('message','Mostrar mensagem'),('set_text','Alterar texto'),('set_enabled','Habilitar componente'),('set_value','Alterar progresso'),('assign','Definir variável'),('call','Chamar função Python'),('script','Executar Bash'),('run','Executar programa'),('ask','Perguntar'),('confirm','Confirmar'),('go_state','Ir para estado'),('open_window','Abrir janela'),('close_window','Fechar janela'),('show_page','Mostrar página'),('if','Condição'),('repeat','Repetição')]


def literal(value=''):
    """Cria expressão neutra com identificador próprio preservável em comentários."""
    return {'id':new_id('value'),'op':'literal','value':value}


def default_block(op,project,window):
    """Valores iniciais válidos quando há controles compatíveis; nunca executa nada."""
    node={'id':new_id('block'),'op':op};components=list(project.find(window).walk())
    if op in {'log','message','set_text','assign','call'}:node['value']=literal('Olá!')
    if op in {'set_text','set_enabled','set_value','show_page'}:
        kinds={'set_text':{'label','button','text_input','checkbox','output'},'set_value':{'progress'},'show_page':{'page'}}.get(op)
        target=next((n for n in components if kinds is None or n.kind.value in kinds),None)
        if not target:raise ValueError('Insira um componente compatível antes de criar esta ação.')
        node['component']=target.id
    if op.startswith('terminal_'):
        target=next((n for n in components if n.kind.value=='terminal'),None)
        if target is None:raise ValueError('Insira um componente Terminal nesta janela.')
        node['component']=target.id
        if op=='terminal_start':node.update(program=literal(''),arguments={'id':new_id('value'),'op':'list','items':[]})
        if op=='terminal_send':node['value']=literal('help\n')
    if op=='set_enabled':node['value']=literal(True)
    if op=='set_value':node['value']=literal(50)
    if op=='assign':node.update(name='valor',scope='project')
    if op=='call':node['function']='saudacao'
    if op in {'run','script'}:node.update(arguments={'id':new_id('value'),'op':'list','items':[]},admin=False);node['program' if op=='run' else 'source']=literal('uname' if op=='run' else 'printf "Olá, Linux\\n"')
    if op=='ask':node.update(kind='text',prompt=literal('Qual é seu nome?'),options={'id':new_id('value'),'op':'list','items':[]},name='resposta')
    if op=='confirm':node['prompt']=literal('Deseja continuar?')
    if op=='go_state':node['state']=next(iter(project.states.get(window,[])),{'id':'@default'})['id']
    if op=='open_window':node.update(window=next((r.id for r in project.roots if r.id!=window),window),close_current=False)
    if op=='if':node.update(condition=literal(True),then=[],**{'else':[]})
    if op=='repeat':node.update(count=literal(3),body=[])
    return node

