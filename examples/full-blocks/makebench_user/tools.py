"""Own module of the workshop: pure Python helpers, imported by actions."""


def format_status(visits, name):
    """Text shown in the status line."""
    return "{} · {}".format(name or "?", visits)
