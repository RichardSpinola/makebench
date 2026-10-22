"""Documento, histórico e recuperação do editor GTK, sem execução implícita."""
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
from makebench.core.project import Project
from makebench.core.history import History
from makebench.core.source import SourceBuffer
from makebench.core.storage import load_project,save_project
from makebench.core.assets import AssetStore


class Document:
    """Única autoridade de dados; widgets nunca substituem silenciosamente o modelo."""
    def __init__(self,project=None,path=None):
        """Lê apenas JSON, imagens e texto Python; não importa o arquivo próprio."""
        self.path=Path(path).resolve() if path else None
        self.project=project or (load_project(self.path) if self.path else Project.empty())
        self.source=SourceBuffer.load(self.path);self.assets=AssetStore(self.path.parent if self.path else None)
        self.history=History(self.project);self.saved=self.project.to_dict()

    @property
    def dirty(self):
        """Inclui fonte Python e alterações estruturais no mesmo aviso de fechamento."""
        return self.history.dirty or self.source.dirty

    def edit(self,change):
        """Valida atomicamente uma alteração e conserva IDs/extensões desconhecidas."""
        before=self.project.to_dict()
        try:change(self.project);Project.from_dict(self.project.to_dict());self.history.push(self.project)
        except Exception:self.project=Project.from_dict(before);raise

    def save(self,path=None):
        """Preserva bytes/mtime do JSON sem edição, inclusive formatos antigos."""
        target=Path(path or self.path).resolve();self.assets.write_referenced(target.parent,self.project.asset_paths())
        self.source.write(target)
        if self.path!=target or self.project.to_dict()!=self.saved:save_project(self.project,target)
        self.path=target;self.assets.root=target.parent;self.saved=deepcopy(self.project.to_dict());self.source.mark_saved();self.history.mark_saved()

    def recovery(self,path):
        """Grava snapshot inerte, incluindo texto ainda com erro de sintaxe e imagens."""
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        value={'project':self.project.to_dict(),'source':self.source.text,'path':str(self.path) if self.path else None,
            'assets':{name:base64.b64encode(self.assets.read(name)).decode() for name in self.project.asset_paths()}}
        temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');os.replace(temporary,path)

    @classmethod
    def recover(cls,path):
        """Abre snapshot sem executar código nem substituir o projeto de origem."""
        value=json.loads(Path(path).read_text(encoding='utf-8'));doc=cls(Project.from_dict(value['project']))
        doc.source.text=value['source'];doc.source.saved_text=value['source']+'\0'
        for name,data in value.get('assets',{}).items():
            AssetStore.inside(Path('/tmp/makebench-recovery'),name);doc.assets._cache[name]=base64.b64decode(data,validate=True)
        return doc
