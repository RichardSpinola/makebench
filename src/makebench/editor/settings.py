# SPDX-License-Identifier: GPL-3.0-or-later
"""Qt settings centers: the global editor and the project's application."""

import json
import re
from pathlib import Path
from PySide6.QtCore import Qt, QSettings, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from makebench.core.environment import gtk_support, build_tools
from makebench.core.diagnostics import environment_report
from makebench.core.exporter import effects
from makebench import __version__
from .theme import manager, icon
from makebench.i18n import language, tr

DEFAULTS = {
    "appearance/theme": "system",
    "appearance/accent": "system",
    "appearance/scale": 100,
    "appearance/reduce_motion": False,
    "appearance/language": "en",
    "projects/folder": str(Path.home() / "Makebench" / "Projects"),
    "projects/trust": True,
    "projects/backend": "gtk",
    "projects/startup": True,
    "editor/code_font": "Monospace",
    "editor/code_size": 11,
    "editor/wrap": False,
    "editor/recovery": 30,
    "editor/grid": True,
    "test/clear": True,
    "test/confirm_restart": True,
    "test/duration": True,
}
CHOICES = {
    "appearance/theme": ["system", "light", "dark"],
    "appearance/accent": ["system"],
    "appearance/scale": [90, 100, 115, 125, 130, 150],
    "appearance/language": ["en", "pt_BR"],
    "projects/backend": ["gtk", "qt"],
    "editor/recovery": [0, 15, 30, 60],
}


def preference(key, settings=None):
    """Invalid values are ignored; QSettings booleans get an explicit conversion."""
    settings = settings or QSettings("Makebench", "Makebench")
    default = DEFAULTS[key]
    value = settings.value("v1/" + key, default)
    if isinstance(default, bool):
        return (
            value
            if isinstance(value, bool)
            else str(value).lower() == "true"
            if str(value).lower() in {"true", "false"}
            else default
        )
    if isinstance(default, int):
        try:
            value = int(value)
        except (ValueError, TypeError):
            return default
    if type(value) is not type(default) or key in CHOICES and value not in CHOICES[key]:
        return default
    if isinstance(value, str) and ("\0" in value or len(value) > 4096):
        return default
    if key == "editor/code_size" and not 8 <= value <= 32:
        return default
    return value


class SettingsShell(QDialog):
    """Window with navigation, option search and Qt card groups."""

    def showEvent(self, event):
        """Name the search fields' clear buttons once every page exists."""
        super().showEvent(event)
        from .controls import name_unlabeled_buttons

        name_unlabeled_buttons(self)

    def __init__(self, parent, title):
        """The search filters rows across all pages and keeps keyboard focus."""
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(860, 640)
        self.setMinimumSize(720, 440)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search settings…"))
        self.search.setClearButtonEnabled(True)
        outer.addWidget(self.search)
        body = QHBoxLayout()
        self.sections = QListWidget()
        self.sections.setMaximumWidth(200)
        self.sections.setMinimumWidth(170)
        body.addWidget(self.sections)
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)
        self.sections.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.search.textChanged.connect(self.filter_rows)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        outer.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        self.rows = []
        self.page_layouts = []
        self.no_results = QLabel(tr("No setting matches the search."))
        self.no_results.hide()
        outer.insertWidget(2, self.no_results)

    def add_page(self, title):
        """A scrollable page also works with larger fonts and a smaller window."""
        self.sections.addItem(title)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(12)
        page.setMaximumWidth(700)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.pages.addWidget(scroll)
        self.page_layouts.append(layout)
        if self.sections.count() == 1:
            self.sections.setCurrentRow(0)
        return layout

    def group(self, page, title, description=""):
        """The title sits outside the card and the description explains the option's effect."""
        heading = QLabel(title)
        heading.setProperty("section", True)
        page.addWidget(heading)
        if description:
            label = QLabel(description)
            label.setWordWrap(True)
            label.setProperty("muted", True)
            page.addWidget(label)
        from PySide6.QtWidgets import QFrame

        card = QFrame()
        card.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        page.addWidget(card)
        return layout

    def row(self, group, label, control, description=""):
        """An option row has a title/description and a right-aligned control."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        text_holder = QWidget()
        text_holder.setFixedWidth(200)
        text = QVBoxLayout(text_holder)
        text.setContentsMargins(0, 0, 0, 0)
        title = QLabel(label)
        title.setWordWrap(True)
        title.setTextFormat(Qt.TextFormat.PlainText)
        text.addWidget(title)
        if description:
            subtitle = QLabel(description)
            subtitle.setTextFormat(Qt.TextFormat.PlainText)
            subtitle.setWordWrap(True)
            subtitle.setProperty("muted", True)
            text.addWidget(subtitle)
        layout.addWidget(text_holder)
        layout.addWidget(control)
        layout.addStretch(1)
        control.setMaximumWidth(360)
        group.addWidget(widget)
        self.rows.append((widget, (label + " " + description).casefold(), self.pages.count() - 1))
        control.setAccessibleName(label)
        return control

    def filter_rows(self, text):
        """The search jumps to the first page with results without changing values."""
        query = text.casefold()
        matches = [
            index
            for index in range(self.sections.count())
            if query in self.sections.item(index).text().casefold()
        ]
        for widget, label, page in self.rows:
            visible = query in label or query in self.sections.item(page).text().casefold()
            widget.setVisible(visible)
            if visible:
                matches.append(page)
        self.no_results.setVisible(bool(query and not matches))
        if query and matches:
            self.sections.setCurrentRow(matches[0])


class EditorPreferences(SettingsShell):
    """Immediate preferences in QSettings, independent of the projects' history."""

    def __init__(self, window):
        """Build the pages and keep each option with a single source of truth."""
        super().__init__(window, tr("Makebench preferences"))
        self.window = window
        self.settings = window.settings
        self.controls = {}
        for prefix, title in [
            ("appearance", tr("Appearance")),
            ("projects", tr("Projects")),
            ("editor", tr("Editor")),
            ("test", tr("Testing")),
        ]:
            page = self.add_page(title)
            group = self.group(page, title, tr("Changes apply immediately."))
            self.populate(group, prefix)
            if prefix == "projects":
                clear = QPushButton(tr("Clear recent projects"))
                clear.clicked.connect(
                    lambda: (self.settings.remove("projects/recent"), window.refresh_recents())
                )
                group.addWidget(clear)
            reset = QPushButton(tr("Restore this page's defaults"))
            reset.clicked.connect(lambda _, prefix=prefix: self.reset_page(prefix))
            page.addWidget(reset, 0, Qt.AlignmentFlag.AlignRight)
        page = self.add_page(tr("Shortcuts"))
        group = self.group(
            page,
            tr("Commands"),
            tr("Shortcuts are read-only in this version. The search also finds command names."),
        )
        from .commands import register

        register(window)
        for action in window.commands:
            shortcut = QLabel(action.shortcut().toString() or tr("No shortcut"))
            self.row(group, action.text().replace("&", "").replace("…", ""), shortcut)
        page = self.add_page(tr("Environment"))
        group = self.group(page, tr("Environment diagnostics"))
        self.report = QPlainTextEdit(diagnostic(window))
        self.report.setReadOnly(True)
        self.report.setMinimumHeight(300)
        group.addWidget(self.report)
        copy = QPushButton(tr("Copy report"))
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.report.toPlainText()))
        group.addWidget(copy)
        page = self.add_page(tr("Plugins"))
        group = self.group(page, tr("Plugins"), tr("Support planned for a future release."))
        label = QLabel(
            tr(
                "This space will be used to manage Makebench extensions. Installing and running plugins is not available yet."
            )
        )
        label.setWordWrap(True)
        group.addWidget(label)
        page = self.add_page(tr("About"))
        group = self.group(page, "Makebench " + __version__)
        label = QLabel(
            tr(
                "Visual editor for Linux applications. No account, server or AI at run time.\n\nPySide6/Qt: LGPL/GPL/commercial. Blockly 13.4.0: Apache-2.0. Optional GTK backend: GTK4 and PyGObject (LGPL), optional libadwaita (LGPL). Fallback symbols are our own vectors.\n\nMakebench is free software under the GNU GPL, version 3 or later."
            )
        )
        label.setWordWrap(True)
        group.addWidget(label)
        documentation = QPushButton(tr("Open the user guide"))
        documentation.clicked.connect(lambda: open_checklist(window))
        group.addWidget(documentation)

    def populate(self, group, prefix):
        """Create controls bound to versioned keys and validated options."""
        labels = {
            "appearance/theme": tr("Theme"),
            "appearance/accent": tr("Accent color"),
            "appearance/scale": tr("Text size"),
            "appearance/reduce_motion": tr("Reduce motion"),
            "appearance/language": tr("Interface language"),
            "projects/folder": tr("Folder for new projects"),
            "projects/trust": tr("Warn about untrusted projects"),
            "projects/backend": tr("Default backend"),
            "projects/startup": tr("Show the start window on launch"),
            "editor/code_font": tr("Code font"),
            "editor/code_size": tr("Code size"),
            "editor/wrap": tr("Wrap code lines"),
            "editor/recovery": tr("Automatic recovery"),
            "editor/grid": tr("Snap to grid by default"),
            "test/clear": tr("Clear output on start"),
            "test/confirm_restart": tr("Confirm restart during a task"),
            "test/duration": tr("Show run time"),
        }
        option_labels = {
            "appearance/theme": [tr("System"), tr("Light"), tr("Dark")],
            "appearance/accent": [tr("From the system")],
            "appearance/scale": ["90%", "100%", "115%", "125%", "130%", "150%"],
            "appearance/language": ["English", "Português (Brasil)"],
            "projects/backend": ["GTK", "Qt"],
            "editor/recovery": [tr("Off"), tr("15 seconds"), tr("30 seconds"), tr("60 seconds")],
        }
        for key, label in labels.items():
            if not key.startswith(prefix + "/"):
                continue
            value = preference(key, self.settings)
            if key == "appearance/accent":
                field = QLabel(tr("From the system"))
            elif key in CHOICES:
                field = QComboBox()
                for text, item in zip(option_labels[key], CHOICES[key]):
                    field.addItem(text, item)
                field.setCurrentIndex(field.findData(value))
                field.currentIndexChanged.connect(
                    lambda _, key=key, field=field: self.changed(key, field.currentData())
                )
            elif isinstance(value, bool):
                field = QCheckBox()
                field.setChecked(value)
                field.toggled.connect(lambda value, key=key: self.changed(key, value))
            elif isinstance(value, int):
                field = QSpinBox()
                field.setRange(8, 32)
                field.setValue(value)
                field.valueChanged.connect(lambda value, key=key: self.changed(key, value))
            else:
                field = QLineEdit(value)
                field.setMinimumWidth(180)
                field.textChanged.connect(lambda value, key=key: self.changed(key, value))
            self.controls[key] = field
            self.row(
                group,
                label,
                field,
                tr("Fixed 4-space indentation.")
                if key == "editor/code_font"
                else tr("Takes effect the next time Makebench starts.")
                if key == "appearance/language"
                else "",
            )

    def changed(self, key, value):
        """Persist only preferences; apply without restarting or marking the project."""
        self.settings.setValue("v1/" + key, value)
        apply_preferences(self.window)

    def reset_page(self, prefix):
        """Restore only one page and update its controls without signal recursion."""
        for key, field in self.controls.items():
            if not key.startswith(prefix + "/"):
                continue
            self.settings.remove("v1/" + key)
            value = preference(key, self.settings)
            field.blockSignals(True)
            if isinstance(field, QComboBox):
                field.setCurrentIndex(field.findData(value))
            elif isinstance(field, QCheckBox):
                field.setChecked(value)
            elif isinstance(field, QSpinBox):
                field.setValue(value)
            else:
                field.setText(tr("From the system") if key == "appearance/accent" else value)
            field.blockSignals(False)
        apply_preferences(self.window)


def apply_preferences(window):
    """Apply theme, code, recovery and behavior to the existing widgets."""
    theme = manager()
    theme.mode = preference("appearance/theme")
    theme.accent = "system"
    theme.scale = preference("appearance/scale")
    theme.reduce_motion = preference("appearance/reduce_motion")
    theme.apply()
    font = QFont(preference("editor/code_font"), preference("editor/code_size"))
    font.setStyleHint(QFont.StyleHint.Monospace)
    for editor in (
        window.source_editor,
        window.generated_editor,
        window.logic.code,
        window.script_editor,
        *getattr(window, "module_editors", {}).values(),
    ):
        editor.setFont(font)
        editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(" ") * 4)
        editor.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if preference("editor/wrap")
            else QPlainTextEdit.LineWrapMode.NoWrap
        )
    interval = preference("editor/recovery")
    if interval:
        window.recovery_timer.setInterval(interval * 1000)
        window.recovery_timer.start()
    else:
        window.recovery_timer.stop()
    window.snap_check.setChecked(preference("editor/grid"))
    window.refresh_trust_banner()


def diagnostic(window=None):
    """Collect the real Qt state without running tools or project code."""
    app = QApplication.instance()
    theme = manager()
    screen = window.screen() if window else app.primaryScreen()
    return environment_report(
        {
            "Qt": __import__("PySide6.QtCore", fromlist=["qVersion"]).qVersion(),
            tr("Platform plugin"): app.platformName(),
            tr("Theme"): tr("Dark") if theme.tokens["dark"] else tr("Light"),
            tr("System accent"): theme.tokens.get("system_accent", tr("Unavailable")),
            tr("Accent adjusted for contrast"): str(theme.tokens.get("accent_adjusted", False)),
            tr("Screen scale"): str(screen.devicePixelRatio()) if screen else tr("Unavailable"),
        }
    )


def show_diagnostic(window):
    """A dedicated window offers the full report and a copy action."""
    dialog = QDialog(window)
    dialog.setWindowTitle(tr("Environment diagnostics"))
    dialog.resize(760, 580)
    layout = QVBoxLayout(dialog)
    report = QPlainTextEdit(diagnostic(window))
    report.setReadOnly(True)
    layout.addWidget(report)
    copy = QPushButton(tr("Copy report"))
    copy.clicked.connect(lambda: QApplication.clipboard().setText(report.toPlainText()))
    layout.addWidget(copy)
    close = QPushButton(tr("Close"))
    close.clicked.connect(dialog.close)
    layout.addWidget(close)
    dialog.show()
    window.diagnostic_dialog = dialog
    return dialog


def open_checklist(window):
    """Open the local user guide that ships with the source and the editor package."""
    path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / ("user-guide.pt-BR.md" if language() == "pt_BR" else "user-guide.md")
    )
    if path.exists():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    else:
        window._show_error(tr("See docs/user-guide.md in the Makebench folder."))


class ApplicationSettings(SettingsShell):
    """Per-project settings, with reversible changes and field search."""

    def __init__(self, window):
        """Identity, icon, backend, dependencies, permissions, windows, data and targets."""
        super().__init__(window, tr("Application settings"))
        self.window = window
        self.fields = {}
        self.validation_errors = {}
        app = window.project.application
        page = self.add_page(tr("Identity"))
        group = self.group(
            page, tr("Identity"), tr("This information ships with the exported application.")
        )
        for key, label in [
            ("name", tr("Public name")),
            ("id", tr("Identifier")),
            ("version", tr("Version")),
            ("description", tr("Description")),
            ("author", tr("Author")),
            ("license", tr("License")),
            ("category", tr("Categories")),
        ]:
            field = QLineEdit(str(app.get(key, "")))
            field.setMinimumWidth(230)
            field.editingFinished.connect(
                lambda key=key, field=field: self.change(key, field.text())
            )
            self.row(
                group,
                label,
                field,
                tr("E.g. com.example.myapp; identifies the application in packages.")
                if key == "id"
                else tr("E.g. 0.1.0")
                if key == "version"
                else "",
            )
            self.fields[key] = field
        self.identity_notice = QLabel()
        self.identity_notice.setWordWrap(True)
        group.addWidget(self.identity_notice)
        page = self.add_page(tr("Icon"))
        group = self.group(page, tr("Application icon"), tr("PNG of at least 256 pixels, or SVG."))
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(128, 128)
        preview_row = QHBoxLayout()
        self.icon_previews = {}
        for size in (16, 32, 64, 128):
            holder = QVBoxLayout()
            image = self.icon_preview if size == 128 else QLabel()
            image.setFixedSize(size, size)
            holder.addWidget(image, 0, Qt.AlignmentFlag.AlignHCenter)
            holder.addWidget(QLabel(str(size) + " px"), 0, Qt.AlignmentFlag.AlignHCenter)
            preview_row.addLayout(holder)
            self.icon_previews[size] = image
        preview_row.addStretch()
        group.addLayout(preview_row)
        choose = QPushButton(tr("Choose icon…"))
        choose.clicked.connect(self.choose_icon)
        group.addWidget(choose)
        self.update_icon()
        page = self.add_page(tr("Appearance"))
        group = self.group(
            page,
            tr("Application backend"),
            tr(
                "The editor is Qt. This choice sets the controls of the application you are building."
            ),
        )
        backend = QComboBox()
        backend.addItem("GTK4 / Adwaita", "gtk")
        backend.addItem("Qt / PySide6", "qt")
        backend.setCurrentIndex(backend.findData(app.get("backend", "qt")))
        backend.currentIndexChanged.connect(lambda _: self.change("backend", backend.currentData()))
        self.row(group, tr("Appearance and execution"), backend)
        app_language = QComboBox()
        app_language.setAccessibleName(tr("Application language"))
        app_language.addItem("English", "en")
        app_language.addItem("Português (Brasil)", "pt_BR")
        app_language.setCurrentIndex(max(0, app_language.findData(app.get("language", "en"))))
        app_language.currentIndexChanged.connect(
            lambda _: self.change("language", app_language.currentData())
        )
        self.row(
            group,
            tr("Application language"),
            app_language,
            tr("Language of the messages and dialogs that Makebench adds to your application."),
        )
        if not gtk_support()["gtk4"]:
            notice = QLabel(
                tr(
                    "GTK4 is missing in this Python. The GTK test lists the required packages, without installing them automatically."
                )
            )
            notice.setWordWrap(True)
            group.addWidget(notice)
        page = self.add_page(tr("Dependencies"))
        group = self.group(
            page,
            tr("Dependencies"),
            tr(
                "Minimum Python 3.12; supported versions 3.12–3.14. GTK requires PyGObject/GTK4; Qt requires PySide6 6.11.2."
            ),
        )
        from .settings_fields import Dependencies

        packages = Dependencies(app.get("packages", []))
        packages.changed.connect(lambda values: self.change("packages", values))
        group.addWidget(packages)
        self.fields["packages"] = packages
        programs, admin = effects(window.project)
        label = QLabel(
            tr("Detected programs: {programs}.").format(programs=", ".join(programs) or tr("none"))
            + " "
            + tr("Your own functions may require other programs.")
        )
        label.setWordWrap(True)
        group.addWidget(label)
        page = self.add_page(tr("Permissions"))
        group = self.group(page, tr("System access"))
        text = QLabel(
            tr(
                "Python source, DEB, RPM and AppImage run with the user's permissions. Testing is not a sandbox."
            )
            + "\n\n"
            + (
                tr(
                    "There are declared administrative actions: Polkit/pkexec and a system agent are required. Makebench never asks for passwords."
                )
                if admin
                else tr("No administrative action declared in the blocks.")
            )
            + "\n\n"
            + tr(
                "The isolated Flatpak blocks host programs and administration. Additional dependencies must exist inside the package."
            )
        )
        text.setWordWrap(True)
        group.addWidget(text)
        page = self.add_page(tr("Windows"))
        group = self.group(page, tr("Application windows"))
        initial = QComboBox()
        roots = [] if window.project.metadata.get("empty_map") else window.project.roots
        if not roots:
            notice = QLabel(tr("No interface yet. Create the first one in the map."))
            group.addWidget(notice)
        initial.setEnabled(bool(roots))
        for root in roots:
            initial.addItem(root.properties.get("title", tr("Interface")), root.id)
        initial.setCurrentIndex(
            initial.findData(window.project.entry_window or window.project.root.id)
        )
        initial.currentIndexChanged.connect(
            lambda _: window._edit(
                lambda: setattr(window.project, "entry_window", initial.currentData())
            )
        )
        self.row(group, tr("Start window"), initial)
        for root in roots:
            group = self.group(
                page,
                root.properties.get("title", tr("Interface")),
                tr("Initial size in logical pixels."),
            )
            field = QLineEdit(root.properties.get("title", tr("Interface")))
            field.editingFinished.connect(
                lambda identifier=root.id, field=field: window._edit(
                    lambda: window.project.find(identifier).properties.update(title=field.text())
                )
            )
            self.row(group, tr("Interface title"), field)
            for key, label, default in [("width", tr("Width"), 640), ("height", tr("Height"), 480)]:
                spin = QSpinBox()
                spin.setRange(100, 20000)
                spin.setValue(root.properties.get(key, default))
                spin.editingFinished.connect(
                    lambda identifier=root.id, key=key, spin=spin: window._edit(
                        lambda: window.project.find(identifier).properties.update(
                            {key: spin.value()}
                        )
                    )
                )
                self.row(group, label, spin)
            resizable = QCheckBox()
            resizable.setChecked(root.properties.get("resizable", True))
            resizable.toggled.connect(
                lambda value, identifier=root.id: window._edit(
                    lambda: window.project.find(identifier).properties.update(resizable=value)
                )
            )
            self.row(group, tr("Allow resizing"), resizable)
            state = QComboBox()
            state.addItem(tr("Default"), "@default")
            for entry in window.project.states.get(root.id, []):
                state.addItem(entry["name"], entry["id"])
            state.setCurrentIndex(state.findData(root.properties.get("initial_state", "@default")))
            state.currentIndexChanged.connect(
                lambda _, identifier=root.id, state=state: window._edit(
                    lambda: window.project.find(identifier).properties.update(
                        initial_state=state.currentData()
                    )
                )
            )
            self.row(group, tr("State on open"), state)
            choose = QPushButton(tr("Choose an icon for this window…"))
            choose.clicked.connect(
                lambda _, identifier=root.id: self.choose_window_icon(identifier)
            )
            group.addWidget(choose)
        page = self.add_page(tr("Data"))
        group = self.group(
            page,
            tr("Variables and initial values"),
            tr("Project or window data. Values are JSON: text, number, boolean or list."),
        )
        self.variables_view = QListWidget()
        self.variables_view.setAccessibleName(tr("Name, type, scope and initial value"))
        group.addWidget(self.variables_view)
        self.variables_view.itemActivated.connect(lambda _: self.edit_variable())
        row = QHBoxLayout()
        for label, callback in [
            (tr("Add…"), lambda: self.edit_variable(new=True)),
            (tr("Edit…"), self.edit_variable),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch()
        group.addLayout(row)
        self.refresh_variables()
        page = self.add_page(tr("Targets"))
        group = self.group(
            page,
            tr("Exporters"),
            tr(
                "A result is marked as built only after passing through the tool and the verification."
            ),
        )
        for name, tool in [
            (tr("Python source"), None),
            ("DEB", "dpkg-deb"),
            ("AppImage", "appimagetool"),
            ("Flatpak", "flatpak-builder"),
            ("RPM", "rpmbuild"),
        ]:
            from makebench.core.build_environment import prepared

            status = QLabel(
                tr("Build from the Export window")
                if not tool or build_tools().get(tool) or tool != "flatpak-builder" and prepared()
                else tr("Prepare tools in the Export window")
            )
            self.row(group, name, status)

    def change(self, key, value):
        """Write only the changed field, without regenerating or running your own sources."""
        error = ""
        if key == "id" and not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_-]*){2,}", value):
            error = tr("Use an identifier such as com.example.myapp.")
        elif key == "version" and not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", value):
            error = tr("Use a version such as 0.1.0.")
        elif key == "name" and not value.strip():
            error = tr("Enter the application's public name.")
        if error:
            self.validation_errors[key] = error
        else:
            self.validation_errors.pop(key, None)
        if hasattr(self, "identity_notice"):
            self.identity_notice.setText("\n".join(self.validation_errors.values()))
        if error:
            return
        if self.window.project.application.get(key) != value:
            self.window.change_application(key, value)

    def choose_icon(self):
        """Import the asset into the project's portable cache and show its real appearance."""
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Application icon"), "", tr("Icons (*.png *.svg)")
        )
        if path:
            try:
                self.change("icon", self.window.assets.import_image(Path(path)))
                self.update_icon()
            except Exception as exc:
                self.window._show_error(exc, tr("Could not use this icon"))

    def choose_window_icon(self, identifier):
        """Each window can have its own icon without depending on the original path."""
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Window icon"), "", tr("Icons (*.png *.svg)")
        )
        if path:
            try:
                name = self.window.assets.import_image(Path(path))
                self.window._edit(
                    lambda: self.window.project.find(identifier).properties.update(icon=name)
                )
            except Exception as exc:
                self.window._show_error(exc, tr("Could not use this icon"))

    def update_icon(self):
        """The image uses the same asset that will ship with the exported application."""
        from PySide6.QtGui import QPixmap

        name = self.window.project.application.get("icon")
        if name:
            try:
                pixmap = QPixmap()
                pixmap.loadFromData(self.window.assets.read(name))
                for size, image in self.icon_previews.items():
                    image.setPixmap(
                        pixmap.scaled(
                            size,
                            size,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
            except Exception:
                self.icon_preview.clear()

    def refresh_variables(self):
        """The list reflects the current model without swapping the data's source of truth."""
        self.variables_view.clear()
        for variable in self.window.project.variables:
            value = variable.get("initial")
            scope = (
                tr("Project")
                if variable.get("scope", "project") == "project"
                else self.window.project.find(variable["window"]).properties.get(
                    "title", tr("Window")
                )
            )
            kind = (
                tr("Null")
                if value is None
                else tr("Boolean")
                if isinstance(value, bool)
                else tr("Number")
                if isinstance(value, (int, float))
                else tr("Text")
                if isinstance(value, str)
                else tr("List")
                if isinstance(value, list)
                else tr("Object")
            )
            self.variables_view.addItem(f"{variable['name']} · {kind} · {scope}\n{value!r}")

    def edit_variable(self, _checked=False, new=False):
        """Open the existing editor and refresh the list after confirming or cancelling."""
        index = None if new else self.variables_view.currentRow()
        if index is not None and index < 0:
            return
        self.window.variable_dialog(index=index)
        self.refresh_variables()
