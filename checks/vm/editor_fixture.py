"""Projeto de QA cuja fonte denuncia qualquer execução indevida ao abrir o editor."""
from pathlib import Path
import argparse
from makebench.core.project import Project
from makebench.core.storage import save_project
from makebench.core.source import SourceBuffer

parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--backend',choices=('qt','gtk'),default='qt');args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
p=Project.empty('Editor QA');p.application['backend']=args.backend
terminal=p.add(p.root.id,'terminal');terminal.properties['terminal_autostart']=True
source=SourceBuffer("from pathlib import Path\nfrom makebench_user.helper import calculate\nPath('/home/qa/should-not-execute').write_text('ERRO')\n")
source.add_module('makebench_user/helper.py',"from pathlib import Path\nPath('/home/qa/should-not-execute').write_text('ERRO módulo')\n\ndef calculate(value):\n    return value+1\n")
p.python_files=sorted(source.modules);path=args.output/'project.makebench.json'
source.write(path);save_project(p,path);source.mark_saved()
