"""Kōan refactor skill -- queue a refactoring mission."""

import re


def handle(ctx):
    """Handle /refactor command -- queue a refactoring mission.

    Usage:
        /refactor https://github.com/owner/repo/pull/42
        /refactor https://github.com/owner/repo/issues/42
        /refactor src/utils.py
    """
    args = ctx.args.strip()

    if not args:
        return (
            "Usage: /refactor <github-url-or-path>\n"
            "Ex: /refactor https://github.com/sukria/koan/pull/42\n"
            "Ex: /refactor src/utils.py\n\n"
            "Queues a refactoring mission."
        )

    from app.utils import get_known_projects, insert_pending_mission, project_name_for_path, resolve_project_path

    # Try to extract a GitHub URL
    url_match = re.search(r'https?://github\.com/[^\s]+/(?:pull|issues)/\d+', args)
    if url_match:
        url = url_match.group(0).split("#")[0]
        parts = re.match(r'https?://github\.com/([^/]+)/([^/]+)/(?:pull|issues)/(\d+)', url)
        if not parts:
            return "\u274c Could not parse URL."

        owner, repo, number = parts.group(1), parts.group(2), parts.group(3)

        project_path = resolve_project_path(repo, owner=owner)
        if not project_path:
            known = ", ".join(n for n, _ in get_known_projects()) or "none"
            return (
                f"\u274c Could not find local project matching repo '{repo}'.\n"
                f"Known projects: {known}"
            )

        project_name = project_name_for_path(project_path)

        mission_entry = f"- [project:{project_name}] /refactor {url}"
        missions_path = ctx.instance_dir / "missions.md"
        insert_pending_mission(missions_path, mission_entry)

        url_type = "PR" if "/pull/" in url else "issue"
        return f"Refactor queued for {url_type} #{number} ({owner}/{repo})"

    # Treat as a file path — no URL found
    file_path = args.strip()
    mission_entry = f"- /refactor {file_path}"
    missions_path = ctx.instance_dir / "missions.md"
    insert_pending_mission(missions_path, mission_entry)

    return f"Refactor queued for {file_path}"
