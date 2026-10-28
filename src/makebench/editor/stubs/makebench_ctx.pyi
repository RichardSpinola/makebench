# SPDX-License-Identifier: GPL-3.0-or-later
"""Type information for the `ctx` object your functions receive (editor suggestions only)."""

from typing import Any

class Data:
    """Records of the collections declared in the Data panel, kept between runs."""

    last_id: int | None
    """The id returned by the latest add."""

    def add(self, collection: str, /, **fields: Any) -> int:
        """Add a record (fields by name) and return its id."""
    def update(self, collection: str, record_id: int, /, **fields: Any) -> None:
        """Change fields of a record."""
    def delete(self, collection: str, record_id: int) -> None:
        """Delete a record; refused while other records still point to it."""
    def get(self, collection: str, record_id: int) -> dict[str, Any] | None:
        """One record as a dict with its id, or None."""
    def find(
        self,
        collection: str,
        field: str | None = None,
        op: str = "=",
        value: Any = None,
        order: str | None = None,
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        """Records where field op value holds (=, !=, <, >, <=, >=, contains)."""
    def count(
        self, collection: str, field: str | None = None, op: str = "=", value: Any = None
    ) -> int:
        """How many records match."""
    def sum(
        self,
        collection: str,
        field: str,
        filter_field: str | None = None,
        op: str = "=",
        value: Any = None,
    ) -> float:
        """Total of a number field over the matching records."""
    def name(self, collection: str, record_id: int) -> str:
        """The text that names a record in references."""

class Context:
    """The running application, as seen by your own Python functions."""

    @property
    def data(self) -> Data:
        """The records of your collections."""

    @property
    def window_variables(self) -> dict[str, Any]:
        """Data of the current window, kept between its events."""
    def read(self, component: str, attribute: str) -> Any:
        """Read the current text, selection or progress of a component."""
    def set_text(self, component: str, value: Any) -> None:
        """Change the text of a control in the running window."""
    def set_enabled(self, component: str, value: bool) -> None:
        """Enable or disable a control."""
    def set_theme(self, theme: str, accent: str = "") -> None:
        """Switch the current window to "system", "light" or "dark", with an optional #rrggbb accent."""
    def set_background(self, color: str) -> None:
        """Paint the current window's background with a #rrggbb color; "" restores the theme's."""
    def set_value(self, component: str, value: float) -> None:
        """Set a progress bar (0 to 100), a number or a slider (within its limits)."""
    def set_options(self, component: str, options: list[str]) -> None:
        """Replace the options of a choice list; the selection stays when it remains."""
    def show_records(
        self, component: str, collection: str, records: list[dict[str, Any]] | None = None
    ) -> None:
        """Show records (all by default) in a table or a choice list; read the pick with ctx.read(component, "record")."""
    def set_rows(self, component: str, rows: list[list[Any]]) -> None:
        """Replace all rows of a table; each row is a list of cells."""
    def add_row(self, component: str, row: list[Any]) -> None:
        """Append one row (a list of cells) to a table."""
    def set_chart(self, component: str, labels: list[Any], values: list[float]) -> None:
        """Show these labels and numbers in a chart (one number per label)."""
    def show_page(self, component: str) -> None:
        """Show a page and the pages that contain it."""
    def go_state(self, state: str) -> None:
        """Switch the current window to one of its states."""
    def open_window(self, window: str, close_current: bool = False) -> None:
        """Open another window, optionally closing this one."""
    def close_window(self) -> None:
        """Close this window; the last window ends the application."""
    def log(self, value: Any) -> None:
        """Write a line to the output right away."""
    def message(self, value: Any) -> None:
        """Show a message and wait until it is closed."""
    def ask(self, kind: str, prompt: str, options: list[str] | None = None) -> Any:
        """Ask the person for a value (kinds: text, choice, file, directory, save_file); Cancel ends the flow."""
    def read_text(self, path: str) -> str:
        """The whole text of a file (UTF-8)."""
    def write_text(self, path: str, text: str) -> None:
        """Replace a file with this text (UTF-8)."""
    def read_csv(self, path: str, header: bool = True) -> list[list[str]]:
        """Rows of a CSV file as lists of texts; the first line is skipped when header is True."""
    def export_csv(self, path: str, headers: list[str], rows: list[list[Any]]) -> None:
        """Write a CSV file (UTF-8) with a header line and one line per row."""
    def export_records_csv(
        self, path: str, collection: str, records: list[dict[str, Any]] | None = None
    ) -> None:
        """Export records of a collection (all by default); references show their names."""
    def export_table_csv(self, path: str, component: str) -> None:
        """Export what a table shows now."""
    def confirm(self, prompt: str) -> bool:
        """Continue only if the person answers Yes."""
    def run(
        self,
        program: str,
        arguments: list[str] | None = None,
        *,
        admin: bool = False,
        check: bool = True,
    ) -> int:
        """Run a program with live output and return its exit code."""
    def run_script(
        self,
        source: str,
        arguments: list[str] | None = None,
        *,
        admin: bool = False,
        check: bool = True,
    ) -> int:
        """Run Bash text; arguments become $1, $2… and are never pasted into the script."""
    def terminal_start(
        self, component: str, program: str | None = None, arguments: list[str] | None = None
    ) -> None:
        """Start the program of a Terminal component."""
    def terminal_send(self, component: str, value: Any) -> None:
        """Type text into a Terminal component."""
    def terminal_stop(self, component: str) -> None:
        """Stop what is running in a Terminal component."""
