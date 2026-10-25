# SPDX-License-Identifier: GPL-3.0-or-later
"""Local control updates without clearing selection, popup or focus."""

from makebench.i18n import tr


def reconcile_combo(combo, entries, current):
    """Keep items and selection when only the label or another panel changed."""
    entries = list(entries)
    blocked = combo.blockSignals(True)
    try:
        existing = [combo.itemData(i) for i in range(combo.count())]
        wanted = [data for _, data in entries]
        if existing != wanted:
            combo.clear()
            for label, data in entries:
                combo.addItem(label, data)
        else:
            for index, (label, _) in enumerate(entries):
                if combo.itemText(index) != label:
                    combo.setItemText(index, label)
        index = combo.findData(current)
        if combo.currentIndex() != index:
            combo.setCurrentIndex(index)
    finally:
        combo.blockSignals(blocked)


def name_unlabeled_buttons(root):
    """Give screen readers a name for the buttons Qt adds by itself.

    Search fields get a clear button and overflowing toolbars/menus an extension
    button; neither has text, so both get an accessible name and tooltip.
    """
    from PySide6.QtWidgets import QLineEdit, QToolButton

    from makebench.i18n import tr

    from PySide6.QtGui import QAction

    for field in root.findChildren(QLineEdit):
        # Naming Qt's internal clear action survives the button being re-created on restyle.
        clear = field.findChild(QAction, "_q_qlineeditclearaction")
        if clear is not None and not clear.toolTip().strip():
            clear.setText(tr("Clear"))
            clear.setToolTip(tr("Clear"))
        for button in field.findChildren(QToolButton):
            if not (button.text() or button.accessibleName() or button.toolTip()):
                button.setAccessibleName(tr("Clear"))
                button.setToolTip(tr("Clear"))
    for button in root.findChildren(QToolButton):
        if button.objectName() in {"qt_toolbar_ext_button", "qt_menubar_ext_button"}:
            button.setAccessibleName(tr("More options"))
            button.setToolTip(tr("More options"))
