"""Local control updates without clearing selection, popup or focus."""


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
