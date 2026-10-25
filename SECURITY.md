# Security

## What Makebench protects, and what it does not

- Opening, editing, previewing, saving and building a project never run its
  Python, scripts or programs. Code is parsed statically.
- The Blockly page runs in a temporary WebEngine profile with no network access
  and a bridge that only exchanges JSON. It cannot run commands or read files.
- Project metadata is sanitised before it goes into package recipes and desktop
  entries.
- Administrative tasks use Polkit (`pkexec`) and the system's authentication
  dialog. Makebench never asks for, sees or stores passwords.

**Testing a project (F5/F9) or running an exported application is not a
sandbox.** The project's code runs with your user's permissions, like any other
program you run. Only test projects you trust, and review projects from others
before pressing F5. Flatpak exports keep the Flatpak sandbox; other formats do not
add one.

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub's private vulnerability reporting](https://github.com/RichardSpinola/makebench/security/advisories/new)
rather than in a public issue. Include the Makebench version, your distribution,
and steps or a small project that reproduces the problem.

Examples of what counts:

- Project code, scripts or programs running when a project is only opened,
  previewed, saved or built.
- The Blockly page reaching the network, files or commands.
- Package metadata injecting commands or desktop entries.
- An administrative task running without the system's authorisation.

You should get an answer within two weeks. Makebench is an alpha maintained by
volunteers, so fixes land on the main branch; there are no supported release
branches yet.
