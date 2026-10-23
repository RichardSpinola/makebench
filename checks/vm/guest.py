"""Instala, abre, executa, captura e remove um artefato dentro da VM descartável."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import tempfile


def run(arguments,**kwargs):
    """Falhas de instalação/teste são registradas, nunca convertidas em sucesso."""
    print('+',*arguments,flush=True);return subprocess.run(arguments,check=True,**kwargs)


def main():
    """Esta rotina pertence ao convidado; não deve ser chamada no desktop do usuário."""
    parser=argparse.ArgumentParser();parser.add_argument('artifact',type=Path);parser.add_argument('--format',choices=('deb','rpm','appimage','flatpak','editor'),required=True);parser.add_argument('--backend',choices=('qt','gtk'),default='qt');parser.add_argument('--output',type=Path,required=True);parser.add_argument('--project',type=Path);parser.add_argument('--quick-close',action='store_true');args=parser.parse_args()
    if not Path('/etc/hostname').read_text().strip().startswith('makebench-'):raise RuntimeError('Executar apenas na VM descartável registrada.')
    if not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        return run(['dbus-run-session','--',sys.executable,__file__,*sys.argv[1:]]).returncode
    artifact=args.artifact.resolve();output=args.output.resolve()
    if output.name!='evidence' or output.parent!=artifact.parent or not output.parent.name.startswith('case-'):raise RuntimeError('Pasta de evidências fora do caso isolado.')
    if output.exists():shutil.rmtree(output)
    output.mkdir(parents=True)
    identifier='org.makebench.qa'+args.backend;format=args.format;home=Path.home();os.environ['DISPLAY']=':91';environment=dict(os.environ,QT_QPA_PLATFORM='xcb',GDK_BACKEND='x11',GSK_RENDERER='cairo',LIBGL_ALWAYS_SOFTWARE='1')
    # O sandbox normal do Chromium é obrigatório no teste do editor.
    environment.pop('QTWEBENGINE_DISABLE_SANDBOX',None);environment.pop('QTWEBENGINE_CHROMIUM_FLAGS',None)
    sentinel=home/'makebench-host-sentinel';sentinel.write_text('Arquivo do host convidado, não compartilhado com o Flatpak.')
    marker=home/'.var/app'/identifier/'data/qa-result.json' if format=='flatpak' else output/'application-result.json'
    if marker.exists():marker.unlink()
    environment['MAKEBENCH_QA_OUTPUT']=str(marker)
    records={'format':format,'backend':args.backend,'os_release':Path('/etc/os-release').read_text(),'architecture':os.uname().machine,'artifact':artifact.name,'steps':[]}
    installed=False;process=None
    with (output/'xvfb.log').open('w') as serverlog:server=subprocess.Popen(['Xvfb',':91','-screen','0','1280x900x24','-nolisten','tcp','-ac'],stdout=serverlog,stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            if Path('/tmp/.X11-unix/X91').exists():break
            if server.poll() is not None:raise RuntimeError('Xvfb não iniciou.')
            time.sleep(.05)
        os.environ.update(environment)
        if format=='deb':
            run(['sudo','env','DEBIAN_FRONTEND=noninteractive','apt-get','install','-y',str(artifact)],timeout=600);installed=True;command=['/usr/bin/'+identifier]
            run(['dpkg-query','-W',identifier]);records['steps'].append('Instalação DEB real')
        elif format=='rpm':
            run(['sudo','dnf','-y','install',str(artifact)],timeout=600);installed=True;command=['/usr/bin/'+identifier]
            run(['rpm','-q',identifier]);records['steps'].append('Instalação RPM real')
        elif format=='flatpak':
            run(['flatpak','remote-add','--user','--if-not-exists','flathub','https://dl.flathub.org/repo/flathub.flatpakrepo'])
            run(['flatpak','install','--user','--noninteractive','--assumeyes',str(artifact)],timeout=1200);installed=True
            command=['flatpak','run','--env=MAKEBENCH_QA_OUTPUT='+str(marker),identifier];records['steps'].append('Instalação Flatpak e resolução automática do runtime')
        else:
            artifact.chmod(0o755);command=[str(artifact)]
            if format=='editor':
                with tempfile.TemporaryDirectory(prefix='makebench-editor-probe-',dir=home) as extracted:
                    run([str(artifact),'--appimage-extract'],cwd=extracted,stdout=subprocess.DEVNULL,timeout=120)
                    appdir=Path(extracted)/'squashfs-root'
                    # Só a cópia descartável troca a entrada por uma sonda confiável;
                    # o AppImage original é aberto sem alteração no teste gráfico abaixo.
                    (appdir/'app/makebench/__main__.py').write_text("import runpy\ndef main():return runpy.run_path('/home/qa/editor-tools.py')['probe']()\n")
                    tools=subprocess.check_output([str(appdir/'AppRun')],env=environment,text=True,timeout=30)
                    records['runtime_tools']=json.loads(tools)
                    records['steps'].append('Ferramentas do host sem bibliotecas privadas e certificados TLS do destino')
                if args.project:command.append(str(args.project.resolve()))
            records['steps'].append('AppImage executável, sem instalação de Python/backend no convidado')
        with (output/'application.log').open('w') as log:process=subprocess.Popen(command,env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+(35 if format=='editor' else 60);result=None;visible=False
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Aplicativo saiu antes da verificação: '+(output/'application.log').read_text())
            windows=subprocess.run(['xdotool','search','--onlyvisible','--name','Makebench' if format=='editor' else 'Fluxo com fios'],capture_output=True,text=True)
            visible=visible or windows.returncode==0
            if format=='editor' and visible:
                time.sleep(.1 if args.quick_close else 5);break
            if marker.exists():
                try:result=json.loads(marker.read_text());break
                except ValueError:pass
            time.sleep(.05)
        if not visible:raise RuntimeError('Nenhuma janela do aplicativo ficou visível.')
        run(['import','-window','root',str(output/'window.png')])
        records['steps'].append('Janela real aberta e captura PNG')
        if format=='editor':
            assert not (home/'should-not-execute').exists(),'Abrir editor executou código do projeto'
            records['steps'].append('Editor Qt/WebEngine abre projeto sem executar Python próprio')
            windows=subprocess.check_output(['xdotool','search','--onlyvisible','--name','Makebench'],text=True).split()
            for window in windows:
                run(['xdotool','windowfocus',window]);run(['xdotool','key','ctrl+q'])
            process.wait(timeout=15);records['steps'].append('Editor fechado pelo atalho Ctrl+Q')
        else:
            if result is None:raise RuntimeError('Fluxo não gerou resultado: '+(output/'application.log').read_text())
            assert result['steps']==3 and result['dependency']=='25.0',result
            if format=='flatpak':assert result['host_visible'] is False,'Sandbox acessou arquivo privado do host convidado'
            else:
                assert result['host_visible'] is True,result
                assert result['prefix']!='/usr' and 'python3.12' in result['executable'],result
            process.wait(timeout=25);assert process.returncode==0,(process.returncode,(output/'application.log').read_text())
            if format!='flatpak':
                deadline=time.monotonic()+3
                pid=result['terminal_pid']
                while Path(f'/proc/{pid}/stat').exists() and time.monotonic()<deadline:time.sleep(.05)
                assert not Path(f'/proc/{pid}/stat').exists(),'Terminal deixou processo após fechar a janela'
            records['application']=result;records['steps'].extend(['Grafo, repetição/condição, dependência Python adicional e duas janelas','Terminal e tarefas executados','Aplicativo encerra e recolhe processos'])
        if installed:
            if format=='deb':
                run(['sudo','apt-get','remove','-y',identifier]);assert not Path('/opt',identifier).exists();assert not Path('/usr/bin',identifier).exists()
            elif format=='rpm':
                run(['sudo','dnf','-y','remove',identifier]);assert not Path('/opt',identifier).exists();assert not Path('/usr/bin',identifier).exists()
            else:
                run(['flatpak','uninstall','--user','--noninteractive','--assumeyes',identifier]);assert subprocess.run(['flatpak','info','--user',identifier],capture_output=True).returncode!=0
            installed=False;records['steps'].append('Remoção real; programa e instalação não permanecem')
        else:
            artifact.unlink();assert not artifact.exists();records['steps'].append('AppImage removido após encerramento')
        records['ok']=True;(output/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));print(json.dumps(records,ensure_ascii=False),flush=True)
        return 0
    finally:
        if process and process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5)
            except (ProcessLookupError,subprocess.TimeoutExpired):
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        server.terminate();server.wait(timeout=5)


if __name__=='__main__':raise SystemExit(main())
