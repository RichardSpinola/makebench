"""Índice estático de Python: sugestões, assinaturas e destinos sem executar imports."""
import ast
from dataclasses import dataclass
from pathlib import Path
import re
from .source import ENTRY_FILE, source_files


@dataclass(frozen=True)
class Definition:
    """Local e assinatura de um símbolo extraído do texto do projeto."""
    name:str
    file:str
    line:int
    column:int
    signature:str=''
    description:str=''


def module_name(filename):
    """Converte caminho reservado em nome importável, inclusive inicializadores."""
    value=filename[:-3].replace('/','.')
    return value[:-9] if value.endswith('.__init__') else value


class CodeIndex:
    """Conserva o último AST válido por arquivo durante digitação incompleta."""
    def __init__(self):
        """Prepara caches locais; nenhuma linguagem/servidor adicional é iniciado."""
        self.trees={};self.texts={};self.errors=[];self.definitions={};self.imports={};self.components=[]
        self.ctx={}
        path=Path(__file__).resolve().parents[1]/'runtime/worker.py'
        tree=ast.parse(path.read_text(encoding='utf-8'))
        context=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Context')
        for node in context.body:
            if isinstance(node,ast.FunctionDef) and not node.name.startswith('_'):
                args=ast.unparse(node.args);args=args.removeprefix('self, ').removeprefix('self')
                self.ctx['ctx.'+node.name]=Definition('ctx.'+node.name,'',node.lineno,1,'ctx.'+node.name+'('+args+')',ast.get_docstring(node) or '')
        for name in ('variables','window_variables'):self.ctx.setdefault('ctx.'+name,Definition('ctx.'+name,'',1,1,'ctx.'+name))

    def update(self,source,components=()):
        """Atualiza arquivos alterados e diagnostica imports locais sem tocar no disco."""
        files=source_files(source);self.components=list(components);self.errors=[]
        for name in set(self.trees)-set(files):self.trees.pop(name,None);self.texts.pop(name,None)
        for name,text in files.items():
            try:
                if self.texts.get(name)!=text:self.trees[name]=ast.parse(text);self.texts[name]=text
            except (SyntaxError,ValueError) as exc:
                self.errors.append({'file':name,'line':getattr(exc,'lineno',1) or 1,'column':getattr(exc,'offset',1) or 1,'message':str(exc)})
        self.definitions={};self.imports={}
        known={module_name(name):name for name in files if name!=ENTRY_FILE}
        for name,tree in self.trees.items():
            definitions={};imports={}
            for node in tree.body:
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                    signature=node.name+'('+ast.unparse(node.args)+')' if hasattr(node,'args') else 'class '+node.name
                    definitions[node.name]=Definition(node.name,name,node.lineno,node.col_offset+1,signature,ast.get_docstring(node) or '')
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):
                    for alias in node.names:
                        imports[alias.asname or alias.name.split('.')[0]]=(alias.name if alias.asname else alias.name.split('.')[0],None)
                        if alias.name.startswith('makebench_user') and alias.name not in known:self._missing(name,node,alias.name)
                elif isinstance(node,ast.ImportFrom):
                    base=node.module or ''
                    if node.level and name!=ENTRY_FILE:
                        package=module_name(name).split('.')
                        if not name.endswith('/__init__.py'):package=package[:-1]
                        base='.'.join(package[:len(package)-node.level+1]+([base] if base else []))
                    for alias in node.names:
                        imports[alias.asname or alias.name]=(base,alias.name)
                        if base.startswith('makebench_user'):
                            if base not in known:self._missing(name,node,base)
                            elif base+'.'+alias.name not in known:
                                target=self.trees.get(known[base]);symbols={n.name for n in target.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))} if target else set()
                                assigned={n.id for n in ast.walk(target) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store)} if target else set()
                                if alias.name not in symbols|assigned and alias.name!='*' and not any(isinstance(n,(ast.Import,ast.ImportFrom)) for n in (target.body if target else [])):self._missing(name,node,base+'.'+alias.name)
            self.definitions[name]=definitions;self.imports[name]=imports
        self.known=known

    def _missing(self,name,node,module):
        """Registra referência local quebrada, comum depois de renomear um módulo."""
        self.errors.append({'file':name,'line':node.lineno,'column':node.col_offset+1,'message':'Referência local não encontrada: '+module})

    def resolve(self,file,token):
        """Resolve definição local ou import explícito; não infere tipos dinâmicos."""
        if token in self.ctx:return self.ctx[token]
        first,_,rest=token.partition('.')
        if first in self.definitions.get(file,{}):return self.definitions[file][first]
        if first in self.imports.get(file,{}):
            base,symbol=self.imports[file][first]
            full=base+('.'+symbol if symbol else '')
            if rest:full+='.'+rest
            if full in self.known:return Definition(token,self.known[full],1,1,token)
            module,_,name=full.rpartition('.')
            return self.definitions.get(self.known.get(module),{}).get(name)
        return None

    def complete(self,file,prefix):
        """Sugere APIs conhecidas, símbolos próprios e nomes importados."""
        candidates=dict(self.definitions.get(file,{}));candidates.update(self.ctx)
        for name in self.imports.get(file,{}):candidates.setdefault(name,Definition(name,file,1,1,name))
        if '.' in prefix and not prefix.startswith('ctx.'):
            base=prefix.rsplit('.',1)[0];resolved=self.resolve(file,base)
            if resolved and resolved.file in self.definitions:
                for name,definition in self.definitions[resolved.file].items():candidates[base+'.'+name]=definition
        return [(name,value) for name,value in sorted(candidates.items()) if name.casefold().startswith(prefix.casefold())]

    def call_signature(self,file,before):
        """Mostra a assinatura da chamada local mais próxima ainda aberta."""
        match=re.search(r'([\w.]+)\([^()]*$',before)
        target=self.resolve(file,match.group(1)) if match else None
        return target.signature if target else ''
