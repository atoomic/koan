"""Kōan projects skill — list configured projects."""


def handle(ctx):
    """Handle /projects command."""
    from app.utils import get_known_projects

    projects = get_known_projects()

    if not projects:
        return "No projects configured."

    lines = ["Configured projects:"]
    for name, path in projects:
        lines.append(f"  - {name} ({path})")
    return "\n".join(lines)
