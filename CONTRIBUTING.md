# Contributing to Makebench

Thank you for helping. Bug reports, translations, documentation and code are
all welcome. Issues and pull requests can be written in English or Portuguese.

## Before you start

- For anything larger than a small fix, open an issue first so we can agree on
  the approach.
- Read [docs/architecture.md](docs/architecture.md). A few rules are not
  negotiable:
  - `makebench.core` never imports Qt.
  - Opening, editing, previewing, saving and building a project never run its code.
  - Changes to the project format need a reader for older formats and tests
    that open them.
  - No network access at run time, and no new runtime dependencies without
    discussion.

## Workflow

1. Set up a virtual environment as described in [docs/building.md](docs/building.md).
2. Make focused commits with clear messages in English.
3. Before opening a pull request, run:

   ```bash
   .venv/bin/ruff format src tests checks examples
   QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
   .venv/bin/python checks/i18n.py
   QT_QPA_PLATFORM=offscreen .venv/bin/python checks/blockly_smoke.py
   ```

4. Add or update tests for the behavior you change. Interface changes should
   say how they were checked (screenshots are welcome).

## Code style

- Formatting is `ruff format` with a line length of 100 (configured in
  `pyproject.toml`).
- Docstrings and comments are in English. Every module, class and function has
  a short docstring that says what it guarantees, not how.
- New Python files start with `# SPDX-License-Identifier: GPL-3.0-or-later`.
- Use the native Qt style and palette; do not add global style sheets.

## User-visible text and translations

All user-visible text is written in English and wrapped in `tr()` or `ntr()`.
After adding or changing text, run `python checks/i18n.py --update` and, if you
can, add the Portuguese translation to `src/makebench/locale/pt_BR/makebench.po`.
New languages are welcome; see [Translations](docs/building.md#translations).

Keep messages short and concrete: say what happened and what the user can do
next. Error dialogs use `editor/errors.show_error`, which keeps technical
details behind **Show details**.

## License

By contributing, you agree that your contributions are licensed under the
[GPL-3.0-or-later](LICENSE), with the [Makebench Runtime Exception](RUNTIME-EXCEPTION.txt)
for runtime code that exported applications include.
