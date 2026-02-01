#!/usr/bin/env python3
"""
Koan — Mission extraction

Extracts the next pending mission from missions.md, scoped to the "En attente" / "Pending"
section only. Prints the mission line to stdout (empty if none found).

This replaces the naive `grep -m1 "^- "` which could match lines from any section.

Usage:
    python3 extract_mission.py /path/to/instance/missions.md [project_name]

If project_name is given, only returns missions tagged [project:name] or untagged.
"""

import re
import sys
from pathlib import Path


def extract_next_mission(missions_path: str, project_name: str = "") -> str:
    """Return the first pending mission line, or empty string if none."""
    path = Path(missions_path)
    if not path.exists():
        return ""

    lines = path.read_text().splitlines()

    in_pending = False
    for line in lines:
        stripped = line.strip().lower()

        # Detect section boundaries
        if stripped in ("## en attente", "## pending"):
            in_pending = True
            continue
        elif stripped.startswith("## "):
            if in_pending:
                break  # Left the pending section
            continue

        if not in_pending:
            continue

        # Only match simple mission items (- prefix)
        if not line.strip().startswith("- "):
            continue

        # If project_name filter is set, check tag
        if project_name:
            tag_match = re.search(r"\[projet?:([a-zA-Z0-9_-]+)\]", line)
            if tag_match:
                if tag_match.group(1).lower() != project_name.lower():
                    continue  # Mission is for a different project
            # No tag = default project, always matches

        return line.strip()

    return ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <missions.md> [project_name]", file=sys.stderr)
        sys.exit(1)

    missions_file = sys.argv[1]
    proj = sys.argv[2] if len(sys.argv) > 2 else ""
    result = extract_next_mission(missions_file, proj)
    print(result)
