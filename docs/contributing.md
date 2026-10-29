# Contributing

Bug reports, translations, documentation and code are all welcome. Issues and
pull requests can be written in English or Portuguese.

## Before you start

- For anything larger than a small fix, open an
  [issue](https://github.com/RichardSpinola/makebench/issues) first so we can
  agree on the approach.
- Read the [architecture](architecture.md). A few rules are not negotiable:
    - `makebench.core` never imports Qt.
    - Opening, editing, previewing, saving and building a project never run its
      code.
    - Changes to the project format need a reader for older formats and tests
      that open them.
    - No network access at run time, and no new runtime dependencies without
      discussion.

## Workflow

1. Set up a virtual environment as described in [Building and testing](building.md).
2. Make focused commits with clear messages in English.
3. Before opening a pull request, run:

    ```bash
    .venv/bin/ruff format src tests checks examples
    QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
    .venv/bin/python checks/i18n.py
    QT_QPA_PLATFORM=offscreen .venv/bin/python checks/blockly_smoke.py
    .venv/bin/python checks/docs.py
    ```

4. Add or update tests for the behavior you change. Interface changes should
   say how they were checked (screenshots are welcome).

## Code style

- Formatting is `ruff format` with a line length of 100 (configured in
  `pyproject.toml`).
- Docstrings and comments are in English. Every module, class and function has
  a short docstring that says what it guarantees, not how.
- New Python files start with an `SPDX-License-Identifier` line (see
  [License](#license)).
- Use the native Qt style and palette; do not add global style sheets.

## Text and translations

All user-visible text is written in English and wrapped in `tr()` or `ntr()`.
After adding or changing text, run `python checks/i18n.py --update` and, if you
can, add the Portuguese translation to `src/makebench/locale/pt_BR/makebench.po`.
New languages are welcome; see [Translations](building.md#translations).

Keep messages short and concrete: say what happened and what the person can do
next. Error dialogs use `editor/errors.show_error`, which keeps technical
details behind **Show details**.

## Documentation

This site is built with MkDocs Material from the `docs/` folder. Every page has
an English file (`page.md`) and a Portuguese one (`page.pt-BR.md`). The pages
under `reference/` and the keyboard shortcuts are generated from the code:
change the code and run `python checks/build_reference.py`, never edit them by
hand. To preview the site:

```bash
.venv/bin/pip install -r docs/requirements.txt
.venv/bin/mkdocs serve
```

## License

By contributing, you agree that your contributions are licensed like the code
they change: GPL-3.0-or-later for the editor (`editor/`), and the MIT license
for the runtime that exported applications include (`core/`, `runtime/`,
`gtk_runtime/`, `ui/`, `terminal/`, `portable/`, `i18n.py`). New files start
with the matching `SPDX-License-Identifier` line.
