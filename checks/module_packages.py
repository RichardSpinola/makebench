"""Constrói exemplos com módulos em ambiente isolado e registra os hashes reais."""
import argparse
import json
from pathlib import Path
from makebench.core.storage import load_project
from makebench.core.source import SourceBuffer
from makebench.core.packages import build_package,FORMATS


def main():
    """Reutiliza SDKs e rodas preparados; nunca importa as funções do exemplo."""
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--backend',choices=('qt','gtk'),required=True);parser.add_argument('--formats',nargs='+',choices=tuple(FORMATS),default=['source','deb','rpm','appimage','flatpak']);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]/'examples/python-modules'/args.backend;path=root/'project.makebench.json'
    project=load_project(path);source=SourceBuffer.load(path).text;results=[]
    def progress(number,text):
        """Registra a ferramenta utilizada, inclusive falha, sem resumo artificial."""
        print(number,text,flush=True)
    for format in args.formats:
        destination=args.output/(args.backend+FORMATS[format][2])
        result=build_package(project,source,lambda name:(root/name).read_bytes(),destination,format,progress);results.append(result)
        (args.output/(args.backend+'-results.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(result),flush=True)


if __name__=='__main__':main()
