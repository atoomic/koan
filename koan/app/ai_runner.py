"""
Koan -- AI exploration runner.

Gathers project context and runs Claude to suggest creative improvements.
Extracted from the /ai skill handler so it can run as a queued mission
via run.sh instead of inlining the full prompt into missions.md.

CLI:
    python3 -m app.ai_runner --project-path <path> --project-name <name> \
        --instance-dir <dir>
"""

import subprocess
from pathlib import Path
from typing import Optional, Tuple


def run_exploration(
    project_path: str,
    project_name: str,
    instance_dir: str,
    notify_fn=None,
    skill_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Execute an AI exploration of a project.

    Gathers git activity, project structure, and missions context, then
    runs Claude to suggest creative improvements.

    Returns:
        (success, summary) tuple.
    """
    if notify_fn is None:
        from app.notify import send_telegram
        notify_fn = send_telegram

    notify_fn(f"Exploring {project_name}...")

    # Gather context
    git_activity = _gather_git_activity(project_path)
    project_structure = _gather_project_structure(project_path)
    missions_context = _get_missions_context(Path(instance_dir))

    # Build prompt from skill template
    if skill_dir is None:
        skill_dir = (
            Path(__file__).resolve().parent.parent / "skills" / "core" / "ai"
        )

    from app.prompts import load_skill_prompt

    prompt = load_skill_prompt(
        skill_dir,
        "ai-explore",
        PROJECT_NAME=project_name,
        GIT_ACTIVITY=git_activity,
        PROJECT_STRUCTURE=project_structure,
        MISSIONS_CONTEXT=missions_context,
    )

    # Run Claude
    try:
        result = _run_claude(prompt, project_path)
    except Exception as e:
        return False, f"Exploration failed: {str(e)[:300]}"

    if not result:
        return False, "Claude returned an empty exploration result."

    # Send result to Telegram (truncated)
    cleaned = _clean_response(result)
    notify_fn(f"AI exploration of {project_name}:\n\n{cleaned}")

    return True, f"Exploration of {project_name} completed."


def _run_claude(prompt: str, project_path: str) -> str:
    """Run Claude to generate exploration ideas."""
    from app.cli_provider import build_full_command
    from app.config import get_model_config

    models = get_model_config()
    cmd = build_full_command(
        prompt=prompt,
        allowed_tools=["Read", "Glob", "Grep", "Bash"],
        model=models.get("chat", ""),
        fallback=models.get("fallback", ""),
        max_turns=5,
    )

    result = subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=600,
        cwd=project_path,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Claude exploration failed: {result.stderr[:300]}"
        )

    return result.stdout.strip()


def _gather_git_activity(project_path: str) -> str:
    """Gather recent git activity for a project."""
    parts = []
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-15", "--no-merges"],
            capture_output=True, text=True, timeout=10,
            cwd=project_path,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts.append("Recent commits:\n" + result.stdout.strip())

        result = subprocess.run(
            ["git", "branch", "-r", "--sort=-committerdate",
             "--format=%(refname:short)"],
            capture_output=True, text=True, timeout=10,
            cwd=project_path,
        )
        if result.returncode == 0 and result.stdout.strip():
            branches = result.stdout.strip().split("\n")[:10]
            parts.append("Active branches:\n" + "\n".join(branches))

        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD~10", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=project_path,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts.append("Recent changes:\n" + result.stdout.strip())

    except (subprocess.TimeoutExpired, Exception) as e:
        parts.append(f"(git activity unavailable: {e})")

    return "\n\n".join(parts) if parts else "No git activity available."


def _gather_project_structure(project_path: str) -> str:
    """Gather top-level project structure."""
    try:
        p = Path(project_path)
        entries = sorted(p.iterdir())
        dirs = [
            e.name + "/"
            for e in entries
            if e.is_dir() and not e.name.startswith(".")
        ]
        files = [
            e.name
            for e in entries
            if e.is_file() and not e.name.startswith(".")
        ]
        parts = []
        if dirs:
            parts.append("Directories: " + ", ".join(dirs[:20]))
        if files:
            parts.append("Files: " + ", ".join(files[:20]))
        return "\n".join(parts)
    except Exception:
        return "Structure unavailable."


def _get_missions_context(instance_dir: Path) -> str:
    """Get current missions context for the prompt."""
    missions_file = instance_dir / "missions.md"
    if not missions_file.exists():
        return "No active missions."

    from app.missions import parse_sections

    sections = parse_sections(missions_file.read_text())
    in_progress = sections.get("in_progress", [])
    pending = sections.get("pending", [])
    parts = []
    if in_progress:
        parts.append("In progress:\n" + "\n".join(in_progress[:5]))
    if pending:
        parts.append("Pending:\n" + "\n".join(pending[:5]))
    return "\n".join(parts) if parts else "No active missions."


def _clean_response(text: str) -> str:
    """Clean Claude CLI output for Telegram delivery."""
    import re

    lines = text.splitlines()
    lines = [
        line for line in lines
        if not re.match(r'^Error:.*max turns', line, re.IGNORECASE)
    ]
    cleaned = "\n".join(lines).strip()
    cleaned = cleaned.replace("```", "")
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")
    cleaned = cleaned.replace("~~", "")
    cleaned = re.sub(r'^#{1,6}\s+', '', cleaned, flags=re.MULTILINE)
    if len(cleaned) > 2000:
        cleaned = cleaned[:1997] + "..."
    return cleaned.strip()


# ---------------------------------------------------------------------------
# CLI entry point -- python3 -m app.ai_runner
# ---------------------------------------------------------------------------

def main(argv=None):
    """CLI entry point for ai_runner.

    Returns exit code (0 = success, 1 = failure).
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Run AI exploration on a project and report findings."
    )
    parser.add_argument(
        "--project-path", required=True,
        help="Local path to the project repository",
    )
    parser.add_argument(
        "--project-name", required=True,
        help="Human-readable project name",
    )
    parser.add_argument(
        "--instance-dir", required=True,
        help="Path to the instance directory",
    )
    cli_args = parser.parse_args(argv)

    skill_dir = (
        Path(__file__).resolve().parent.parent / "skills" / "core" / "ai"
    )

    success, summary = run_exploration(
        project_path=cli_args.project_path,
        project_name=cli_args.project_name,
        instance_dir=cli_args.instance_dir,
        skill_dir=skill_dir,
    )
    print(summary)
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
