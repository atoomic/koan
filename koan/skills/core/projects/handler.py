"""Kōan projects skill — list configured projects."""

import os


def _shorten_path(path):
    """Replace the user's HOME directory prefix with ~ for shorter display."""
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def handle(ctx):
    """Handle /projects command."""
    from app.utils import get_known_projects

    projects = get_known_projects()

    if not projects:
        return "No projects configured."

    lines = ["Configured projects:"]
    for name, path in projects:
        lines.append(f"  - {name}: {_shorten_path(path)}")
    return "\n".join(lines)
