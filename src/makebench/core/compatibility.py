"""Python syntax compatibility without importing project files."""

import ast
from makebench.i18n import tr

SUPPORTED_MINORS = (12, 13, 14)


def syntax_error(source, minor):
    """Return a diagnostic for the target grammar; never evaluates imports or calls."""
    from .source import source_files

    for name, text in source_files(source).items():
        try:
            ast.parse(text, feature_version=(3, minor))
        except (SyntaxError, ValueError) as exc:
            return tr(
                "{name}: your Python is incompatible with the target Python 3.{minor}: {error}"
            ).format(name=name, minor=minor, error=exc)
    return None


def minimum_minor(source):
    """Infer the lowest supported grammar, without promising to validate dynamic APIs."""
    return next((minor for minor in SUPPORTED_MINORS if syntax_error(source, minor) is None), None)
