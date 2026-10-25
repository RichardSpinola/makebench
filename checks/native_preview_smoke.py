# SPDX-License-Identifier: GPL-3.0-or-later
"""Real GTK in the Designer: selection and visual changes never run project actions."""

import os, tempfile, time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
tmp = tempfile.TemporaryDirectory()
os.environ["XDG_CONFIG_HOME"] = tmp.name + "/config"
os.environ["XDG_STATE_HOME"] = tmp.name + "/state"
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from makebench.core.project import Project, ComponentKind, LayoutKind
from makebench.editor.window import MainWindow
from native_palette import kde_palette

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
app.setPalette(kde_palette("dark"))
p = Project.empty("Janela GTK nativa")
button = p.add(p.root.id, ComponentKind.BUTTON)
button.properties["text"] = "GTK button"
p.application["backend"] = "gtk"
w = MainWindow(p)
marker = Path(tmp.name) / "nao-executar"
w.source.text = f"from pathlib import Path\nPath({str(marker)!r}).write_text('erro')\n"
w.source_editor.setPlainText(w.source.text)
w.show()
w.set_mode("design")
surface = w.canvas.gtk_surface


def wait(predicate):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        QTest.qWait(20)
        if predicate():
            return
    raise AssertionError(surface.error)


try:
    wait(lambda: not surface.image.isNull())
    assert not marker.exists()
    assert button.id in surface.rectangles, surface.rectangles
    QTest.mouseClick(surface, Qt.MouseButton.LeftButton, pos=surface.rectangles[button.id].center())
    assert w.selected_id == button.id
    assert "source" not in surface.payload and "workflows" not in surface.payload
    old = surface.image.cacheKey()
    w._change_property(button.id, "text", "Alterado no GTK")
    wait(lambda: surface.image.cacheKey() != old and surface.job is None)
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
        w.grab().save(str(out / "design-gtk-nativo.png"))
    p.root.layout = LayoutKind.FREE
    w._refresh()
    wait(lambda: surface.job is None and not surface.timer.isActive())
    origin = surface.rectangles[button.id].center()
    before = dict(p.find(button.id).geometry)
    old = surface.image.cacheKey()
    from PySide6.QtCore import QPoint

    QTest.mousePress(surface, Qt.MouseButton.LeftButton, pos=origin)
    QTest.mouseMove(surface, origin + QPoint(32, 24))
    QTest.mouseRelease(surface, Qt.MouseButton.LeftButton, pos=origin + QPoint(32, 24))
    assert w.project.find(button.id).geometry["x"] == before["x"] + 32
    wait(lambda: surface.image.cacheKey() != old and surface.job is None)
    assert not marker.exists()
    w.project.application["backend"] = "qt"
    w._refresh()
    QTest.qWait(60)
    assert not surface.isVisible()
    if out:
        w.grab().save(str(out / "design-qt-nativo.png"))
    print(
        "OK: real GTK image, native areas, selection, updated property, free movement, inert preview and return to Qt without imitation."
    )
finally:
    w.history.mark_saved()
    w.source.mark_saved()
    w.close()
    w.deleteLater()
    app.processEvents()
