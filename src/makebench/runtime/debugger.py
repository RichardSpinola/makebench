"""Depuração do snapshot Python, com comandos concorrentes e inspeção sem eval."""
from __future__ import annotations
import queue
import sys
import threading
from collections import deque
from itertools import islice


class DebugStopped(BaseException):
    """Interrompe o worker inclusive se o projeto captura Exception."""


def inspect_value(value, depth=0, budget=None):
    """Serializa valores nativos sem chamar repr, propriedades ou código do projeto."""
    budget=[1000] if budget is None else budget
    if budget[0]<=0:return '<limite de inspeção>'
    budget[0]-=1
    kind = type(value)
    if kind in (str, int, float, bool, type(None)):
        if kind is str: return value[:512]
        if kind is float:
            import math
            return value if math.isfinite(value) else str(value)
        if kind is int and value.bit_length() > 1024: return '<inteiro grande>'
        return value
    if depth >= 3: return '<'+type.__getattribute__(kind,'__name__')[:100]+'>'
    if kind in (list, tuple): return [inspect_value(v, depth+1,budget) for v in value[:100]]
    if kind is dict:
        return {str(k)[:100]:inspect_value(v,depth+1,budget) for k,v in islice(value.items(),100) if type(k) in (str,int,bool)}
    return '<'+type.__getattribute__(kind,'__name__')[:100]+'>'


class Debugger:
    """Controla pausas apenas em fontes do projeto no worker principal."""
    def __init__(self, send):
        """Prepara sincronização; configuração explícita habilita o rastreamento."""
        self.send = send; self.condition = threading.Condition()
        self.enabled = False; self.paused = False; self.pause_requested = False
        self.stopping = False; self.mode = 'continue'; self.depth = 0; self.last_frame = None
        self.files = set(); self.breakpoints = set(); self.lines = {}; self.flow = None; self.component = None
        self.context = None; self.entry = True; self.last_location = None

    def configure(self, config, source_filename, generated, context, file_names=None):
        """Associa mapas do snapshot, sem aceitar avaliação ou fontes adicionais."""
        self.enabled = bool(config.get('enabled'))
        self.file_names=file_names or {source_filename:'@actions'}
        self.files = {*self.file_names, '<makebench-generated>'}
        for (flow,block),line in generated.lines.items(): self.lines.setdefault(line,(flow,block))
        self.block_lines=generated.lines
        self.context = context; self.command({'action':'breakpoints','items':config.get('breakpoints',[])})

    def command(self, message):
        """Recebe comandos da thread de transporte mesmo com o worker aguardando UI."""
        action = message.get('action')
        with self.condition:
            if action == 'breakpoints':
                self.breakpoints = {('source',item.get('path','@actions'),item.get('line')) if item.get('file')=='source' else ('block',item.get('flow'),item.get('block')) for item in message.get('items',[]) if isinstance(item,dict)}
            elif action == 'pause': self.pause_requested = True
            elif action == 'stop': self.stopping = True; self.paused = False
            elif action in {'continue','step_over','step_in','step_out'}:
                self.mode = action; self.depth = self.frame_depth(self.last_frame) if self.last_frame else 0
                self.pause_requested = False; self.paused = False; self.condition.notify_all()
            self.condition.notify_all()

    def frame_depth(self, frame):
        """Conta apenas chamadas pertencentes às fontes autorizadas do snapshot."""
        count = 0
        while frame:
            count += frame.f_code.co_filename in self.files; frame = frame.f_back
        return count

    def location(self, frame):
        """Resolve linha própria ou ID de bloco no código gerado do snapshot."""
        if frame.f_code.co_filename == '<makebench-generated>':
            flow,block = self.lines.get(frame.f_lineno,(self.flow,None))
            if block is None and frame.f_code.co_name=='_value':block=frame.f_locals.get('identifier')
            if block is None and '_pc' in frame.f_locals:block=frame.f_locals.get('_pc') or self.context.graph_node
            if block is None:
                preceding=[(number,key[1]) for key,number in self.block_lines.items() if key[0]==self.flow and number<=frame.f_lineno]
                if preceding:block=max(preceding,key=lambda item:item[0])[1]
            return {'flow':flow,'block':block,'line':frame.f_lineno}
        return {'flow':self.flow,'source_line':frame.f_lineno,'source_file':self.file_names[frame.f_code.co_filename]}

    def snapshot(self, frame, reason):
        """Captura pilha e dados limitados; nenhuma expressão é avaliada."""
        stack = []; current = frame;budget=[1000]
        while current and len(stack)<64:
            if current.f_code.co_filename in self.files:
                stack.append({'name':current.f_code.co_name[:128], **self.location(current),
                              'variables':{name[:100]:inspect_value(value,budget=budget) for name,value in islice(current.f_locals.items(),100) if not name.startswith('__') and name!='ctx' and (current.f_code.co_filename!='<makebench-generated>' or not name.startswith('_'))}})
            current = current.f_back
        return {'type':'debug','state':'paused','reason':reason,'component':self.component,**self.location(frame),
                'stack':stack,'variables':inspect_value(self.context.variables,budget=budget),
                'window_variables':inspect_value(self.context.window_variables,budget=budget)}

    def checkpoint(self, frame=None, waiting=False):
        """Atende pausa/cancelamento, inclusive dentro de uma espera por resposta da UI."""
        if self.stopping: raise DebugStopped()
        if not self.enabled: return
        frame = frame or self.last_frame
        if frame is None: return
        if self.pause_requested:
            self.pause(frame,'pause')

    def pause(self, frame, reason):
        """Suspende o worker sem bloquear o leitor de comandos ou a interface."""
        self.last_frame = frame
        with self.condition:
            self.paused = True; self.pause_requested = False
            self.send(self.snapshot(frame,reason))
            while self.paused and not self.stopping: self.condition.wait(.1)
        if self.stopping: raise DebugStopped()
        self.send({'type':'debug','state':'running'})

    def trace(self, frame, event, arg):
        """Rastreia linhas próprias e instruções mapeadas; bibliotecas ficam fora."""
        if not self.enabled or frame.f_code.co_filename not in self.files: return None
        if event != 'line': return self.trace
        self.last_frame = frame
        self.checkpoint(frame)
        generated = frame.f_code.co_filename == '<makebench-generated>'
        if generated and frame.f_lineno not in self.lines: return self.trace
        location = self.location(frame); depth = self.frame_depth(frame)
        point = ('block',location.get('block')) if generated else ('source',location.get('source_file','@actions'),frame.f_lineno)
        hit = any(item[0]=='block' and (item[1] is None or item[1]==self.flow) and self.block_lines.get((self.flow,item[2]))==frame.f_lineno for item in self.breakpoints) if generated else point in self.breakpoints
        step = self.mode == 'step_in' or (self.mode == 'step_over' and depth<=self.depth) or (self.mode == 'step_out' and depth<self.depth)
        if self.entry or hit or step:
            self.entry = False; self.pause(frame,'breakpoint' if hit else 'entry' if self.mode=='continue' and not step else 'step')
        return self.trace


class WorkerTransport:
    """Um leitor proprietário separa comandos de depuração de eventos e respostas."""
    def __init__(self, receive, debugger):
        """Inicia leitor somente após o snapshot; entrada é protocolo JSON privado."""
        self.queue = queue.Queue(); self.debugger = debugger
        def read():
            """Desvia comandos sem consumir respostas aguardadas pelo contexto."""
            try:
                while True:
                    value = receive()
                    if value.get('type') == 'debug': debugger.command(value)
                    elif value.get('type') == 'shutdown':
                        if debugger.paused:debugger.command({'action':'stop'})
                        self.queue.put(value); return
                    else: self.queue.put(value)
            except (EOFError,ValueError,OSError) as exc:
                if debugger.paused:debugger.command({'action':'stop'})
                self.queue.put(exc)
        self.thread = threading.Thread(target=read,daemon=True); self.thread.start()
        self.deferred = deque()

    def receive(self, response=None):
        """Espera por tipo/ID, preservando outras mensagens e atendendo Pausar/Parar."""
        if response is None and self.deferred: return self.deferred.popleft()
        while True:
            self.debugger.checkpoint(waiting=response is not None)
            try: value = self.queue.get(timeout=.05)
            except queue.Empty: continue
            if isinstance(value, BaseException): raise value
            if response is None or value.get('type') == 'shutdown' or (value.get('type')=='response' and value.get('id')==response): return value
            self.deferred.append(value)
