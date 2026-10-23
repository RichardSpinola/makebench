"""Matriz real em compositor Wayland privado; não muda a escala do proprietário."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def main():
    """Testa os dois toolkits em 100/125/150%, isolando compositor e configurações."""
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--check',choices=('terminal','graph'),default='terminal');args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    results=[]
    for scale in ('1','1.25','1.5'):
        with tempfile.TemporaryDirectory(prefix='makebench-wayland-',ignore_cleanup_errors=True) as directory:
            root=Path(directory);runtime=root/'runtime';runtime.mkdir(mode=0o700)
            environment=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),XDG_CONFIG_HOME=str(root/'config'),XDG_STATE_HOME=str(root/'state'),QT_QPA_PLATFORM='wayland',GDK_BACKEND='wayland',GSK_RENDERER='cairo',LIBGL_ALWAYS_SOFTWARE='1')
            for key in ('QT_SCALE_FACTOR','GDK_SCALE','GDK_DPI_SCALE','WAYLAND_DISPLAY','DISPLAY'):environment.pop(key,None)
            with (output/f'compositor-{scale}.log').open('w') as log:
                compositor=subprocess.Popen(['dbus-run-session','--',sys.executable,'checks/private_compositor.py','--virtual','--width','1920','--height','1200','--scale',scale,'--socket','makebench-test','--no-global-shortcuts','--no-lockscreen','--no-kactivities'],env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    deadline=time.monotonic()+12
                    while not (runtime/'makebench-test').exists():
                        if compositor.poll() is not None:raise RuntimeError('Compositor privado não iniciou')
                        if time.monotonic()>deadline:raise RuntimeError('Prazo do compositor privado excedido')
                        time.sleep(.1)
                    environment['WAYLAND_DISPLAY']='makebench-test'
                    environment.update(json.loads((runtime/'private-bus.json').read_text()))
                    info=subprocess.run(['kscreen-doctor','-j'],env=environment,capture_output=True,text=True,check=True,timeout=10)
                    outputs=json.loads(info.stdout)['outputs']
                    assert len(outputs)==1 and outputs[0]['name'].lower().startswith('virtual'),outputs
                    subprocess.run(['kscreen-doctor',f"output.{outputs[0]['id']}.scale.{scale}"],env=environment,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=10)
                    time.sleep(.3)
                    configured=json.loads(subprocess.run(['kscreen-doctor','-j'],env=environment,capture_output=True,text=True,check=True,timeout=10).stdout)['outputs'][0]['scale']
                    assert abs(configured-float(scale))<.01,configured
                    for backend in ('qt','gtk'):
                        for theme in ('light','dark'):
                            target=output/f'{backend}-{theme}-{scale}';target.mkdir(exist_ok=True)
                            with (target/'run.log').open('w') as runlog:
                                result=subprocess.run([sys.executable,'checks/graph_acceptance.py' if args.check=='graph' else 'checks/terminal_debug_acceptance.py','--backend',backend,'--theme',theme,'--output',str(target)],env=environment,stdout=runlog,stderr=subprocess.STDOUT,timeout=75)
                            if result.returncode:raise RuntimeError(f'Falha em {target.name}')
                            data=json.loads((target/'results.json').read_text());data['output_scale']=configured
                            assert data['actual_scale']>=float(scale) and data['actual_scale']<=__import__('math').ceil(float(scale)),data
                            results.append(data);print('OK',target.name,data['actual_scale'],flush=True)
                finally:
                    try:os.killpg(compositor.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    subprocess.run(['fusermount3','-uz',str(runtime/'doc')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    try:compositor.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(compositor.pid,signal.SIGKILL);compositor.wait()
    (output/'matrix.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
