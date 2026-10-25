# Third-party components

Makebench is free software under the GNU General Public License, version 3 or
later (see `GPL-3.0.txt`). Applications exported by Makebench may also use the
Makebench Runtime Exception (`RUNTIME-EXCEPTION.txt`). The components below keep
their own licenses; packages that redistribute them must keep these notices.

## Blockly 13.4.0 — Apache-2.0

Block editor used by the Logic area, embedded unmodified in
`makebench/web/vendor/blockly` together with its `LICENSE` file, the English and
Brazilian Portuguese message files and its media. Copyright Google LLC.
Source: https://registry.npmjs.org/blockly/-/blockly-13.4.0.tgz (integrity in
`vendor-lock.json`).

## PySide6 / Qt 6.11.2 — LGPL-3.0 (also GPL and commercial)

Qt for Python, used by the editor and by Qt applications. Installed as a
separate, unmodified dependency. Source and licenses: https://www.qt.io/qt-for-python
and https://code.qt.io.

## pyte 0.8.2 — LGPL-3.0-or-later

Copyright (C) 2011-2013 Sergei Lebedev, https://github.com/selectel/pyte.
Terminal emulation shared by the Qt and GTK terminals. The original license text
ships as `pyte-LICENSE.txt`; the LGPL builds on the GPL text in `GPL-3.0.txt`.
pyte is a separate, unmodified Python dependency that can be replaced in the
application's environment. Source of the version used:
https://files.pythonhosted.org/packages/source/p/pyte/pyte-0.8.2.tar.gz

pyte depends on wcwidth (MIT license); distributed packages must keep its
metadata and license notice too.

## Optional system components

The GTK backend uses GTK 4, PyGObject and, optionally, libadwaita (LGPL-2.1-or-later)
from the system or the packaging SDK. Native packages built by Makebench copy the
license and notice files of the libraries they bundle into
`usr/share/third-party-licenses` and `usr/share/common-licenses`.

These notices describe Makebench's components. They do not decide the license of
an application you build with Makebench; choose that license yourself.
