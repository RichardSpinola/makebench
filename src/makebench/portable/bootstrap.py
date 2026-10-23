"""Entrada confiável do pacote relocável; não lê nem importa projetos na preparação."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys


def main():
    """Configura dados/typelibs relativos ao pacote e inicia o aplicativo explicitamente."""
    root=Path(__file__).resolve().parent
    usr=root/'usr';site=usr/'lib/python3.12/site-packages'
    environment=os.environ
    controlled=('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','PATH','GI_TYPELIB_PATH','GIO_MODULE_DIR','GSETTINGS_SCHEMA_DIR','XDG_DATA_DIRS','FONTCONFIG_FILE','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QTWEBENGINEPROCESS_PATH','GDK_PIXBUF_MODULEDIR','GDK_PIXBUF_MODULE_FILE')
    original={key:environment.get(key) for key in controlled}
    for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','PATH'):original[key]=environment.get('MAKEBENCH_ORIGINAL_'+key) or None
    environment['MAKEBENCH_ORIGINAL_ENV']=json.dumps(original)
    environment['MAKEBENCH_PORTABLE_ROOT']=str(root)
    # O Python incluído usa certificados confiados pela distribuição de destino.
    if not environment.get('SSL_CERT_FILE'):
        for candidate in ('/etc/ssl/certs/ca-certificates.crt','/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem','/etc/pki/tls/certs/ca-bundle.crt','/etc/ssl/cert.pem'):
            if Path(candidate).is_file():environment['SSL_CERT_FILE']=candidate;break
    environment['GI_TYPELIB_PATH']=str(usr/'lib/girepository-1.0')
    environment['GIO_MODULE_DIR']=str(usr/'lib/gio/modules')
    environment['GSETTINGS_SCHEMA_DIR']=str(usr/'share/glib-2.0/schemas')
    environment['XDG_DATA_DIRS']=str(usr/'share')+':'+environment.get('XDG_DATA_DIRS','/usr/local/share:/usr/share')
    environment['FONTCONFIG_FILE']=str(usr/'etc/fonts/fonts.conf')
    environment['QT_PLUGIN_PATH']=str(site/'PySide6/Qt/plugins')
    environment['QTWEBENGINEPROCESS_PATH']=str(site/'PySide6/Qt/libexec/QtWebEngineProcess')
    loaders=usr/'bin/gdk-pixbuf-query-loaders'
    if loaders.exists():
        environment['GDK_PIXBUF_MODULEDIR']=str(usr/'lib/gdk-pixbuf-2.0/2.10.0/loaders')
        cache=Path(environment.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'makebench-runtime'/hashlib.sha256(str(root).encode()).hexdigest()[:20]
        cache.mkdir(parents=True,exist_ok=True);destination=cache/'loaders.cache'
        if not destination.is_file():
            result=subprocess.run([str(loaders)],capture_output=True,env=environment)
            if result.returncode==0:destination.write_bytes(result.stdout)
        if destination.is_file():environment['GDK_PIXBUF_MODULE_FILE']=str(destination)
    sys.path.insert(0,str(root/'app'))
    if (root/'editor-entry').exists():
        from makebench.__main__ import main as start
        return start()
    import runpy
    sys.argv=[str(root/'app/run.py'),*sys.argv[1:]]
    runpy.run_path(str(root/'app/run.py'),run_name='__main__')
    return 0


if __name__=='__main__':raise SystemExit(main())
