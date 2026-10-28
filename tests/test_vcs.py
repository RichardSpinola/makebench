# SPDX-License-Identifier: GPL-3.0-or-later
"""Version history in Git: opt-in, non-destructive, offline-testable."""

import support  # noqa: F401  (first: isolates settings and data)
import json
import os
import tempfile
import unittest
from pathlib import Path

from makebench.core import vcs

HOME_ENV = {"HOME", "XDG_CONFIG_HOME", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"}


@unittest.skipUnless(vcs.available(), "git is not installed")
class VersionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.saved_env = {k: os.environ.get(k) for k in HOME_ENV}
        os.environ["HOME"] = str(base / "home")
        os.environ["GIT_CONFIG_GLOBAL"] = str(base / "gitconfig")
        os.environ["GIT_CONFIG_SYSTEM"] = os.devnull
        (base / "home").mkdir()
        self.addCleanup(self.restore_env)
        self.root = base / "my project"
        self.root.mkdir()
        self.file = self.root / "app.makebench.json"
        self.write(1)

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def write(self, children):
        window = {
            "id": "w",
            "kind": "window",
            "children": [{"id": f"c{i}"} for i in range(children)],
        }
        self.file.write_text(json.dumps({"ui": window, "workflows": []}))

    def test_nothing_is_created_until_init(self):
        self.assertFalse(vcs.is_repo(self.root))
        self.assertFalse((self.root / ".git").exists())

    def test_save_versions_and_restore_without_losing_any(self):
        vcs.init(self.root)
        first = vcs.commit_all(self.root, "one")
        self.write(3)
        (self.root / "extra.py").write_text("x = 1\n")
        second = vcs.commit_all(self.root, "two")
        self.assertNotEqual(first, second)
        self.assertIsNone(vcs.commit_all(self.root, "nothing changed"))
        vcs.restore(self.root, first)
        self.assertEqual(len(json.loads(self.file.read_text())["ui"]["children"]), 1)
        self.assertFalse((self.root / "extra.py").exists())
        revs = [v.rev for v in vcs.log(self.root)]
        self.assertIn(first, revs)
        self.assertIn(second, revs)
        self.assertGreaterEqual(len(revs), 3)
        vcs.restore(self.root, second)
        self.assertTrue((self.root / "extra.py").is_file())

    def test_unsaved_edit_is_kept_as_a_version_before_restoring(self):
        vcs.init(self.root)
        first = vcs.commit_all(self.root, "one")
        self.write(5)
        vcs.restore(self.root, first)
        subjects = [v.subject for v in vcs.log(self.root)]
        self.assertIn("Before restoring", subjects)

    def test_names_and_descriptions(self):
        vcs.init(self.root)
        first = vcs.commit_all(self.root, "one")
        self.write(4)
        second = vcs.commit_all(self.root, "two")
        vcs.label(self.root, first, "Login ready")
        names = {v.rev: v.names for v in vcs.log(self.root)}
        self.assertEqual(names[first], ["Login ready"])
        self.assertIn("+3 components", vcs.describe(self.root, second))

    def test_missing_identity_does_not_break_saving(self):
        vcs.init(self.root)
        self.assertEqual(vcs.identity(self.root), ("", ""))
        self.assertTrue(vcs.commit_all(self.root, "one"))
        vcs.set_identity(self.root, "Ana", "ana@example.com")
        self.assertEqual(vcs.identity(self.root), ("Ana", "ana@example.com"))
        self.assertEqual(vcs._get(self.root, "user.name"), "Ana")
        self.assertFalse(Path(os.environ["GIT_CONFIG_GLOBAL"]).exists())

    def test_gitignore_keeps_user_lines(self):
        (self.root / ".gitignore").write_text("secret.txt")
        vcs.init(self.root)
        vcs.init(self.root)
        text = (self.root / ".gitignore").read_text()
        self.assertTrue(text.startswith("secret.txt\n"))
        self.assertEqual(text.count("*.bak-v*"), 1)

    def test_files_changed_outside_are_recorded(self):
        vcs.init(self.root)
        vcs.commit_all(self.root, "one")
        (self.root / "notes.py").write_text("y = 2\n")
        self.assertTrue(vcs.commit_all(self.root, "outside"))

    def test_remote_roundtrip_with_a_local_server(self):
        server = Path(self.temp.name) / "server.git"
        vcs._run(self.temp.name, ["init", "-q", "--bare", str(server)])
        vcs.init(self.root)
        vcs.commit_all(self.root, "one")
        vcs.set_remote(self.root, str(server))
        vcs.set_remote(self.root, str(server))
        self.assertEqual(list(vcs.remotes(self.root)), ["origin"])
        vcs.push(self.root)
        vcs.fetch(self.root)
        self.assertEqual(vcs.ahead_behind(self.root), (0, 0))
        self.write(2)
        vcs.commit_all(self.root, "two")
        vcs.fetch(self.root)
        self.assertEqual(vcs.ahead_behind(self.root), (1, 0))
        other = Path(self.temp.name) / "other"
        vcs._run(self.temp.name, ["clone", "-q", str(server), str(other)])
        vcs.pull(other)
        (other / "n.txt").write_text("n")
        vcs.set_identity(other, "B", "b@example.com")
        vcs.commit_all(other, "other side")
        vcs.push(other)
        vcs.fetch(self.root)
        self.write(9)
        vcs.commit_all(self.root, "diverge")
        with self.assertRaises(vcs.VcsError):
            vcs.pull(self.root)
        with self.assertRaises(vcs.VcsError):
            vcs.push(self.root)

    def test_bad_remote_address_is_refused(self):
        vcs.init(self.root)
        for bad in ("", "--upload-pack=x", "a b"):
            with self.assertRaises(vcs.VcsError):
                vcs.set_remote(self.root, bad)

    def test_clone_from_a_local_server(self):
        vcs.init(self.root)
        vcs.commit_all(self.root, "first")
        server = Path(self.temp.name) / "server.git"
        vcs._run(self.temp.name, ["init", "--bare", str(server)])
        vcs.set_remote(self.root, str(server))
        vcs.push(self.root)
        parent = Path(self.temp.name) / "downloads"
        target = vcs.clone(str(server), parent)
        self.assertEqual(target, parent / "server")
        self.assertTrue((target / "app.makebench.json").is_file())
        with self.assertRaises(vcs.VcsError):
            vcs.clone(str(server), parent)

    def test_clone_failure_leaves_nothing_and_bad_addresses_are_refused(self):
        parent = Path(self.temp.name) / "downloads"
        with self.assertRaises(vcs.VcsError):
            vcs.clone(str(Path(self.temp.name) / "nothing.git"), parent)
        self.assertFalse((parent / "nothing").exists())
        for bad in ("", "--upload-pack=x", "a b", "ext::sh -c x"):
            with self.assertRaises(vcs.VcsError):
                vcs.clone(bad, parent)
        self.assertEqual(vcs.repo_name("https://github.com/you/app.git"), "app")
        self.assertEqual(vcs.repo_name("git@host:you/my app/"), "my-app")


if __name__ == "__main__":
    unittest.main()
