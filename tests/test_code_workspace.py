"""Contratos de módulos, edição inerte, recuperação e depuração por arquivo."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from makebench.core.project import Project,ProjectError,ComponentKind,LayoutKind
from makebench.core.source import SourceBuffer,SourceText,source_files,source_signature
from makebench.core.storage import StorageError,load_project,save_project
from makebench.core.document import Document
from makebench.core.bundle import write_bundle,read_bundle
from makebench.core.code_index import CodeIndex


class SourceWorkspaceTests(unittest.TestCase):
    """Persistência de vários arquivos preserva conteúdo e recusa conflitos reais."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.path=self.root/'project.makebench.json'
        self.doc=Document();self.doc.source.add_module('makebench_user/helpers.py','def soma(a, b):\n    return a+b\n');self.doc.source.text='from makebench_user.helpers import soma\n'

    def test_old_versions_and_manifest_upgrade_backup(self):
        old=Project.empty();save_project(old,self.path);before=self.path.read_bytes();restored=load_project(self.path)
        self.assertEqual(restored.to_dict()['format_version'],4);self.assertEqual(self.path.read_bytes(),before)
        self.doc.path=self.path;self.doc.save();self.assertEqual(load_project(self.path).to_dict()['format_version'],8)
        self.assertEqual(self.path.with_name(self.path.name+'.bak-v4').read_bytes(),before)
        self.assertEqual(source_files(SourceBuffer.load(self.path).text),source_files(self.doc.source.text));self.assertFalse(self.doc.dirty)
        data=self.doc.project.to_dict();data['format_version']=7
        with self.assertRaises(ProjectError):Project.from_dict(data)

    def test_externally_changed_module_prevents_all_writes(self):
        self.doc.save(self.path);entry=self.doc.source.path;before=entry.read_bytes()
        (self.root/'makebench_user/helpers.py').write_text('# outra edição\n');self.doc.source.text='# entrada modificada\n'
        with self.assertRaisesRegex(ProjectError,'fora do Makebench'):self.doc.save()
        self.assertEqual(entry.read_bytes(),before);self.assertTrue(self.doc.dirty)

    def test_save_as_keeps_deleted_original_module(self):
        self.doc.save(self.path);original=self.root/'makebench_user/helpers.py';self.doc.source.remove_module('makebench_user/helpers.py')
        other=self.root/'other';other.mkdir();self.doc.save(other/'project.makebench.json')
        self.assertTrue(original.exists());self.assertNotIn('makebench_user/helpers.py',load_project(other/'project.makebench.json').python_files)

    def test_failed_json_preserves_deleted_file_and_retry(self):
        self.doc.save(self.path);original=self.root/'makebench_user/helpers.py';self.doc.source.remove_module('makebench_user/helpers.py')
        with patch('makebench.core.storage.save_project',side_effect=OSError('Sem espaço')):
            with self.assertRaisesRegex(StorageError,'Python.*já foram gravados.*não'):self.doc.save()
        self.assertTrue(original.exists());self.assertTrue(self.doc.dirty)
        self.doc.save();self.assertFalse(original.exists());self.assertFalse(self.doc.dirty)

    def test_symlink_parent_and_invalid_names_are_rejected(self):
        for name in ['../outside.py','makebench_user/../outside.py','makebench_user//x.py','makebench_user/x.txt','makebench_user/class.py','/makebench_user/x.py']:
            with self.assertRaises(ProjectError,msg=name):self.doc.source.add_module(name)
        outside=self.root/'outside';outside.mkdir();(self.root/'makebench_user').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ProjectError):self.doc.save(self.path)
        self.assertFalse(any(outside.iterdir()))

    def test_missing_non_utf8_and_duplicate_modules(self):
        self.doc.save(self.path);path=self.root/'makebench_user/helpers.py';path.unlink()
        with self.assertRaisesRegex(ProjectError,'ausente'):SourceBuffer.load(self.path)
        path.write_bytes(b'\xff')
        with self.assertRaisesRegex(ProjectError,'UTF-8'):SourceBuffer.load(self.path)
        value=self.doc.project.to_dict();value['python_files'].append(value['python_files'][0])
        with self.assertRaises(ProjectError):Project.from_dict(value)

    def test_bundle_and_recovery_preserve_comments_invalid_source_and_ids(self):
        self.doc.source.modules['makebench_user/helpers.py'].text='# comentário\ndef incompleta(\n'
        self.doc.project.python_files=sorted(self.doc.source.modules);before=self.doc.project.to_dict()
        archive=self.root/'project.zip';write_bundle(self.doc.project,self.doc.source.text,lambda _:b'',archive)
        path=read_bundle(archive,self.root/'unpacked');restored=SourceBuffer.load(path)
        self.assertEqual(source_files(restored.text),source_files(self.doc.source.text));self.assertEqual(load_project(path).to_dict(),before)
        recovery=self.root/'recovery.json';self.doc.recovery(recovery);copy=Document.recover(recovery)
        self.assertEqual(source_files(copy.source.text),source_files(self.doc.source.text));self.assertTrue(copy.dirty)

    def test_rename_does_not_rewrite_imports_and_detects_destination_conflict(self):
        self.doc.save(self.path);before=str(self.doc.source.text)
        self.doc.source.rename_module('makebench_user/helpers.py','makebench_user/util.py');self.assertEqual(self.doc.source.text,before)
        (self.root/'makebench_user/util.py').write_text('# outro arquivo')
        with self.assertRaisesRegex(ProjectError,'destino'):self.doc.save()
        self.assertTrue((self.root/'makebench_user/helpers.py').exists())

    def test_rename_back_and_recreate_keep_ownership_and_detect_external_changes(self):
        self.doc.save(self.path);source=self.doc.source
        source.rename_module('makebench_user/helpers.py','makebench_user/util.py')
        source.modules['makebench_user/util.py'].text='# edição preservada\n'
        source.rename_module('makebench_user/util.py','makebench_user/helpers.py');self.doc.save()
        self.assertEqual((self.root/'makebench_user/helpers.py').read_text(),'# edição preservada\n')
        source.remove_module('makebench_user/helpers.py');source.add_module('makebench_user/helpers.py','# recriado\n')
        (self.root/'makebench_user/helpers.py').write_text('# alteração externa\n')
        with self.assertRaises(ProjectError):self.doc.save()

    def test_bundle_reports_missing_manifest_and_accepts_declared_directories(self):
        import zipfile
        archive=self.root/'invalid.zip'
        with zipfile.ZipFile(archive,'w') as output:output.writestr('other.txt','sem projeto')
        with self.assertRaisesRegex(ProjectError,'project.makebench.json'):read_bundle(archive,self.root/'invalid')
        self.doc.project.python_files=sorted(self.doc.source.modules);archive=self.root/'valid.zip'
        write_bundle(self.doc.project,self.doc.source.text,lambda _:b'',archive)
        with zipfile.ZipFile(archive,'a') as output:output.writestr('makebench_user/','')
        self.assertEqual(SourceBuffer.load(read_bundle(archive,self.root/'valid')).text,self.doc.source.text)

    def test_snapshot_signature_includes_unsaved_modules(self):
        snapshot=self.doc.source.text;before=source_signature(snapshot)
        self.doc.source.modules['makebench_user/helpers.py'].text='# novo texto\n'
        self.assertEqual(source_signature(snapshot),before);self.assertNotEqual(source_signature(self.doc.source.text),before)


class CodeIndexTests(unittest.TestCase):
    """Índice não importa módulos e conserva definições durante erro de sintaxe."""
    def setUp(self):
        self.index=CodeIndex();self.source=SourceText('from makebench_user.helpers import soma as add\nimport makebench_user.helpers as helper\n',{'makebench_user/__init__.py':'','makebench_user/helpers.py':'def soma(a, b=1):\n    """Soma valores."""\n    return a+b\n'})

    def test_completion_signatures_and_definitions(self):
        self.index.update(self.source)
        self.assertIn('ctx.terminal_start',dict(self.index.complete('@actions','ctx.term')))
        target=self.index.resolve('@actions','add');self.assertEqual(target.file,'makebench_user/helpers.py');self.assertEqual(target.line,1)
        self.assertEqual(self.index.resolve('@actions','helper.soma'),target)
        self.assertIn('a, b=1',self.index.call_signature('@actions','add('));self.assertIn('helper.soma',dict(self.index.complete('@actions','helper.s')))

    def test_last_valid_index_and_broken_import_after_rename(self):
        self.index.update(self.source);self.source.modules['makebench_user/helpers.py']='def soma(\n'
        self.index.update(self.source);self.assertIsNotNone(self.index.resolve('@actions','add'));self.assertTrue(self.index.errors)
        del self.source.modules['makebench_user/helpers.py'];self.source.modules['makebench_user/util.py']=''
        self.index.update(self.source);self.assertIsNone(self.index.resolve('@actions','add'));self.assertTrue(any('Referência local' in e['message'] for e in self.index.errors))

    def test_index_does_not_execute_top_level(self):
        source=SourceText('raise RuntimeError("não executar")\nimport makebench_user.helpers\n',dict(self.source.modules))
        with patch('subprocess.Popen') as process:self.index.update(source);process.assert_not_called()
        self.assertFalse(self.index.errors)



class ModuleWorkerTests(unittest.TestCase):
    """Imports e breakpoints reais operam na cópia iniciada, inclusive imports tardios."""
    def make_worker(self,text=None):
        from test_terminal_debug import WorkerHarness
        from makebench.core.logic import create_flow
        from makebench.core.logic_defaults import literal
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        root=Path(directory.name);(root/'makebench_user').mkdir();(root/'makebench_user/__init__.py').write_text('')
        (root/'makebench_user/helpers.py').write_text('raise AssertionError("não ler disco")\n')
        source=SourceText('def action(ctx, value):\n    from makebench_user.helpers import calculate\n    ctx.variables["result"]=calculate(value)\n',{'makebench_user/__init__.py':'','makebench_user/helpers.py':text or 'def calculate(value):\n    result=value+5\n    return result\n'})
        project=Project.empty();project.python_files=sorted(source.modules);flow=create_flow(project,project.root.id);flow['body']=[{'id':'call','op':'call','function':'action','value':literal(4)}]
        worker=WorkerHarness(project,source,str(root));self.addCleanup(worker.close)
        worker.send({'type':'event','flow':flow['id'],'window':project.root.id});worker.until(lambda m:m['type']=='debug' and m['state']=='paused')
        return worker,root

    def test_module_breakpoint_stack_variables_and_late_import_snapshot(self):
        worker,root=self.make_worker()
        worker.command('breakpoints',items=[{'file':'source','path':'makebench_user/helpers.py','line':3}]);worker.command('continue')
        paused=worker.until(lambda m:m['type']=='debug' and m['state']=='paused')
        self.assertEqual(paused['source_file'],'makebench_user/helpers.py');self.assertEqual(paused['source_line'],3)
        self.assertEqual(paused['stack'][0]['variables']['result'],9)
        self.assertEqual(paused['stack'][1]['source_file'],'@actions')
        worker.command('continue');self.assertEqual(worker.until(lambda m:m['type']=='done')['outcome'],'success')

    def test_error_origin_is_deepest_module(self):
        worker,_=self.make_worker('def calculate(value):\n    raise ValueError("falha localizada")\n')
        worker.command('continue')
        with self.assertRaises(AssertionError) as raised:worker.until(lambda m:m['type']=='done')
        error=raised.exception.args[0];self.assertEqual(error['source_file'],'makebench_user/helpers.py');self.assertEqual(error['source_line'],2)


class ModuleExportTests(unittest.TestCase):
    """Os dois exportadores incluem arquivos declarados e mantêm a fonte inerte."""
    def test_both_source_backends_include_modules_and_no_top_level_execution(self):
        import zipfile
        from makebench.core.exporter import export_source
        for backend in ('qt','gtk'):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);example=Path(__file__).resolve().parents[1]/'examples/python-modules'/backend;path=example/'project.makebench.json'
                project=load_project(path);source=SourceBuffer.load(path).text
                marker=root/'executed';source=SourceText(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n'+str(source),source.modules)
                archive=root/'app.zip';export_source(project,source,lambda name:(example/name).read_bytes(),archive)
                self.assertFalse(marker.exists())
                with zipfile.ZipFile(archive) as package:
                    self.assertTrue(set(project.python_files)<=set(package.namelist()))
                    for name in project.python_files:self.assertEqual(package.read(name).decode(),source.modules[name])
                    self.assertIn('makebench/core/source_runtime.py',package.namelist())
                source.modules['makebench_user/calculations.py']='def broken(\n'
                with self.assertRaises(ProjectError):export_source(project,source,lambda name:(example/name).read_bytes(),root/'invalid.zip')

    def test_module_and_package_collision_is_rejected(self):
        source=SourceBuffer();source.add_module('makebench_user/helpers.py')
        with self.assertRaises(ProjectError):source.add_module('makebench_user/helpers/extra.py')

if __name__=='__main__':unittest.main()
