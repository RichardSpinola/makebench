"""Preparação isolada: integridade das rodas, limites dos comandos e cancelamento."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from makebench.core.project import Project,ProjectError
from makebench.core.exporter import BuildCancelled
from makebench.core.build_environment import (prepared,container_command,run_tool,flatpak_wheels,copy_flatpak_wheels,flatpak_requirements,IMAGE)


class BuildEnvironmentTests(unittest.TestCase):
    """Valida fronteiras que impedem builds parciais, rede implícita e cache alterado."""
    def setUp(self):
        """Cache descartável não altera recibos nem ferramentas do proprietário."""
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.environment=patch.dict(os.environ,{'XDG_CACHE_HOME':str(self.root)});self.environment.start();self.addCleanup(self.environment.stop)

    def test_receipt_query_is_readonly_and_container_mounts_only_stage(self):
        """Abrir Publicar não inicia ferramentas e o build não monta a pasta pessoal."""
        root=self.root/'makebench/builders';root.mkdir(parents=True);(root/'tools.json').write_text(json.dumps({'image':IMAGE}))
        with patch('subprocess.Popen') as process,patch('subprocess.run') as run:
            self.assertTrue(prepared());process.assert_not_called();run.assert_not_called()
        stage=self.root/'staging';stage.mkdir()
        with patch('shutil.which',return_value='/usr/bin/podman'):command=container_command(['dpkg-deb','--build',str(stage/'payload'),str(stage/'app.deb')],stage)
        self.assertIn('--network=none',command);self.assertIn('--read-only',command);self.assertIn('/work/payload',command)
        self.assertEqual(command.count('--volume'),1);self.assertEqual(command[command.index('--volume')+1],str(stage)+':/work:rw,Z')

    def test_wheel_integrity_is_checked_before_copy(self):
        """Dependência alterada entre preparação e construção é rejeitada."""
        p=Project.empty();p.application['backend']='qt';cache=flatpak_wheels(p);cache.mkdir(parents=True)
        wheel=cache/'example-1.0-py3-none-any.whl';wheel.write_bytes(b'bytes originais')
        (cache/'receipt.json').write_text(json.dumps({'files':{wheel.name:hashlib.sha256(wheel.read_bytes()).hexdigest()}}))
        copy_flatpak_wheels(p,self.root/'ok');self.assertEqual((self.root/'ok'/wheel.name).read_bytes(),wheel.read_bytes())
        wheel.write_bytes(b'alterado')
        with self.assertRaisesRegex(ProjectError,'alterada'):copy_flatpak_wheels(p,self.root/'falha')

    def test_python_dependencies_cannot_be_pip_options_or_urls(self):
        """Preparação baixa rodas binárias por nomes, sem fontes ou hooks do projeto."""
        p=Project.empty()
        for dependency in ['--index-url=https://example.com','https://example.com/pkg.whl','./pacote','name @ https://example.com/a.whl']:
            p.application['packages']=[dependency]
            with self.assertRaises(ProjectError):flatpak_requirements(p)
        p.application['packages']=['requests>=2.32,<3'];self.assertIn('requests>=2.32,<3',flatpak_requirements(p))

    def test_cancel_stops_tool_and_returns_no_success(self):
        """Cancelamento interrompe a ferramenta em vez de aguardar ou publicar sucesso."""
        start=time.monotonic()
        with self.assertRaises(BuildCancelled):run_tool([sys.executable,'-c','import time; time.sleep(20)'],cancelled=lambda:time.monotonic()-start>.2)
        self.assertLess(time.monotonic()-start,3)
