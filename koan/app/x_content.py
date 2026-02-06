#!/usr/bin/env python3
"""
Koan -- X (Twitter) content screening

Screens tweet content before posting to prevent:
- Project name leaks
- Code snippets
- File paths
- Credentials / tokens
- Technical identifiers

Two layers:
1. Pattern-based blocklist (fast, no API call)
2. Optional Claude-based review (slower, more nuanced)

This module does NOT generate content — it only validates it.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

from app.utils import load_config


# Common slash patterns that are NOT repo references
_COMMON_SLASH = frozenset({"ai/ml", "and/or", "he/she", "w/o", "i/o", "yes/no", "input/output", "do/while"})

# Pre-compiled repo reference pattern
_REPO_RE = re.compile(r"\b([a-z][\w-]*/[a-z][\w-]*(?:#\d+)?)\b", re.IGNORECASE)

# Patterns that should NEVER appear in a tweet
_BLOCKED_PATTERNS = [
    # Credentials and tokens
    (re.compile(r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"), "JWT-like token"),
    (re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}"), "GitHub token"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "API key (sk-)"),
    (re.compile(r"xoxb-[A-Za-z0-9-]{20,}"), "Slack token"),
    (re.compile(r"AKIA[A-Z0-9]{16}"), "AWS access key"),
    (re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"), "Base64 encoded data"),

    # File paths (absolute)
    (re.compile(r"/(?:Users|home|var|etc|opt)/\S+"), "File path"),
    (re.compile(r"[A-Z]:\\(?:Users|Program Files)\\\S+"), "Windows path"),

    # Code blocks
    (re.compile(r"```[\s\S]*```"), "Code block"),
    (re.compile(r"def \w+\(.*\):"), "Python function definition"),
    (re.compile(r"class \w+[\(:]"), "Class definition"),
    (re.compile(r"import \w+"), "Import statement"),
    (re.compile(r"from \w+ import"), "From-import statement"),

    # Environment variables with values
    (re.compile(r"[A-Z_]{3,}=\S+"), "Environment variable assignment"),

    # URLs with internal hostnames
    (re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)\S*"), "Local URL"),
    (re.compile(r"https?://\d+\.\d+\.\d+\.\d+\S*"), "IP-based URL"),
]

# Project names that must not appear (loaded from config)
_project_names_cache = None


def _get_project_names() -> List[str]:
    """Get known project names to screen against."""
    global _project_names_cache
    if _project_names_cache is not None:
        return _project_names_cache

    names = []
    # From KOAN_PROJECTS env var
    projects_str = os.environ.get("KOAN_PROJECTS", "")
    if projects_str:
        for entry in projects_str.split(";"):
            entry = entry.strip()
            if ":" in entry:
                name = entry.split(":")[0].strip()
                if name:
                    names.append(name)

    # From projects.yaml if available
    try:
        projects_yaml = Path(os.environ.get("KOAN_ROOT", ".")) / "projects.yaml"
        if projects_yaml.exists():
            import yaml
            data = yaml.safe_load(projects_yaml.read_text())
            if isinstance(data, dict) and "projects" in data:
                for proj in data["projects"]:
                    if isinstance(proj, dict) and "name" in proj:
                        names.append(proj["name"])
    except Exception:
        pass

    # Always screen for "koan" itself
    names.append("koan")
    _project_names_cache = list(set(names))
    return _project_names_cache


def screen_content(text: str) -> Tuple[bool, str]:
    """Screen tweet content for sensitive data.

    Returns:
        (allowed, reason) — reason explains rejection if not allowed.
    """
    if not text or not text.strip():
        return False, "Empty content"

    # Length check (X limit is 280 chars)
    if len(text) > 280:
        return False, f"Too long ({len(text)} chars, max 280)"

    # Pattern checks
    for pattern, description in _BLOCKED_PATTERNS:
        if pattern.search(text):
            return False, f"Blocked: {description} detected"

    # Project name checks (case-insensitive)
    project_names = _get_project_names()
    text_lower = text.lower()
    for name in project_names:
        if name.lower() in text_lower:
            return False, f"Blocked: project name '{name}' detected"

    # Check for repo-like references (pre-compiled patterns)
    for match in _REPO_RE.findall(text):
        if match.lower() not in _COMMON_SLASH:
            return False, f"Blocked: possible repo reference '{match}'"

    return True, "OK"


def sanitize_for_tweet(text: str) -> str:
    """Clean up text for tweet format.

    - Strip markdown formatting
    - Collapse whitespace
    - Ensure within character limit

    Does NOT screen for content safety — use screen_content() first.
    """
    # Remove markdown bold/italic
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)

    # Remove markdown headers
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)

    # Remove markdown links, keep text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Collapse multiple whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate if needed
    if len(text) > 280:
        text = text[:277] + "..."

    return text


def reset_project_cache():
    """Reset project names cache. For testing."""
    global _project_names_cache
    _project_names_cache = None
