"""Kōan implement skill -- queue an implementation mission for a GitHub issue."""

import re


def handle(ctx):
    """Handle /implement command -- queue a mission to implement a GitHub issue.

    Usage:
        /implement https://github.com/owner/repo/issues/42
        /implement https://github.com/owner/repo/issues/42 phase 1 only
    """
    args = ctx.args.strip()

    if not args:
        return (
            "Usage: /implement <github-issue-url> [context]\n"
            "Ex: /implement https://github.com/sukria/koan/issues/42\n"
            "Ex: /implement https://github.com/sukria/koan/issues/42 phase 1 only\n\n"
            "Queues a mission to implement the described issue."
        )

    # Extract URL from args
    url_match = re.search(r'https?://github\.com/[^\s]+/issues/\d+', args)
    if not url_match:
        return (
            "\u274c No valid GitHub issue URL found.\n"
            "Ex: /implement https://github.com/owner/repo/issues/123"
        )

    issue_url = url_match.group(0).split("#")[0]

    # Extract additional context (everything after the URL)
    context = args[url_match.end():].strip()

    from app.utils import get_known_projects, insert_pending_mission, project_name_for_path, resolve_project_path

    # Parse owner/repo from URL
    parts = re.match(r'https?://github\.com/([^/]+)/([^/]+)/issues/(\d+)', issue_url)
    if not parts:
        return "\u274c Could not parse issue URL."

    owner, repo, issue_number = parts.group(1), parts.group(2), parts.group(3)

    project_path = resolve_project_path(repo, owner=owner)
    if not project_path:
        known = ", ".join(n for n, _ in get_known_projects()) or "none"
        return (
            f"\u274c Could not find local project matching repo '{repo}'.\n"
            f"Known projects: {known}"
        )

    project_name = project_name_for_path(project_path)

    # Build mission entry
    mission_text = f"/implement {issue_url}"
    if context:
        mission_text += f" {context}"

    mission_entry = f"- [project:{project_name}] {mission_text}"
    missions_path = ctx.instance_dir / "missions.md"
    insert_pending_mission(missions_path, mission_entry)

    suffix = f" — {context}" if context else ""
    return f"Implementation queued for issue #{issue_number} ({owner}/{repo}){suffix}"
