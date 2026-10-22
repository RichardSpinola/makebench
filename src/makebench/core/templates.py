"""Modelos de estrutura: dados puros, sem carregar ou executar funções próprias."""
from .project import Project,ComponentKind,LayoutKind,new_id
from .navigation import welcome_template,add_window
from .logic import create_flow

MODELS=[('simple','Aplicativo simples','Uma janela com texto, campo e botão.'),
        ('welcome','Assistente','Três etapas com Voltar, Próximo e Concluir.'),
        ('tasks','Central de tarefas / utilitário','Scripts, progresso e saída.'),
        ('multi','Aplicativo com várias janelas','Barra lateral e janela de preferências.'),
        ('blank','Em branco','Uma janela para começar do seu jeito.')]


def make_template(key,name):
    """Cria modelos independentes; tarefas usa o exemplo distribuído pelo editor."""
    if key=='welcome':
        p=welcome_template(name);p.root.properties.update(width=520,height=430,padding=24,spacing=18)
        return p
    p=Project.empty(name);p.root.properties.update(width=720,height=480,padding=24,spacing=18)
    if key=='blank':return p
    if key=='simple':
        text=p.add(p.root.id,ComponentKind.LABEL);text.properties['text']='Seu aplicativo começa aqui'
        entry=p.add(p.root.id,ComponentKind.TEXT_INPUT);entry.properties['placeholder']='Digite seu nome'
        button=p.add(p.root.id,ComponentKind.BUTTON);button.properties['text']='Continuar'
        create_flow(p,button.id)['body']=[{'id':new_id('block'),'op':'message','value':{'id':new_id('value'),'op':'literal','value':'Pronto para criar!'}}]
    elif key=='multi':
        p.root.layout=LayoutKind.HORIZONTAL
        sidebar=p.add(p.root.id,ComponentKind.CONTAINER);sidebar.properties.update(padding=12,spacing=12,size_mode={'width':'fixed','height':'fill'});sidebar.geometry['width']=190
        title=p.add(sidebar.id,ComponentKind.LABEL);title.properties['text']='Meu aplicativo'
        preferences=p.add(sidebar.id,ComponentKind.BUTTON);preferences.properties['text']='Preferências'
        content=p.add(p.root.id,ComponentKind.CONTAINER);content.properties.update(padding=24,spacing=18,size_mode={'width':'fill','height':'fill'})
        heading=p.add(content.id,ComponentKind.LABEL);heading.properties['text']='Área de trabalho'
        output=p.add(content.id,ComponentKind.OUTPUT);output.properties['text']='Organize suas ferramentas nesta área.'
        window=add_window(p,'Preferências');window.properties.update(width=480,height=360,padding=24,spacing=18)
        option=p.add(window.id,ComponentKind.CHECKBOX);option.properties['text']='Ativar notificações'
        close=p.add(window.id,ComponentKind.BUTTON);close.properties['text']='Concluir'
        create_flow(p,preferences.id)['body']=[{'id':new_id('block'),'op':'open_window','window':window.id,'close_current':False}]
        create_flow(p,close.id)['body']=[{'id':new_id('block'),'op':'close_window'}]
    return p
