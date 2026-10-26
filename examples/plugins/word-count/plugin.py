# SPDX-License-Identifier: MIT
"""Example plugin: counts the words written in the labels and buttons of the project."""


def register(api):
    def count_words(project):
        total = 0
        for window in project.roots:
            for item in window.walk():
                total += len(str(item.properties.get("text", "")).split())
        # Show the result in the first window's title so the change is visible and undoable.
        project.root.properties["title"] = (
            f"{project.root.properties.get('title', '')} ({total} words)"
        )

    api.add_command("Count words in the interface", count_words)
    api.add_snippet("greet_user", 'ctx.message("Hello, " + ctx.read("name", "text"))\n')
