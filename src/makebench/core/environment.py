"""Detecção somente leitura de bibliotecas e ferramentas opcionais."""

import importlib.util
import shutil

GTK_HELP = "GTK4 não está disponível neste Python. Debian/Ubuntu: python3-gi, gir1.2-gtk-4.0 e, opcionalmente, gir1.2-adw-1. Fedora: python3-gobject, gtk4 e, opcionalmente, libadwaita. Instale pelo gerenciador da sua distribuição; o Makebench não instala pacotes."


def gtk_support():
    """Detecta introspecção sem inicializar GTK, abrir janelas ou iniciar processos."""
    result = {"pygobject": False, "gtk4": False, "adwaita": False, "reason": ""}
    try:
        import gi

        result["pygobject"] = True
        gi.require_version("Gtk", "4.0")
        result["gtk4"] = True
        try:
            gi.require_version("Adw", "1")
            result["adwaita"] = True
        except (ValueError, ImportError):
            pass
    except (ValueError, ImportError) as exc:
        result["reason"] = str(exc)
    return result


def build_tools():
    """Retorna caminhos de ferramentas sem instalar ou executar qualquer uma."""
    return {
        name: shutil.which(name)
        for name in (
            "dpkg-deb",
            "appimagetool",
            "flatpak-builder",
            "appstreamcli",
            "flatpak-builder-lint",
            "rpmbuild",
            "pkexec",
        )
    }
