"""Projeto de QA cuja fonte denuncia qualquer execução indevida ao abrir o editor."""
from pathlib import Path
import argparse
from makebench.core.project import Project
from makebench.core.storage import save_project

parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--backend',choices=('qt','gtk'),default='qt');args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
p=Project.empty('Editor QA');p.application['backend']=args.backend
terminal=p.add(p.root.id,'terminal');terminal.properties['terminal_autostart']=True
save_project(p,args.output/'project.makebench.json')
(args.output/'project.actions.py').write_text("from pathlib import Path\nPath('/home/qa/should-not-execute').write_text('ERRO')\n")
