#!/usr/bin/env python3
"""
Kōan Cost Tracker — Per-mission token cost tracking.

Records token usage for each mission run and provides summaries.
Data stored in instance/cost_history.json.

CLI usage (called from run.sh):
    cost_tracker.py record <claude_json> <instance_dir> <project> [mission_title]

Library usage (called from awake.py):
    from app.cost_tracker import get_cost_summary
    summary = get_cost_summary(instance_dir)
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.utils import atomic_write


COST_FILE = "cost_history.json"
MAX_HISTORY_DAYS = 30


def _load_history(instance_dir: Path) -> List[Dict]:
    cost_file = instance_dir / COST_FILE
    if cost_file.exists():
        try:
            return json.loads(cost_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_history(instance_dir: Path, history: List[Dict]):
    cost_file = instance_dir / COST_FILE
    atomic_write(cost_file, json.dumps(history, indent=2) + "\n")


def _prune_old_entries(history: List[Dict]) -> List[Dict]:
    cutoff = (datetime.now() - timedelta(days=MAX_HISTORY_DAYS)).isoformat()
    return [e for e in history if e.get("timestamp", "") >= cutoff]


def _extract_tokens(claude_json_path: Path) -> Optional[Dict[str, int]]:
    """Extract input/output tokens from Claude JSON output."""
    try:
        data = json.loads(claude_json_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    # Try top-level fields
    inp = data.get("input_tokens", 0)
    out = data.get("output_tokens", 0)
    if inp or out:
        return {"input_tokens": inp, "output_tokens": out}

    # Try nested usage object
    usage = data.get("usage", {})
    if isinstance(usage, dict):
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        if inp or out:
            return {"input_tokens": inp, "output_tokens": out}

    # Try stats or metadata
    for key in ("stats", "metadata", "session"):
        sub = data.get(key, {})
        if isinstance(sub, dict):
            inp = sub.get("input_tokens", 0)
            out = sub.get("output_tokens", 0)
            if inp or out:
                return {"input_tokens": inp, "output_tokens": out}

    return None


def record_mission_cost(
    claude_json_path: Path,
    instance_dir: Path,
    project: str,
    mission: str = "",
):
    """Record token cost for a mission run."""
    tokens = _extract_tokens(claude_json_path)
    if tokens is None:
        return

    entry = {
        "timestamp": datetime.now().isoformat(),
        "project": project,
        "mission": mission or "(autonomous)",
        "input_tokens": tokens["input_tokens"],
        "output_tokens": tokens["output_tokens"],
        "total_tokens": tokens["input_tokens"] + tokens["output_tokens"],
    }

    history = _load_history(instance_dir)
    history.append(entry)
    history = _prune_old_entries(history)
    _save_history(instance_dir, history)


def _format_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def get_cost_summary(
    instance_dir: Path,
    project: Optional[str] = None,
    days: int = 7,
) -> str:
    """Build a human-readable cost summary."""
    history = _load_history(instance_dir)
    if not history:
        return "No cost data yet. Costs are tracked after each mission run."

    now = datetime.now()
    cutoff = (now - timedelta(days=days)).isoformat()
    entries = [e for e in history if e.get("timestamp", "") >= cutoff]

    if project:
        entries = [e for e in entries if e.get("project") == project]

    if not entries:
        scope = f" for {project}" if project else ""
        return f"No cost data{scope} in the last {days} days."

    # Today's missions
    today = now.strftime("%Y-%m-%d")
    today_entries = [e for e in entries if e["timestamp"].startswith(today)]

    # Per-project totals
    by_project: Dict[str, int] = {}
    total_tokens = 0
    for e in entries:
        proj = e.get("project", "unknown")
        tokens = e.get("total_tokens", 0)
        by_project[proj] = by_project.get(proj, 0) + tokens
        total_tokens += tokens

    # Build output
    lines = []
    scope = f" ({project})" if project else ""
    lines.append(f"Token costs — last {days} days{scope}")
    lines.append("")

    # Today's breakdown
    if today_entries:
        lines.append(f"Today ({today}):")
        for e in today_entries:
            mission = e.get("mission", "?")
            if len(mission) > 40:
                mission = mission[:37] + "..."
            total = _format_tokens(e["total_tokens"])
            inp = _format_tokens(e["input_tokens"])
            out = _format_tokens(e["output_tokens"])
            proj = e.get("project", "?")
            lines.append(f"  [{proj}] {mission}")
            lines.append(f"    {total} total ({inp} in / {out} out)")
        lines.append("")

    # Previous days (grouped by date)
    older = [e for e in entries if not e["timestamp"].startswith(today)]
    if older:
        by_date: Dict[str, list] = {}
        for e in older:
            day = e["timestamp"][:10]
            by_date.setdefault(day, []).append(e)
        for day in sorted(by_date, reverse=True):
            day_entries = by_date[day]
            day_total = sum(e.get("total_tokens", 0) for e in day_entries)
            lines.append(f"{day}: {len(day_entries)} runs, {_format_tokens(day_total)}")
            for e in day_entries:
                mission = e.get("mission", "?")
                if len(mission) > 40:
                    mission = mission[:37] + "..."
                proj = e.get("project", "?")
                lines.append(f"  [{proj}] {mission} — {_format_tokens(e['total_tokens'])}")
        lines.append("")

    # Per-project summary
    if len(by_project) > 1 or not today_entries:
        lines.append("By project:")
        for proj in sorted(by_project):
            lines.append(f"  {proj}: {_format_tokens(by_project[proj])}")
        lines.append("")

    # Grand total
    lines.append(f"Total: {_format_tokens(total_tokens)} tokens ({len(entries)} runs)")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: cost_tracker.py record <claude_json> <instance_dir> <project> [mission]",
              file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "record":
        if len(sys.argv) < 5:
            print("Usage: cost_tracker.py record <claude_json> <instance_dir> <project> [mission]",
                  file=sys.stderr)
            sys.exit(1)
        claude_json = Path(sys.argv[2])
        instance_dir = Path(sys.argv[3])
        project = sys.argv[4]
        mission = sys.argv[5] if len(sys.argv) > 5 else ""
        record_mission_cost(claude_json, instance_dir, project, mission)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
