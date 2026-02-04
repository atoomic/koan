#!/usr/bin/env python3
"""
Kōan — Error context extraction for mission failures

Extracts meaningful error context from Claude CLI stderr/stdout
when a mission fails (non-zero exit code). Returns a concise summary
suitable for Telegram notifications.

Usage from shell:
    python3 error_context.py <stderr_file> [stdout_file]

Usage from Python:
    from app.error_context import extract_error_summary
    summary = extract_error_summary(stderr_text, stdout_text)
"""

import json
import re
import sys


# Lines matching these patterns are noise — skip them
NOISE_PATTERNS = [
    re.compile(r"^\s*$"),                          # blank lines
    re.compile(r"^╭|^│|^╰|^┌|^└|^├"),             # box-drawing chars (TUI)
    re.compile(r"^\s*\d+%"),                       # progress bars
    re.compile(r"^Compiling|^Bundling|^Building"),  # build noise
    re.compile(r"^\[koan\]"),                       # our own wrapper logs
    re.compile(r"^npm warn"),                       # npm warnings
    re.compile(r"^\s*at\s+"),                       # JS stack trace internals
    re.compile(r"^#"),                              # comments / markdown headers
]

# Patterns that indicate the actual error cause
ERROR_SIGNAL_PATTERNS = [
    re.compile(r"error", re.IGNORECASE),
    re.compile(r"failed", re.IGNORECASE),
    re.compile(r"exception", re.IGNORECASE),
    re.compile(r"traceback", re.IGNORECASE),
    re.compile(r"permission denied", re.IGNORECASE),
    re.compile(r"not found", re.IGNORECASE),
    re.compile(r"timeout", re.IGNORECASE),
    re.compile(r"quota", re.IGNORECASE),
    re.compile(r"rate limit", re.IGNORECASE),
    re.compile(r"SIGTERM|SIGKILL|killed", re.IGNORECASE),
    re.compile(r"out of memory|OOM", re.IGNORECASE),
    re.compile(r"unauthorized|forbidden|401|403", re.IGNORECASE),
]


def _is_noise(line: str) -> bool:
    """Check if a line is noise that should be filtered."""
    return any(p.search(line) for p in NOISE_PATTERNS)


def _is_error_signal(line: str) -> bool:
    """Check if a line contains an error signal."""
    return any(p.search(line) for p in ERROR_SIGNAL_PATTERNS)


def _extract_from_json(stdout_text: str) -> str:
    """Try to extract error info from Claude CLI JSON output."""
    if not stdout_text or not stdout_text.strip():
        return ""
    try:
        data = json.loads(stdout_text.strip())
        # Claude CLI JSON output may have an error field
        if isinstance(data, dict):
            for key in ("error", "message", "detail", "reason"):
                if key in data and data[key]:
                    return str(data[key])[:200]
    except (json.JSONDecodeError, ValueError):
        pass
    return ""


def extract_error_summary(stderr_text: str, stdout_text: str = "",
                          max_lines: int = 5) -> str:
    """Extract a concise error summary from Claude CLI output.

    Prioritizes stderr, falls back to stdout. Filters noise lines,
    highlights error signals, and returns the most relevant lines.

    Args:
        stderr_text: Content of stderr capture
        stdout_text: Content of stdout capture (JSON or plain text)
        max_lines: Maximum lines to include in summary

    Returns:
        A concise error summary string, or empty string if no useful info found
    """
    # Try JSON error extraction first
    json_error = _extract_from_json(stdout_text)
    if json_error:
        return json_error

    # Combine stderr (primary) and last lines of stdout (secondary)
    lines = []
    if stderr_text:
        lines.extend(stderr_text.strip().splitlines())
    if stdout_text and not lines:
        # Only use stdout if stderr is empty
        lines.extend(stdout_text.strip().splitlines()[-20:])

    if not lines:
        return ""

    # Filter noise
    meaningful = [line.strip() for line in lines if not _is_noise(line)]
    if not meaningful:
        # If everything was filtered, take last raw lines
        meaningful = [line.strip() for line in lines if line.strip()][-max_lines:]

    # Find error signal lines (most informative)
    error_lines = [line for line in meaningful if _is_error_signal(line)]

    if error_lines:
        # Take last N error lines (usually the most specific)
        selected = error_lines[-max_lines:]
    else:
        # No explicit error signals — take last N meaningful lines
        selected = meaningful[-max_lines:]

    # Truncate individual lines
    selected = [line[:200] for line in selected]

    return "\n".join(selected)


def format_failure_notification(mission_title: str, project_name: str,
                                run_num: int, max_runs: int,
                                error_summary: str) -> str:
    """Format a failure notification message with error context.

    Args:
        mission_title: The mission that failed (empty for autonomous)
        project_name: Project name
        run_num: Current run number
        max_runs: Maximum runs
        error_summary: Output from extract_error_summary()

    Returns:
        Formatted notification string ready for Telegram
    """
    parts = [f"Run {run_num}/{max_runs} — [{project_name}]"]

    if mission_title:
        parts.append(f"Mission failed: {mission_title}")
    else:
        parts.append("Run failed")

    if error_summary:
        # Take first 2 lines of error summary for the notification
        summary_lines = error_summary.strip().splitlines()[:2]
        reason = " | ".join(summary_lines)
        # Cap total length for Telegram readability
        if len(reason) > 300:
            reason = reason[:297] + "..."
        parts.append(f"Reason: {reason}")

    return "\n".join(parts)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <stderr_file> [stdout_file]",
              file=sys.stderr)
        sys.exit(1)

    stderr_file = sys.argv[1]
    stdout_file = sys.argv[2] if len(sys.argv) > 2 else ""

    stderr_text = ""
    stdout_text = ""
    try:
        with open(stderr_file) as f:
            stderr_text = f.read()
    except OSError:
        pass

    if stdout_file:
        try:
            with open(stdout_file) as f:
                stdout_text = f.read()
        except OSError:
            pass

    summary = extract_error_summary(stderr_text, stdout_text)
    if summary:
        print(summary)
    else:
        print("No error context available")
