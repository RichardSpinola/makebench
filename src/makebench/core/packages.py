"""Receitas e construção de pacotes em staging, sem executar código do projeto."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET
from .exporter import export_source,verify,effects,BuildCancelled
from .project import ProjectError
from .environment import build_tools

FORMATS={'source':('Fonte Python',None,'.zip'),'deb':('DEB','dpkg-deb','.deb'),
    'appimage':('AppImage','appimagetool','.AppImage'),'flatpak':('Flatpak','flatpak-builder','.flatpak'),'rpm':('RPM','rpmbuild','.rpm')}


def one_line(value):
    """Metadados nunca injetam linhas de controle, comandos ou entradas desktop."""
    return re.sub(r'[\r\n\x00-\x1f]',' ',str(value)).strip()


def preflight(project,source,read_asset,format):
    """Inclui ferramentas e restrições explícitas por destino, sem executar builds."""
    issues=verify(project,source,read_asset);programs,admin=effects(project)
    tool=FORMATS[format][1]
    if tool and not build_tools().get(tool):issues.append({'level':'warning','message':f'Gerado, não construído (falta {tool}). A saída será uma receita ZIP.','field':'destinations'})
    if format=='flatpak' and (admin or programs):issues.append({'level':'error','message':'Flatpak isolado não permite programas do host ou ações administrativas declaradas. Use Fonte Python, DEB, RPM ou AppImage.','field':'permissions'})
    if format=='flatpak' and project.application.get('backend','qt')=='qt':issues.append({'level':'warning','message':'O manifesto Qt exige rodas PySide6 compatíveis fornecidas em wheels/; não há download implícito.','field':'dependencies'})
    if project.application.get('packages') and format!='source':issues.append({'level':'warning','message':'Pacotes Python adicionais precisam ser fornecidos para a distribuição alvo; o empacotador não instala dependências automaticamente.','field':'packages'})
    return issues


def policy_xml(project):
    """Declara a necessidade de autenticação sem conceder permissão automática.

    Não associa um executável genérico a um ID que permitiria elevar qualquer
    argumento sem confirmação. pkexec usa sua política padrão de autenticação.
    """
    app=project.application;root=ET.Element('policyconfig');action=ET.SubElement(root,'action',id=app['id']+'.admin')
    ET.SubElement(action,'description').text='Ação administrativa de '+app['name'];ET.SubElement(action,'message').text='Autorize a ação administrativa solicitada pelo aplicativo.'
    defaults=ET.SubElement(action,'defaults')
    for tag,value in [('allow_any','no'),('allow_inactive','no'),('allow_active','auth_admin')]:ET.SubElement(defaults,tag).text=value
    return '<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(root,encoding='unicode')+'\n'


def write_recipe(project,source,read_asset,format,root,progress=None,cancelled=None):
    """Gera entradas completas; a presença da receita nunca significa pacote pronto."""
    root=Path(root);root.mkdir(parents=True,exist_ok=True);app=project.application;identifier=app['id'];name=one_line(app['name']);version=app['version'];gtk=app.get('backend','qt')=='gtk';programs,admin=effects(project)
    export_source(project,source,read_asset,root/'source.zip',progress,cancelled)
    with zipfile.ZipFile(root/'source.zip') as z:z.extractall(root/'app')
    icon_ext=Path(app['icon']).suffix;icon_name=identifier+icon_ext
    desktop=f'[Desktop Entry]\nType=Application\nName={name}\nComment={one_line(app.get("description",""))}\nExec={identifier}\nIcon={identifier}\nTerminal=false\nCategories={one_line(app.get("category","Utility")).rstrip(";")};\n'
    (root/(identifier+'.desktop')).write_text(desktop,encoding='utf-8');(root/icon_name).write_bytes(read_asset(app['icon']))
    if admin:(root/(identifier+'.policy')).write_text(policy_xml(project),encoding='utf-8')
    payload=root/'payload';location=payload/'opt'/identifier;location.mkdir(parents=True)
    shutil.copytree(root/'app',location,dirs_exist_ok=True)
    binary=payload/'usr/bin'/identifier;binary.parent.mkdir(parents=True,exist_ok=True);binary.write_text('#!/bin/sh\nexec /usr/bin/python3 '+shlex.quote('/opt/'+identifier+'/run.py')+' "$@"\n');binary.chmod(0o755)
    for target,origin in [(payload/'usr/share/applications'/(identifier+'.desktop'),root/(identifier+'.desktop')),(payload/'usr/share/icons/hicolor'/('scalable' if icon_ext=='.svg' else '256x256')/'apps'/icon_name,root/icon_name)]:target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(origin,target)
    if admin:
        target=payload/'usr/share/polkit-1/actions'/(identifier+'.policy');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/(identifier+'.policy'),target)
    if format=='deb':
        control=payload/'DEBIAN';control.mkdir();deps='python3 (>= 3.13), python3-gi, gir1.2-gtk-4.0' if gtk else 'python3 (>= 3.13), python3-pyside6.qtwidgets'
        if admin:deps+=', policykit-1'
        text=f'Package: {identifier.replace("_","-")}\nVersion: {version}\nSection: utils\nPriority: optional\nArchitecture: amd64\nMaintainer: {one_line(app.get("author") or "Autor não informado")}\nDepends: {deps}\nDescription: {one_line(app.get("description") or name)}\n'
        (control/'control').write_text(text,encoding='utf-8')
        # Ubuntu 24.04 fornece Python 3.12; Python 3.13+ é requisito externo explícito.
    elif format=='rpm':
        spec=f'Name: {identifier.replace("_","-")}\nVersion: {version.split("-")[0].split("+")[0]}\nRelease: 1%{{?dist}}\nSummary: {one_line(app.get("description") or name)}\nLicense: {one_line(app.get("license") or "LicenseRef-unspecified")}\nBuildArch: x86_64\nRequires: python3 >= 3.13\n'
        spec+='Requires: python3-gobject, gtk4\n' if gtk else 'Requires: python3-pyside6\n'
        if admin:spec+='Requires: polkit\n'
        spec+='\n%description\n'+one_line(app.get('description') or name)+'\n\n%install\nmkdir -p %{buildroot}\ncp -a %{_sourcedir}/payload/. %{buildroot}/\n\n%files\n/opt/'+identifier+'\n/usr/bin/'+identifier+'\n/usr/share/applications/'+identifier+'.desktop\n/usr/share/icons/hicolor/*/apps/'+icon_name+'\n'
        if admin:spec+='/usr/share/polkit-1/actions/'+identifier+'.policy\n'
        # Os macros do template são controlados; texto livre não pode adicionar macros.
        for raw in (one_line(app.get('description') or name),one_line(app.get('license') or 'LicenseRef-unspecified')):
            if '%' in raw:raise ProjectError('Remova % dos metadados antes de gerar RPM; macros não são aceitos em texto livre.')
        (root/'app.spec').write_text(spec,encoding='utf-8')
    elif format=='appimage':
        appdir=root/'AppDir';shutil.copytree(root/'app',appdir/'app');shutil.copy2(root/(identifier+'.desktop'),appdir/(identifier+'.desktop'));shutil.copy2(root/icon_name,appdir/icon_name)
        launcher=appdir/'AppRun';launcher.write_text('#!/bin/sh\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec python3 "$HERE/app/run.py" "$@"\n');launcher.chmod(0o755)
        (root/'DEPENDENCIAS.txt').write_text('Este AppImage inclui o aplicativo e o runtime Makebench. Requer Python 3.13+ e '+('GTK4/PyGObject' if gtk else 'PySide6 6.11.2')+' instalados no sistema. Não é um runtime Python autocontido.\n',encoding='utf-8')
    elif format=='flatpak':
        runtime='org.gnome.Platform' if gtk else 'org.kde.Platform';sdk='org.gnome.Sdk' if gtk else 'org.kde.Sdk'
        manifest={'app-id':identifier,'runtime':runtime,'runtime-version':'50' if gtk else '6.10','sdk':sdk,'command':identifier,
            'finish-args':['--socket=wayland','--socket=fallback-x11','--share=ipc','--device=dri'],
            'modules':[{'name':'application','buildsystem':'simple','build-commands':['mkdir -p /app/share/'+identifier,'cp -a app/. /app/share/'+identifier+'/',
                'install -Dm755 flatpak-launcher /app/bin/'+identifier,'install -Dm644 '+identifier+'.desktop /app/share/applications/'+identifier+'.desktop',
                'install -Dm644 '+icon_name+' /app/share/icons/hicolor/'+('scalable' if icon_ext=='.svg' else '256x256')+'/apps/'+icon_name,
                'install -Dm644 '+identifier+'.metainfo.xml /app/share/metainfo/'+identifier+'.metainfo.xml'],
                'sources':[{'type':'dir','path':'.','skip':['payload','repo','build-dir','AppDir']}]}]}
        (root/(identifier+'.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (root/'flatpak-launcher').write_text('#!/bin/sh\nexec python3 /app/share/'+identifier+'/run.py "$@"\n');(root/'flatpak-launcher').chmod(0o755)
        metadata=ET.Element('component',type='desktop-application')
        for tag,value in [('id',identifier),('metadata_license','CC0-1.0'),('project_license',app.get('license') or 'LicenseRef-unspecified'),('name',name),('summary',one_line(app.get('description') or name)[:100])]:ET.SubElement(metadata,tag).text=value
        ET.SubElement(metadata,'launchable',type='desktop-id').text=identifier+'.desktop';description=ET.SubElement(metadata,'description');ET.SubElement(description,'p').text=one_line(app.get('description') or name)
        (root/(identifier+'.metainfo.xml')).write_text('<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(metadata,encoding='unicode'),encoding='utf-8')
    (root/'LEIA-ME-PACOTE.txt').write_text('Receita '+FORMATS[format][0]+' gerada pelo Makebench. Gerar não significa construir ou validar instalação.\nPython mínimo: 3.13. Ubuntu 24.04 fornece 3.12: forneça Python 3.13 por método adequado antes de instalar o DEB.\nNenhuma fonte do projeto foi executada. Dependências Python adicionais precisam ser fornecidas.\nPolítica Polkit não concede acesso automático; pkexec mantém autenticação padrão do sistema.\n',encoding='utf-8')
    return root


def build_package(project,source,read_asset,destination,format,progress=None,cancelled=None,recipe_only=False):
    """Constrói com ferramentas presentes; publica exclusivamente ao terminar e verificar."""
    if format=='source':return dict(export_source(project,source,read_asset,destination,progress,cancelled),status='Construído e verificado',format=format)
    issues=preflight(project,source,read_asset,format);errors=[i['message'] for i in issues if i['level']=='error']
    if errors:raise ProjectError('\n'.join(errors))
    destination=Path(destination)
    if destination.exists():raise ProjectError('O destino já existe. Escolha outro nome.')
    tool=FORMATS[format][1];available=build_tools().get(tool);recipe=recipe_only or not available
    def step(number,message):
        """Cancelamento acontece antes de publicar qualquer artefato no destino."""
        if cancelled and cancelled():raise BuildCancelled('Construção cancelada.')
        if progress:progress(number,message)
    def run(arguments,cwd):
        """Ferramenta explícita, sem shell; logs e cancelamento da árvore de build."""
        import selectors
        step(50,'Executar '+Path(arguments[0]).name)
        process=subprocess.Popen(arguments,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
        selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ);tail=[]
        try:
            while process.poll() is None or selector.get_map():
                if cancelled and cancelled():
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=.7)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                    raise BuildCancelled('Construção cancelada.')
                for key,_ in selector.select(.1):
                    data=os.read(key.fileobj.fileno(),8192)
                    if not data:selector.unregister(key.fileobj);continue
                    text=data.decode('utf-8',errors='replace');tail.append(text)
                    if progress:progress(65,text.rstrip())
            if process.returncode:raise ProjectError('Falha ao construir: '+''.join(tail)[-6000:])
        finally:selector.close();process.stdout.close()
    with tempfile.TemporaryDirectory(prefix='.makebench-package-',dir=destination.parent) as directory:
        root=write_recipe(project,source,read_asset,format,Path(directory)/'recipe',progress,cancelled);step(35,'Receita gerada')
        if recipe:
            result=Path(directory)/'recipe.zip'
            with zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as z:
                for path in sorted(root.rglob('*')):
                    if path.is_file():z.write(path,path.relative_to(root))
            status='Gerado, não construído ('+('receita solicitada' if available else 'falta '+tool)+')'
        else:
            if project.application.get('packages'):raise ProjectError('Forneça as dependências Python adicionais para o destino. Gere a receita para preparar uma construção offline.')
            identifier=project.application['id']
            if format=='deb':
                result=Path(directory)/'app.deb';run([available,'--build','--root-owner-group',str(root/'payload'),str(result)],root);run([available,'--info',str(result)],root);run([available,'--contents',str(result)],root)
            elif format=='appimage':
                result=Path(directory)/'app.AppImage';run([available,'--no-appstream',str(root/'AppDir'),str(result)],root)
                if result.read_bytes()[:4]!=b'\x7fELF':raise ProjectError('AppImage gerado não é um executável ELF.')
            elif format=='rpm':
                for name in ('BUILD','RPMS','SOURCES','SPECS','SRPMS'): (root/name).mkdir()
                shutil.copytree(root/'payload',root/'SOURCES'/'payload');run([available,'--define','_topdir '+str(root),'-bb',str(root/'app.spec')],root)
                packages=list((root/'RPMS').rglob('*.rpm'))
                if len(packages)!=1:raise ProjectError('A construção não produziu exatamente um RPM.')
                result=packages[0]
                if shutil.which('rpm'):run([shutil.which('rpm'),'-qip',str(result)],root)
            else:
                if project.application.get('backend','qt')=='qt':raise ProjectError('O Flatpak Qt exige rodas PySide6 offline. Gere a receita e forneça as dependências antes de construir.')
                if shutil.which('appstreamcli'):run([shutil.which('appstreamcli'),'validate','--no-net','--override=url-homepage-missing=info',str(root/(identifier+'.metainfo.xml'))],root)
                repo=Path(directory)/'repo';builddir=Path(directory)/'build-dir'
                run([available,'--disable-download','--force-clean','--repo='+str(repo),str(builddir),str(root/(identifier+'.json'))],root)
                flatpak=shutil.which('flatpak')
                if not flatpak:raise ProjectError('Falta flatpak para gerar o bundle final.')
                result=Path(directory)/'app.flatpak';run([flatpak,'build-bundle',str(repo),str(result),identifier],root)
            status='Construído e verificado (instalação no destino ainda não testada)'
        step(95,'Publicar resultado completo');os.link(result,destination)
    return {'path':str(destination),'size':destination.stat().st_size,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'status':status,'format':format}
