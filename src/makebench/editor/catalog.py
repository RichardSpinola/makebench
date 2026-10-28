# SPDX-License-Identifier: GPL-3.0-or-later
"""Component catalog for insertion; every listed type has a Qt/GTK renderer."""

from PySide6.QtCore import Qt
from makebench.i18n import tr

CATEGORIES = {
    "layout": tr("Structure"),
    "content": tr("Content"),
    "input": tr("Input and actions"),
    "feedback": tr("Output and state"),
}
COMPONENTS = {
    "container": ("layout", tr("Groups elements in a row, column, grid or free position.")),
    "pages": ("layout", tr("A set of tabbed pages inside the same window.")),
    "page": ("layout", tr("A page that belongs to a set of tabs.")),
    "spacer": ("layout", tr("Takes up free space in the layout.")),
    "separator": ("layout", tr("Visually separates groups of controls.")),
    "label": ("content", tr("Text shown in the interface.")),
    "image": ("content", tr("Image imported and saved with the project.")),
    "button": ("input", tr("Fires a click event and its actions.")),
    "text_input": ("input", tr("Receives text typed by the user.")),
    "text_area": ("input", tr("Receives several lines of text typed by the user.")),
    "choice": ("input", tr("A list of options; the user picks one.")),
    "date": ("input", tr("A calendar date the user picks.")),
    "checkbox": ("input", tr("An option that can be checked or unchecked.")),
    "terminal": (
        "feedback",
        tr(
            "Interactive Linux terminal, with colors and keyboard. The preview never starts processes."
        ),
    ),
    "number": ("input", tr("A number the user types or adjusts, with limits and step.")),
    "slider": ("input", tr("A bar the user drags to pick a whole number in a range.")),
    "progress": ("feedback", tr("Shows a value between 0 and 100.")),
    "output": ("feedback", tr("Shows messages and task output.")),
}


def filter_library(window):
    """Search name/description and category without re-creating the selection or draggable items."""
    query = window.insert_search.text().casefold()
    category = window.insert_category.currentData()
    for index in range(window.palette.count()):
        item = window.palette.item(index)
        kind = item.data(Qt.ItemDataRole.UserRole)
        group, description = COMPONENTS[kind]
        item.setHidden(
            bool(category and group != category)
            or query not in (item.text() + " " + description).casefold()
        )
        item.setToolTip(description + "\n" + tr("Available in Qt and GTK4."))
    # Group headings depend on which rows are visible.
    window.palette.scheduleDelayedItemsLayout()
