"""Workspace directory scanner — auto-discovers projects.

Scans KOAN_ROOT/workspace/ for immediate child directories (including
symlinks), returning (name, resolved_path) tuples for each discovered project.

Projects are discovered by their directory name — no configuration needed.
"""

import logging
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)


def discover_workspace_projects(koan_root: str) -> List[Tuple[str, str]]:
    """Scan workspace/ directory for projects.

    Returns sorted list of (name, resolved_path) tuples.
    Skips hidden directories, broken symlinks, and non-directories.
    Returns empty list if workspace/ doesn't exist.
    """
    workspace_dir = Path(koan_root) / "workspace"
    if not workspace_dir.is_dir():
        return []

    projects = []
    try:
        entries = sorted(workspace_dir.iterdir(), key=lambda p: p.name.lower())
    except OSError as e:
        logger.warning("Cannot read workspace directory: %s", e)
        return []

    for entry in entries:
        name = entry.name

        # Skip hidden directories and special files
        if name.startswith("."):
            continue

        # Skip non-directory files (README.md, etc.)
        if entry.is_file():
            continue

        # Resolve symlinks
        try:
            resolved = entry.resolve()
        except OSError as e:
            logger.warning("Workspace: cannot resolve '%s': %s", name, e)
            continue

        # Validate target is a directory
        if not resolved.is_dir():
            logger.warning("Workspace: '%s' points to non-directory: %s", name, resolved)
            continue

        projects.append((name, str(resolved)))

    return projects
