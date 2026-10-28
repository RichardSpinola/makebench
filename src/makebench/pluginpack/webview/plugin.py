# SPDX-License-Identifier: MIT
"""Official plugin: Web view windows, whose whole content is one HTML page.

It is also the reference for writing a plugin with API v2. It adds a project template and
three commands, and opens its own editing dialog. Makebench itself already knows how to show,
save and export a Web view window, so projects made with it keep working with the plugin off.
"""

from html import escape

from makebench.core.project import Project
from makebench.i18n import tr

PAGE = "web_page"
# Where the page waits while the window goes back to holding components.
SAVED_PAGE = "web_page_saved"


def starter_page(title):
    """A small welcome tour: plain HTML, CSS and a few lines of JavaScript."""
    steps = [
        (
            tr("Welcome"),
            tr("This window is a web page. Edit it with Plugins › Edit Web view page…"),
        ),
        (tr("Make it yours"), tr("Change the text, the colors in the style block or add images.")),
        (tr("All set"), tr("Run the application to try the buttons and links.")),
    ]
    sections = "\n".join(
        f"  <section{' hidden' if index else ''}>\n"
        f"    <h1>{escape(heading)}</h1>\n    <p>{escape(text)}</p>\n  </section>"
        for index, (heading, text) in enumerate(steps)
    )
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; --accent: #3584e4; }}
  body {{ margin: 0; font-family: system-ui, sans-serif; display: grid;
         place-items: center; min-height: 100vh; }}
  main {{ max-width: 34rem; padding: 2rem; text-align: center; }}
  h1 {{ color: var(--accent); }}
  button {{ font: inherit; padding: .5rem 1.5rem; border: 0; border-radius: .5rem;
           background: var(--accent); color: white; cursor: pointer; }}
</style>
</head>
<body>
<main>
{sections}
  <button id="next">{escape(tr("Next"))}</button>
</main>
<script>
  const sections = [...document.querySelectorAll("section")];
  let current = 0;
  document.getElementById("next").addEventListener("click", () => {{
    sections[current].hidden = true;
    current = (current + 1) % sections.length;
    sections[current].hidden = false;
  }});
</script>
</body>
</html>
"""


def register(api):
    def new_project(name):
        project = Project.empty(name)
        project.root.properties.update(width=760, height=520, web_page=starter_page(name))
        return project

    def make_web(project, context):
        window = project.find(context.window)
        if PAGE in window.properties:
            raise api.Refusal(tr("This window is already a Web view."))
        if window.children:
            raise api.Refusal(
                tr("A Web view shows only its page. Use an empty window or add a new one.")
            )
        title = window.properties.get("title", project.name)
        window.properties[PAGE] = window.properties.pop(SAVED_PAGE, None) or starter_page(title)

    def make_normal(project, context):
        window = project.find(context.window)
        if PAGE not in window.properties:
            raise api.Refusal(tr("This window is not a Web view."))
        # Keep the page, so turning the Web view on again brings it back.
        window.properties[SAVED_PAGE] = window.properties.pop(PAGE)

    def edit_page(project, context):
        window = project.find(context.window)
        if PAGE not in window.properties:
            raise api.Refusal(tr("Open a Web view window in Design first."))
        page = PageEditor(window.properties[PAGE], context).ask()
        if page is not None:
            window.properties[PAGE] = page

    api.add_template(
        tr("Web view"), tr("One window whose content is an HTML page you write."), new_project
    )
    api.add_command(tr("Edit Web view page…"), edit_page)
    api.add_command(tr("Turn this window into a Web view"), make_web)
    api.add_command(tr("Turn this Web view back into a normal window"), make_normal)


class PageEditor:
    """HTML on the left, the page as it will look on the right."""

    def __init__(self, html, context):
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QFontDatabase
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QPlainTextEdit,
            QPushButton,
            QSplitter,
            QVBoxLayout,
        )

        self.context = context
        self.dialog = QDialog(context.parent)
        self.dialog.setWindowTitle(tr("Edit Web view page"))
        self.dialog.resize(1100, 680)
        layout = QVBoxLayout(self.dialog)
        self.split = QSplitter()
        self.text = QPlainTextEdit(html)
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.setAccessibleName(tr("Page HTML"))
        self.split.addWidget(self.text)
        self.preview = None
        layout.addWidget(self.split, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        image = QPushButton(tr("Insert image…"))
        image.setEnabled(context.import_image is not None)
        image.clicked.connect(self.insert_image)
        buttons.addButton(image, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(self.dialog.accept)
        buttons.rejected.connect(self.dialog.reject)
        layout.addWidget(buttons)
        # Typing waits a moment before the preview reloads.
        self.timer = QTimer(self.dialog, singleShot=True, interval=400)
        self.timer.timeout.connect(self.show_preview)
        self.text.textChanged.connect(self.timer.start)
        self.show_preview()

    def show_preview(self):
        from makebench.ui.web import web_widget

        if self.preview is not None:
            self.preview.deleteLater()
        read = self.context.read_asset or (lambda _name: b"")
        self.preview = web_widget(self.text.toPlainText(), read)
        self.split.addWidget(self.preview)

    def insert_image(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        path, _ = QFileDialog.getOpenFileName(
            self.dialog, tr("Choose an image"), "", tr("Images (*.png *.jpg *.jpeg *.webp *.svg)")
        )
        if not path:
            return
        try:
            name = self.context.import_image(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self.dialog, tr("Insert image…"), str(exc))
            return
        self.text.insertPlainText(f'<img src="{name}" alt="">')

    def ask(self):
        """The new HTML, or None when the person cancels."""
        from PySide6.QtWidgets import QDialog

        accepted = self.dialog.exec() == QDialog.DialogCode.Accepted
        return self.text.toPlainText() if accepted else None
