"""Jornadas de edição Qt para arquivos Python e propriedades comuns."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from makebench.core.project import Project,ComponentKind,LayoutKind
from makebench.core.storage import load_project


class CodeWorkspaceInterfaceTests(unittest.TestCase):
    """Edição real de múltiplos arquivos e propriedades coletivas com histórico."""
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([]);cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from makebench.editor.window import MainWindow
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'XDG_STATE_HOME':str(self.root/'state'),'XDG_CONFIG_HOME':str(self.root/'config')});self.env.start();self.addCleanup(self.env.stop)
        self.window=MainWindow(Project.empty());self.window.recovery_timer.stop();self.window._created_here=True
        self.window._show_error=lambda message:self.fail(message)

    def tearDown(self):
        self.window.history.mark_saved();self.window.source.mark_saved();self.window.close();self.app.processEvents();self.window.deleteLater();self.app.processEvents()

    def test_tabs_module_undo_save_reopen_and_generated_readonly(self):
        w=self.window;w.add_code_module('makebench_user/helpers.py','# comentário\n')
        editor=w.module_editors['makebench_user/helpers.py'];editor.appendPlainText('value = 2');self.assertIn('value = 2',w.source.modules['makebench_user/helpers.py'].text)
        w.undo();self.assertNotIn('value = 2',w.source.modules['makebench_user/helpers.py'].text);w.redo()
        path=self.root/'project.makebench.json';self.assertTrue(w.save_to(path));self.assertFalse(w.source.dirty)
        w._replace_project(load_project(path),path);self.assertIn('value = 2',w.module_editors['makebench_user/helpers.py'].toPlainText());self.assertTrue(w.generated_editor.isReadOnly())

    def test_batch_mixed_properties_single_undo_preserves_widgets_and_zoom(self):
        from PySide6.QtWidgets import QLineEdit
        w=self.window;w.project.root.layout=LayoutKind.FREE
        a=w.project.add(w.project.root.id,ComponentKind.BUTTON);b=w.project.add(w.project.root.id,ComponentKind.BUTTON);a.properties['text']='A';b.properties['text']='B';w.history.push(w.project);w._refresh();w.set_mode('Design');w.select_multiple([a.id,b.id])
        field=w.inspector.findChild(QLineEdit,'batch_text');self.assertEqual(field.placeholderText(),'Múltiplos valores')
        frames={name:widget for name,widget in w.canvas._frames.items()};zoom=w.zoom_view.zoom;before=w.history._index
        w.change_multiple_properties('text','Mesmo texto')
        self.assertEqual(w.history._index,before+1);self.assertEqual(w.project.find(a.id).properties['text'],'Mesmo texto');self.assertEqual(w.project.find(b.id).properties['text'],'Mesmo texto')
        self.assertEqual(frames,w.canvas._frames);self.assertEqual(w.zoom_view.zoom,zoom);self.assertEqual(w.selected_ids,{a.id,b.id})
        w.undo();self.assertEqual(w.project.find(a.id).properties['text'],'A');self.assertEqual(w.project.find(b.id).properties['text'],'B')

    def test_incompatible_layout_disables_alignment_with_explanation(self):
        from PySide6.QtWidgets import QToolButton
        w=self.window;a=w.project.add(w.project.root.id,ComponentKind.BUTTON);b=w.project.add(w.project.root.id,ComponentKind.BUTTON);w._refresh();w.select_multiple([a.id,b.id])
        button=w.inspector.findChild(QToolButton,'selection_left');self.assertFalse(button.isEnabled());self.assertIn('Livre',button.toolTip())

    def test_module_diagnostics_navigate_and_snapshot_changes(self):
        w=self.window;w.add_code_module('makebench_user/helpers.py','def calculate(value):\n    return value+1\n');before=w.execution_fingerprint()
        w.module_editors['makebench_user/helpers.py'].setPlainText('def calculate(\n');w._update_actions()
        self.assertNotEqual(w.execution_fingerprint(),before);targets=[w.problems.item(i) for i in range(w.problems.count())];item=next(i for i in targets if i.data(256).get('source_file')=='makebench_user/helpers.py')
        w.go_to_problem(item);self.assertIs(w.active_code_editor(),w.module_editors['makebench_user/helpers.py'])

    def test_completion_enter_undo_and_component_suggestions(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        w=self.window;w.show();w.set_mode('Código');editor=w.source_editor
        editor.setPlainText('def action(ctx, value):\n    ctx.term');editor.moveCursor(editor.textCursor().MoveOperation.End);editor.setFocus();QTest.qWait(20)
        QTest.keyClick(editor,Qt.Key.Key_Space,Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(w._entry_assist.popup.isVisible());self.assertEqual(w._entry_assist.popup.count(),3)
        QTest.keyClick(editor,Qt.Key.Key_Return);self.assertIn('ctx.terminal_send',editor.toPlainText());self.assertFalse(w._entry_assist.popup.isVisible())
        w.undo();self.assertTrue(editor.toPlainText().endswith('ctx.term'))
        node=w.project.add(w.project.root.id,ComponentKind.BUTTON);node.properties['code_name']='executar'
        editor.setPlainText("ctx.set_text('exe");editor.moveCursor(editor.textCursor().MoveOperation.End)
        QTest.keyClick(editor,Qt.Key.Key_Space,Qt.KeyboardModifier.ControlModifier);self.assertEqual(w._entry_assist.popup.count(),1)
        QTest.keyClick(editor,Qt.Key.Key_Return);self.assertIn(node.id,editor.toPlainText())

    def test_f12_and_outline_use_active_module(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        w=self.window;w.show();w.add_code_module('makebench_user/helpers.py','def calculate(value):\n    return value+1\n')
        w.source_editor.setPlainText('from makebench_user.helpers import calculate\n\ndef action(ctx, value):\n    return calculate(value)\n');w.open_code_file('@actions',4)
        cursor=w.source_editor.textCursor();cursor.movePosition(cursor.MoveOperation.Right,cursor.MoveMode.MoveAnchor,15);w.source_editor.setTextCursor(cursor)
        QTest.keyClick(w.source_editor,Qt.Key.Key_F12)
        self.assertIs(w.active_code_editor(),w.module_editors['makebench_user/helpers.py'])
        self.assertIn('calculate',w.function_outline.item(0).text());self.assertEqual(w.code_tree.currentItem().data(0,Qt.ItemDataRole.UserRole),'makebench_user/helpers.py')
        with patch('makebench.editor.development.QInputDialog.getText',return_value=('other',True)):w.new_function()
        self.assertIn('def other',w.source.modules['makebench_user/helpers.py'].text);self.assertNotIn('def other',w.source.text)

    def test_batch_defaults_enabled_and_grid_keyboard(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QCheckBox
        w=self.window;w.project.root.layout=LayoutKind.FREE;a=w.project.add(w.project.root.id,ComponentKind.BUTTON);b=w.project.add(w.project.root.id,ComponentKind.BUTTON);w._refresh();w.set_mode('Design');w.select_multiple([a.id,b.id])
        self.assertIsNotNone(w.inspector.findChild(QCheckBox,'batch_enabled'));w.change_multiple_properties('enabled',False)
        self.assertFalse(w.project.find(a.id).properties['enabled']);self.assertFalse(w.project.find(b.id).properties['enabled'])
        w.select_multiple([a.id]);before=w.project.find(a.id).geometry['x'];w.snap_check.setChecked(True);QTest.keyClick(w.canvas,Qt.Key.Key_Right)
        self.assertEqual(w.project.find(a.id).geometry['x'],before+8)
        w.snap_check.setChecked(False);QTest.keyClick(w.canvas,Qt.Key.Key_Right);self.assertEqual(w.project.find(a.id).geometry['x'],before+9)
