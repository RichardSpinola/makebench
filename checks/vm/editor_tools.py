"""Sonda confiável do runtime do editor; não importa projetos do usuário."""
import json
import ssl


def probe():
    """Exerce o bootstrap real e ferramentas do host, mantendo certificados do destino."""
    from makebench.core.build_environment import run_tool
    version=run_tool(['/usr/bin/flatpak','--version']).strip()
    run_tool(['/usr/bin/python3','-c',"import os; assert not os.environ.get('PYTHONHOME'); assert not os.environ.get('PYTHONPATH')"])
    certificates=ssl.create_default_context().cert_store_stats()['x509_ca']
    assert certificates>0,'Python portátil não encontrou certificados confiáveis do destino'
    print(json.dumps({'host_flatpak':version,'certificates':certificates,'host_python_clean':True}))
    return 0
