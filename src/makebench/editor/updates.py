"""Transações de apresentação: uma edição não mostra painéis intermediários vazios."""
from contextlib import contextmanager


@contextmanager
def hold_updates(widget):
    """Agrupa repinturas e respeita uma transação externa já em andamento."""
    enabled = widget.updatesEnabled()
    if enabled:
        widget.setUpdatesEnabled(False)
    try:
        yield
    finally:
        if enabled:
            widget.setUpdatesEnabled(True)
            widget.update()
