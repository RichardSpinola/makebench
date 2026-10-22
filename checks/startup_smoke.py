"""Inicializador real: WebEngine preparado, bancada oculta e X interno encerra."""
import os
import tempfile
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')


def main():
    """Exercita a entrada pública sem abrir projetos nem tocar nas preferências do autor."""
    with tempfile.TemporaryDirectory(prefix='makebench-startup-') as root:
        os.environ['XDG_CONFIG_HOME'] = root + '/config'
        os.environ['XDG_STATE_HOME'] = root + '/state'
        from PySide6.QtCore import Qt, QTimer
        from makebench.editor.startup import StartupDialog
        from makebench.__main__ import main as launch
        original = StartupDialog.show
        verified = []

        def show(dialog):
            """Fecha pela mesma ação usada pelo usuário após a primeira apresentação."""
            original(dialog)

            def close():
                """Confere a janela real e deixa Qt encerrar pelo último diálogo fechado."""
                verified.append(dialog.isVisible() and not dialog.window.isVisible()
                                and bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
                                and dialog.minimumSize() == dialog.maximumSize())
                dialog.banner.close_button.click()

            QTimer.singleShot(100, close)

        with patch('sys.argv', ['makebench']), patch.object(StartupDialog, 'show', show):
            assert launch() == 0
        assert verified == [True], verified
    print('OK: inicializador real fixo, sem moldura, bancada oculta e saída pelo X interno.')


if __name__ == '__main__':
    main()
