# Exporting

When the app works with ++f5++, turn it into something other people can
install. Choose **Project › Export application…** (++ctrl+shift+e++).

Building never runs your project: Makebench only packs its files.

## 1. Who is it for?

The window starts by asking who will use the app; each answer is a format.

| Answer | Format | What you get |
|---|---|---|
| **Anyone on Linux** | AppImage | one file that runs without installing |
| **Ubuntu, Debian or Mint** | DEB | installs with a menu entry (built for Ubuntu 24.04 x86_64) |
| **Fedora or openSUSE** | RPM | installs with a menu entry (built for Fedora 44 x86_64) |
| **Any distribution, isolated** | Flatpak | runs apart from the system |
| **Programmers** | Python source | a ZIP with the Python code, to read and change |

DEB, RPM and AppImage carry Python and the toolkit inside, so nothing else has
to be installed. Flatpak uses the GNOME runtime for GTK apps and the KDE
runtime for Qt apps, and keeps the Flatpak sandbox. The Python source needs
Python and the toolkit on the target computer (its `README` says how to run
it).

**Application…** edits the name, identifier, version, icon and language of the
app. The same settings are in **Project › Application settings…**.

## 2. Verify

**Check** looks for problems before building: missing functions, components
that a toolkit does not support, window options that GTK on Wayland ignores,
large dependencies (such as Qt WebEngine) and similar. Fix what it reports, or
build anyway if a warning does not matter to you.

## 3. Build

**Build with** chooses the tools:

- **Tools prepared by Makebench**: Makebench downloads and prepares the build
  tools in rootless Podman containers, cached in `~/.cache/makebench/builders`.
  Nothing is installed on your system.
- **System tools**: uses the packaging tools already installed.
- **Automatic**: picks whichever is ready.

Preparing tools is always a separate step (**Prepare tools…**) with visible
output and a **Cancel** button. Then click **Build…** and choose where to save.
**Show details** shows the full log; at the end, **Open folder** and
**Copy path** take you to the result.

**Export only the recipe** produces a ZIP with the build files instead of a
package, for building elsewhere.

## Qt, GTK or a light HTML app

The toolkit is chosen when the project is created (**Application look**) and
can be changed in the application settings.

| | Qt | GTK 4 | Light HTML app |
|---|---|---|---|
| Look | the same on every desktop | the GNOME (Adwaita) look | one HTML page in a GTK window |
| What the package carries | its own Qt (PySide6 Essentials) | uses the system's GTK | uses the system's WebKitGTK |
| Measured on *Complete workshop* | opens in about 0.6 s, about 125 MB | about 2 s, about 185 MB | — |

**Light HTML app** is a template in **New project**. Edit its page with the
official **Web view** plugin (**Plugins › Edit Web view page…**, after turning
the plugin on). A Web view window on **Qt** needs Qt WebEngine, which makes the
package much larger; Check warns about it.

## Window options in exported apps

- **Full screen** starts the window in full screen; in Qt apps ++f11++ toggles
  it.
- **Centered** and **Always on top** work in Qt; GTK 4 on Wayland ignores them,
  and Check says so.
- Menu items can have a shortcut after `|`, such as `Save | Ctrl+S`; it works
  in the exported app.

## The Makebench editor as an AppImage

In the **Export** field, **Makebench editor (AppImage)** builds the editor
itself, with the examples, as one AppImage. This is how the releases are made.

## Licenses

The runtime that goes into your app is under the MIT license, so you choose the
license of your own app. Third-party parts (PySide6/Qt, GTK and others) keep
their own licenses; the exported app includes their notices.
