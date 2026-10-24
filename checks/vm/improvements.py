"""Valida a entrega de módulos/Designer nas VMs descartáveis já preparadas."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from machine import Machine


def main():
    """Uma VM por vez; aguarda publicação atômica dos artefatos e desliga no final."""
    parser=argparse.ArgumentParser();parser.add_argument('--system',choices=('ubuntu','fedora'),required=True);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--packages',type=Path,required=True);parser.add_argument('--editor',type=Path,required=True);parser.add_argument('--fixtures',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    machine=Machine(args.root);machine.resume();cases=[]
    validate=Path(__file__).with_name('validate.py')
    def run(backend,format,artifact,project=None,quick=False):
        """Só lê artefatos completos; preserva logs e resultados de cada instalação."""
        deadline=time.monotonic()+600
        if not artifact.exists():print('Aguardando construção:',artifact.name,flush=True)
        while not artifact.exists():
            if time.monotonic()>deadline:raise RuntimeError('Artefato não ficou pronto: '+str(artifact))
            time.sleep(1)
        target=args.output/(args.system+'-'+backend+'-'+format)
        command=[sys.executable,str(validate),str(args.root),str(artifact),'--format',format,'--backend',backend,'--output',str(target)]
        if project:command+=['--project-dir',str(project)]
        if quick:command+=['--quick-close']
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.with_suffix('.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
        data=json.loads((target/'results.json').read_text());cases.append(data);print('OK',args.system,backend,format,flush=True)
    try:
        for backend in ('qt','gtk'):
            run(backend,'editor',args.editor,args.fixtures/('vm-editor-modules-'+backend),quick=backend=='gtk')
        native='deb' if args.system=='ubuntu' else 'rpm'
        for backend in ('qt','gtk'):
            for format,suffix in [(native,native),('appimage','AppImage'),('flatpak','flatpak')]:run(backend,format,args.packages/(backend+'.'+suffix))
        args.output.mkdir(parents=True,exist_ok=True);(args.output/(args.system+'-results.json')).write_text(json.dumps(cases,ensure_ascii=False,indent=2))
    finally:machine.stop()


if __name__=='__main__':main()
