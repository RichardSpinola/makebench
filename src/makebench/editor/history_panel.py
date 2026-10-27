# SPDX-License-Identifier: GPL-3.0-or-later
"""Version history window: every save is a version you can name, view and restore."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from makebench.core import vcs
from makebench.core.project import ProjectError
from makebench.core.storage import load_project
from makebench.i18n import ntr, tr

from .errors import show_error
from .look import header
from .theme import icon


class _Signals(QObject):
    done = Signal(object, object)


class _Job(QRunnable):
    """Run a Git call off the interface thread and report its result."""

    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = _Signals()

    def run(self):
        """Call the function; errors travel back as the second signal value."""
        try:
            outcome = (self.function(), None)
        except Exception as exc:  # noqa: BLE001 - reported to the person
            outcome = (None, exc)
        try:
            self.signals.done.emit(*outcome)
        except RuntimeError:
            pass  # the application is closing; nobody is waiting for the answer


_ACTIVE = set()


def run_in_background(function, callback):
    """Start `function` on the thread pool; `callback(result, error)` runs in the UI thread."""
    job = _Job(function)
    job.setAutoDelete(False)
    _ACTIVE.add(job)

    def finished(result, error):
        _ACTIVE.discard(job)
        callback(result, error)

    job.signals.done.connect(finished)
    QThreadPool.globalInstance().start(job)
    return job


def history_enabled(window) -> bool:
    """True when this project's folder already has a version history."""
    return window.path is not None and vcs.is_repo(window.path.parent)


def record_version(window):
    """After a successful save, record a version in the background (never blocks saving)."""
    if not history_enabled(window):
        return
    root = window.path.parent
    stamp = datetime.now().strftime("%H:%M")
    message = tr("Saved at {time}").format(time=stamp)

    def done(_result, error):
        if error is not None:
            window.statusBar().showMessage(
                tr("The file was saved, but the version could not be recorded: {error}").format(
                    error=error
                ),
                10000,
            )
        panel = getattr(window, "history_dialog", None)
        if panel is not None and panel.isVisible():
            panel.refresh()

    window._history_jobs = [j for j in getattr(window, "_history_jobs", []) if j][-3:]
    window._history_jobs.append(run_in_background(lambda: vcs.commit_all(root, message), done))


class HistoryDialog(QDialog):
    """Lists versions by day with what changed, and offers name, restore and send."""

    def __init__(self, window):
        super().__init__(window)
        self.window_ = window
        self.setWindowTitle(tr("Version history"))
        self.resize(640, 640)
        layout = QVBoxLayout(self)
        banner = header(tr("Version history"), " ", icon("history"))
        layout.addWidget(banner)
        # The banner's phrase says where history stands: off, empty or how many versions.
        self.status = banner.help
        self.enable = QPushButton(tr("Turn on version history"))
        self.enable.setDefault(True)
        self.enable.clicked.connect(self.turn_on)
        layout.addWidget(self.enable, 0, Qt.AlignmentFlag.AlignLeft)
        self.versions = QListWidget()
        self.versions.setAccessibleName(tr("Versions"))
        self.versions.currentItemChanged.connect(self._selected)
        layout.addWidget(self.versions, 1)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        row = QHBoxLayout()
        self.name_button = QPushButton(tr("Name this version…"))
        self.name_button.clicked.connect(self.name_version)
        self.restore_button = QPushButton(tr("Restore this version"))
        self.restore_button.clicked.connect(self.restore_version)
        row.addWidget(self.name_button)
        row.addWidget(self.restore_button)
        row.addStretch(1)
        layout.addLayout(row)
        # Takes the free space while the list is hidden, so the text stays at the top.
        self.filler = QWidget()
        layout.addWidget(self.filler, 1)
        self.cloud = QGroupBox(tr("Online copy"))
        form = QFormLayout(self.cloud)
        self.account = QLabel()
        form.addRow(tr("Signed in as"), self.account)
        self.address = QLineEdit()
        self.address.setPlaceholderText(
            "https://github.com/you/app.git  ·  git@gitlab.com:you/app.git"
        )
        self.address.setAccessibleName(tr("Repository address"))
        form.addRow(tr("Address"), self.address)
        self.sync_state = QLabel()
        form.addRow(tr("State"), self.sync_state)
        buttons = QHBoxLayout()
        self.connect_button = QPushButton(tr("Connect"))
        self.connect_button.clicked.connect(self.connect_remote)
        self.send_button = QPushButton(tr("Send"))
        self.send_button.clicked.connect(self.send)
        self.fetch_button = QPushButton(tr("Get updates"))
        self.fetch_button.clicked.connect(self.get_updates)
        self.create_button = QPushButton(tr("Create on GitHub"))
        self.create_button.clicked.connect(self.create_github)
        for button in (
            self.connect_button,
            self.send_button,
            self.fetch_button,
            self.create_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        form.addRow(buttons)
        note = QLabel(
            tr(
                "Nothing is sent unless you press Send. Makebench uses the sign-in your computer already has (gh, SSH key or keyring) and never stores passwords."
            )
        )
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(self.cloud)
        self.refresh()

    @property
    def root(self) -> Path | None:
        """The project folder, or None for a project without a file yet."""
        return self.window_.path.parent if self.window_.path else None

    def refresh(self):
        """Rebuild the list and the buttons from the repository."""
        self.versions.clear()
        enabled = history_enabled(self.window_)
        available = vcs.available()
        self.enable.setVisible(available and not enabled)
        self.cloud.setVisible(enabled)
        self.filler.setVisible(not enabled)
        if enabled != getattr(self, "_sized_for", None):
            # A short window while history is off; room for the list once it is on.
            self._sized_for = enabled
            if enabled:
                self.resize(640, 640)
            else:
                self.resize(520, self.sizeHint().height())
        for widget in (self.versions, self.detail, self.name_button, self.restore_button):
            widget.setVisible(enabled)
        if not available:
            self.status.setText(
                tr("Git is not installed on this computer, so history is unavailable.")
            )
            return
        if self.root is None:
            self.status.setText(tr("Save the project once to be able to turn on its history."))
            self.enable.setEnabled(False)
            return
        if not enabled:
            self.status.setText(
                tr(
                    "History is off. When it is on, every time you save, Makebench keeps that version so you can come back to it."
                )
            )
            return
        versions = vcs.log(self.root)
        self.status.setText(
            ntr("{count} version kept.", "{count} versions kept.", len(versions)).format(
                count=len(versions)
            )
        )
        day = None
        bold = QFont()
        bold.setBold(True)
        for version in versions:
            moment = datetime.fromtimestamp(version.time)
            if moment.date() != day:
                day = moment.date()
                header = QListWidgetItem(moment.strftime("%A, %d/%m/%Y"))
                header.setFont(bold)
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                self.versions.addItem(header)
            title = ", ".join(version.names) or version.subject
            item = QListWidgetItem(f"{moment:%H:%M}   {title}")
            if version.names:
                item.setFont(bold)
            item.setData(Qt.ItemDataRole.UserRole, version)
            self.versions.addItem(item)
        for index in range(self.versions.count()):
            if self.versions.item(index).data(Qt.ItemDataRole.UserRole):
                self.versions.setCurrentRow(index)
                break
        self._selected()
        self._refresh_cloud()

    def _version(self):
        item = self.versions.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected(self, *_):
        version = self._version()
        self.name_button.setEnabled(version is not None)
        self.restore_button.setEnabled(version is not None)
        if version is None:
            self.detail.setText("")
            return
        try:
            self.detail.setText(
                tr("Changes: {summary}").format(summary=vcs.describe(self.root, version.rev))
            )
        except vcs.VcsError:
            self.detail.setText("")

    def _refresh_cloud(self):
        remotes = vcs.remotes(self.root)
        self.address.setText(remotes.get("origin", ""))
        connected = "origin" in remotes
        for button in (self.send_button, self.fetch_button):
            button.setEnabled(connected)
        self.create_button.setVisible(not connected)
        self.account.setText(tr("checking…"))
        run_in_background(vcs.account, self._account_ready)
        if not connected:
            self.sync_state.setText(tr("Not connected"))
            return
        state = vcs.ahead_behind(self.root)
        if state is None:
            self.sync_state.setText(tr("Connected. Press Send to upload your versions."))
        else:
            ahead, behind = state
            self.sync_state.setText(
                tr("{ahead} not sent yet · {behind} to get").format(ahead=ahead, behind=behind)
            )

    def _account_ready(self, login, _error):
        self.account.setText(
            login
            or tr("not signed in (for GitHub: run `gh auth login`; for others, use an SSH key)")
        )

    def _fail(self, error):
        show_error(self, error, tr("Version history"))

    def turn_on(self):
        """Create the history for this project folder after the person asked."""
        try:
            vcs.init(self.root)
            if not all(vcs.identity(self.root)):
                name, ok = QInputDialog.getText(self, tr("Your name"), tr("Name shown on versions"))
                if not ok:
                    return
                email, ok = QInputDialog.getText(
                    self, tr("Your e-mail"), tr("E-mail shown on versions")
                )
                if not ok:
                    return
                vcs.set_identity(self.root, name, email)
            vcs.commit_all(self.root, tr("History turned on"))
        except vcs.VcsError as exc:
            self._fail(exc)
        self.refresh()

    def name_version(self):
        """Give the selected version a name that is easy to find again."""
        version = self._version()
        if version is None:
            return
        name, ok = QInputDialog.getText(self, tr("Name this version"), tr("Name"))
        if not ok:
            return
        try:
            vcs.label(self.root, version.rev, name)
        except vcs.VcsError as exc:
            self._fail(exc)
        self.refresh()

    def restore_version(self):
        """Bring back the selected version; the current state is kept as a version first."""
        version = self._version()
        window = self.window_
        if version is None or window.path is None:
            return
        moment = datetime.fromtimestamp(version.time).strftime("%d/%m/%Y %H:%M")
        answer = QMessageBox.question(
            self,
            tr("Restore this version"),
            tr(
                "Go back to the version from {moment}? What you have now is kept as a version, so you can return to it."
            ).format(moment=moment),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if (window.history.dirty or window.source.dirty) and not window.save():
            return
        try:
            vcs.restore(self.root, version.rev)
            project = load_project(window.path)
            window._replace_project(project, window.path)
        except (vcs.VcsError, ProjectError, OSError) as exc:
            self._fail(exc)
        self.refresh()

    def connect_remote(self):
        """Save the online address typed by the person."""
        try:
            vcs.set_remote(self.root, self.address.text())
        except vcs.VcsError as exc:
            self._fail(exc)
        self._refresh_cloud()

    def _network(self, function):
        for button in (self.send_button, self.fetch_button, self.connect_button):
            button.setEnabled(False)
        self.sync_state.setText(tr("Working…"))

        def done(_result, error):
            if error is not None:
                self._fail(error)
            self.refresh()

        self._job = run_in_background(function, done)

    def send(self):
        """Upload the versions (only when the person presses the button)."""
        root = self.root
        self._network(lambda: vcs.push(root))

    def get_updates(self):
        """Download newer versions, joining them only when nothing conflicts."""
        root = self.root

        def work():
            vcs.fetch(root)
            state = vcs.ahead_behind(root)
            if state and state[1] and not state[0]:
                vcs.pull(root)

        self._network(work)

    def create_github(self):
        """Create a private online repository with the GitHub command line."""
        name, ok = QInputDialog.getText(
            self, tr("Create on GitHub"), tr("Repository name"), text=self.root.name
        )
        if not ok:
            return
        root = self.root
        self._network(lambda: vcs.create_github_repo(root, name))


def install_history(window):
    """Add File › Version history… and keep the dialog on the window."""
    action = QAction(tr("Version history…"), window)

    def show():
        window.history_dialog = HistoryDialog(window)
        window.history_dialog.show()

    action.triggered.connect(show)
    window.history_action = action
    return action
