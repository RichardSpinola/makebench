# Examples

Makebench comes with ready-made projects. Choose **File › Open example…** (also
on the start screen): Makebench copies the example into your projects folder
and opens the copy, so you can change it freely. The original never changes.

Opening an example runs nothing. Press ++f5++ to test it.

## Start here

**My notes** — a saved list, CSV export
:   One window with a text field, a long text, a table and two buttons. Notes
    are saved in a collection and exported to CSV. It is the app built in the
    [blocks tutorial](tutorial-blocks.md).

**Welcome wizard** — states and two windows
:   A wizard that changes its content with **states** instead of separate
    windows, and opens a second window at the end. Good for learning the
    **Map**: each line between cards is a real transition.

## Logic, tasks and debugging

**Task center** — tasks, questions and live output
:   Runs programs and Bash scripts as supervised tasks, asks the person
    questions and shows the output live in an output panel.

**Terminal and debugging** — breakpoints, step by step
:   An interactive terminal component and a flow prepared for the debugger:
    set breakpoints, press ++f9++ and step through it.

**Python twins**
:   *Welcome wizard · Python*, *Task center · Python* and
    *Terminal and debugging · Python* do exactly the same as the three
    examples above, in Python. They were produced with **Project › Convert to
    Python…**, so you can compare blocks and code side by side.

**Python modules** — several files
:   A Python project whose code is split into modules under `makebench_user/`.

## Data

**Bookshop** — books, clients, sales and stock
:   Three collections: *Books* (title, price, stock), *Clients* (name) and
    *Sales*, whose *Client* and *Book* fields are references. Recording a sale
    checks and lowers the stock, computes the total and updates the cash; a
    sale can be marked as delivered. See the [data guide](data.md).

## Everything at once

**Complete workshop** — every component, logic in blocks
:   Uses every kind of component, several windows with different looks, a
    state, a task, a terminal, block functions, modules and a breakpoint. It
    has a Data page with authors, books, a table, a chart and CSV export. Its
    *Test guide* window lists what to try.

## Plugin examples

The repository's [`examples/plugins`](https://github.com/RichardSpinola/makebench/tree/main/examples/plugins)
folder has small plugins to read before [writing your own](plugins.md).

!!! note "Language"
    With the interface in Portuguese, **Open example…** offers the Portuguese
    versions of the same projects.
