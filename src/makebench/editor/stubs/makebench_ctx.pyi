# SPDX-License-Identifier: GPL-3.0-or-later
"""Type information for the `ctx` object your functions receive (editor suggestions only)."""

from typing import Any

class Context:
    """The running application, as seen by your own Python functions."""

    @property
    def window_variables(self) -> dict[str, Any]:
        """Data of the current window, kept between its events."""
    def read(self, component: str, attribute: str) -> Any:
        """Read the current text, selection or progress of a component."""
    def set_text(self, component: str, value: Any) -> None:
        """Change the text of a control in the running window."""
    def set_enabled(self, component: str, value: bool) -> None:
        """Enable or disable a control."""
    def set_value(self, component: str, value: int) -> None:
        """Set a progress bar from 0 to 100."""
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
        """Ask the person for a value; Cancel ends the flow."""
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
