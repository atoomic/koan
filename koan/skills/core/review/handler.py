"""Kōan review skill -- queue a code review mission."""

import re


def handle(ctx):
    """Handle /review command -- queue a code review mission.

    Usage:
        /review https://github.com/owner/repo/pull/42
        /review https://github.com/owner/repo/issues/42
    """
    args = ctx.args.strip()

    if not args:
        return (
            "Usage: /review <github-url>\n"
            "Ex: /review https://github.com/sukria/koan/pull/42\n"
            "Ex: /review https://github.com/sukria/koan/issues/42\n\n"
            "Queues a code review mission."
        )

    # Accept both PR and issue URLs
    url_match = re.search(r'https?://github\.com/[^\s]+/(?:pull|issues)/\d+', args)
    if not url_match:
        return (
            "\u274c No valid GitHub PR or issue URL found.\n"
            "Ex: /review https://github.com/owner/repo/pull/123"
        )

    url = url_match.group(0).split("#")[0]

    from app.utils import get_known_projects, insert_pending_mission, project_name_for_path, resolve_project_path

    # Parse owner/repo/number from URL
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

    mission_entry = f"- [project:{project_name}] /review {url}"
    missions_path = ctx.instance_dir / "missions.md"
    insert_pending_mission(missions_path, mission_entry)

    url_type = "PR" if "/pull/" in url else "issue"
    return f"Review queued for {url_type} #{number} ({owner}/{repo})"
