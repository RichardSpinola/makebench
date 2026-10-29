# Questions and problems

## Installing and starting

**The AppImage does not start.**
:   Make it executable (`chmod +x Makebench-*.AppImage`). If the system has no
    FUSE, run it with `--appimage-extract-and-run`. The AppImage needs glibc
    2.39 or newer (Ubuntu 24.04, Fedora 40 and later). See
    [Install](install.md).

**GTK preview or GTK apps do not work.**
:   GTK apps need GTK 4 and PyGObject from your distribution; the GTK preview
    in the editor also needs `gtk4-broadwayd`. **Help › Environment
    diagnostics…** lists what is present and what is missing. Qt projects work
    without any of it.

**How do I switch the interface to Portuguese?**
:   **View › Preferences… › Appearance › Interface language**, then restart
    Makebench.

## Projects and files

**Makebench asked to upgrade my project.**
:   Projects made with an older Makebench open normally. Saving writes the
    lowest format that holds the features the project uses; when that is newer
    than the file's format, the previous file is kept next to it as
    `<name>.makebench.json.bak-vN` (N is the old format number). A project
    made by a newer Makebench is refused with a clear message instead of being
    damaged. See [Compatibility](compatibility.md).

**I edited the Python file in another editor.**
:   Makebench notices it. If you have no unsaved changes, it reloads the file;
    otherwise it shows *Functions changed outside Makebench.* with
    **Reload file** and **Keep my version**.

**Does opening a project or an example run its code?**
:   No. Opening, editing, previewing, saving and building never run project
    code. Only **Run › Test application** (++f5++) and **Debug application**
    (++f9++) do.

## Safety

**Is the app I test isolated from my computer?**
:   No. Testing runs the project's logic, programs and scripts with your user's
    permissions, like any program you start. Makebench shows what runs and lets
    you stop it, but it is not a sandbox. Only open projects you trust, as you
    would with a script. Exported Flatpak apps do run in the Flatpak sandbox.

**Can an app ask for administrator rights?**
:   Only through Polkit, for the administrative actions declared in its logic
    (**Project › Application settings… › Permissions** lists them). The system
    asks for the password in its own window; Makebench never asks for or sees
    passwords.

**Can a plugin or theme harm my computer?**
:   Themes are only colors and cannot run code. Plugins are Python code that
    runs inside the editor with your permissions; Makebench lists what each one
    asks for before you turn it on. Install plugins only from sources you
    trust. See [Writing plugins](plugins.md).

## Data

**Where are my app's records?**
:   In a SQLite file. Exported apps use `~/.local/share/<app id>/data.sqlite`;
    tests in the editor use a separate database, so testing never touches the
    data of an installed app. See [Data and charts](data.md#where-the-data-lives).

**How do I start over with empty test data?**
:   Click **Delete test data…** in the Data panel.

## Exported apps

**My window is not centered (or not on top) under GNOME.**
:   GTK 4 on Wayland lets the desktop place windows, so **Centered** and
    **Always on top** are ignored there. Qt apps honor them. The export check
    warns about it.

**Why is my Qt package so large?**
:   A Qt package carries its own Qt. A **Web view** window adds Qt WebEngine,
    which is much larger. GTK apps use the system's GTK and the **Light HTML
    app** template uses the system's WebKitGTK. See [Exporting](export.md).

**Do I have to use the GPL for my app?**
:   No. The runtime inside exported apps is MIT, so you choose your app's
    license. The editor itself is GPL-3.0-or-later.

## Still stuck?

Open an issue on
[GitHub](https://github.com/RichardSpinola/makebench/issues) with what you did,
what happened and the text of **Help › Environment diagnostics…**. Issues can be
written in English or Portuguese.
