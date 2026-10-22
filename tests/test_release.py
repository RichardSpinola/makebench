"""Aceitação da primeira versão: paleta, modelos, GTK e pacotes inertes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtGui import QPalette,QColor
from PySide6.QtWidgets import QApplication
from makebench.ui.theme import derive_tokens,contrast,ThemeManager


class PaletteTests(unittest.TestCase):
    """O destaque segue a origem e continua visível nos dois esquemas."""
    @classmethod
    def setUpClass(cls):
        """Compartilha a aplicação de teste sem tocar em configurações do autor."""
        cls.app=QApplication.instance() or QApplication([])

    def test_simulated_accents_and_contrast(self):
        """Paletas diferentes alteram seleção; textos/controles têm razão mínima."""
        accents=[]
        for color in ('#3584e4','#26a269'):
            palette=QPalette();palette.setColor(QPalette.ColorRole.Accent,QColor(color))
            for dark in (False,True):
                t=derive_tokens(palette,dark,system_surfaces=False)
                accents.append(t['accent'])
                for key in ('text','muted','success','warning','error','info'):
                    for bg in ('panel','raised'):self.assertGreaterEqual(contrast(t[key],t[bg]),4.5,(key,bg,t))
                for bg in ('panel','raised'):
                    self.assertGreaterEqual(contrast(t['accent'],t[bg]),3)
                    self.assertGreaterEqual(contrast(t['control'],t[bg]),3)
                self.assertGreaterEqual(contrast(t['on_accent'],t['fill']),4.5)
        self.assertNotEqual(accents[0],accents[2])

    def test_theme_does_not_replace_system_palette(self):
        """Aplicar preferências não chama setPalette no aplicativo."""
        from unittest.mock import patch
        theme=getattr(self.app,'makebench_theme',None) or ThemeManager(self.app)
        with patch.object(self.app,'setPalette') as setter:
            theme.set_mode('dark');theme.set_accent('green');theme.set_mode('light')
            setter.assert_not_called()
        theme.set_accent('system');theme.set_mode('system')
