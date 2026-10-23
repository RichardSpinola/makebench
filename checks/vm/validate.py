"""Orquestra testes reais no convidado; nunca instala artefatos no host."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from machine import Machine


def main():
    """Copia artefato e rotina; traz evidências reais inclusive quando o teste falha."""
    parser = argparse.ArgumentParser()
    parser.add_argument('machine', type=Path)
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--format', choices=('deb', 'rpm', 'appimage', 'flatpak', 'editor'), required=True)
    parser.add_argument('--backend', choices=('qt', 'gtk'), default='qt')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--project-dir', type=Path)
    parser.add_argument('--quick-close', action='store_true')
    args = parser.parse_args()
    if (args.output/'results.json').exists():raise RuntimeError('Escolha uma pasta nova para não sobrescrever evidências anteriores.')
    machine = Machine(args.machine)
    root = '/home/qa/case-' + args.backend + '-' + args.format
    machine.ssh('mkdir -p ' + shlex.quote(root))
    machine.copy_to(Path(__file__).with_name('guest.py'), '/home/qa/guest-check.py')
    machine.copy_to(Path(__file__).with_name('editor_tools.py'), '/home/qa/editor-tools.py')
    machine.copy_to(args.artifact, root + '/' + args.artifact.name)
    arguments = ['python3', '/home/qa/guest-check.py', root + '/' + args.artifact.name,
                 '--format', args.format, '--backend', args.backend, '--output', root + '/evidence']
    if args.project_dir:
        for file in args.project_dir.rglob('*'):
            if file.is_file():
                target = root + '/project/' + file.relative_to(args.project_dir).as_posix()
                machine.ssh('mkdir -p ' + shlex.quote(str(Path(target).parent)))
                machine.copy_to(file, target)
        arguments += ['--project', root + '/project/project.makebench.json']
    if args.quick_close:arguments += ['--quick-close']
    try:
        machine.ssh(shlex.join(arguments), timeout=1800)
    finally:
        args.output.mkdir(parents=True, exist_ok=True)
        subprocess.run(['scp', '-r', '-F', '/dev/null', '-i', str(machine.root/'qa-key'),
                        '-o', 'IdentitiesOnly=yes', '-o', 'UserKnownHostsFile='+str(machine.root/'known_hosts'),
                        '-P', str(machine.receipt['port']), 'qa@127.0.0.1:'+root+'/evidence/.', str(args.output)], check=True)
    result = json.loads((args.output/'results.json').read_text())
    with args.artifact.open('rb') as binary:
        result['artifact_sha256'] = hashlib.file_digest(binary, 'sha256').hexdigest()
    (args.output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
