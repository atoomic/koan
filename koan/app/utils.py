#!/usr/bin/env python3
"""
Koan -- Shared utilities

Core shared helpers used across modules:
- load_dotenv: .env file loading
- load_config: config.yaml loading
- parse_project: [project:name] / [projet:name] tag extraction
- insert_pending_mission: append mission to missions.md pending section
- atomic_write: atomic file write (temp + rename)
- get_known_projects: project list from env vars
- append_to_outbox: locked outbox append

For config, journal, and telegram history, see the dedicated modules:
- app.config: tools, models, CLI flags, behavioral settings
- app.journal: journal file operations
- app.telegram_history: conversation history management
"""

import fcntl
import os
import re
import tempfile
import threading
import yaml
from pathlib import Path
from typing import Optional, Tuple, List


if "KOAN_ROOT" not in os.environ:
    raise SystemExit("KOAN_ROOT environment variable is not set. Run via 'make run' or 'make awake'.")
KOAN_ROOT = Path(os.environ["KOAN_ROOT"])

# Pre-compiled regex for project tag extraction (accepts both [project:X] and [projet:X])
_PROJECT_TAG_RE = re.compile(r'\[projec?t:([a-zA-Z0-9_-]+)\]')
_PROJECT_TAG_STRIP_RE = re.compile(r'\[projec?t:[a-zA-Z0-9_-]+\]\s*')

_MISSIONS_DEFAULT = "# Missions\n\n## Pending\n\n## In Progress\n\n## Done\n"
_MISSIONS_LOCK = threading.Lock()


def load_dotenv():
    """Load .env file from the project root, stripping quotes from values.

    Uses os.environ.setdefault so existing env vars are not overwritten.
    """
    env_path = KOAN_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_config() -> dict:
    """Load configuration from instance/config.yaml.

    Returns the full config dict, or empty dict if file doesn't exist.
    """
    config_path = KOAN_ROOT / "instance" / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as e:
        print(f"[utils] Error loading config: {e}")
        return {}


def parse_project(text: str) -> Tuple[Optional[str], str]:
    """Extract [project:name] or [projet:name] from text.

    Returns (project_name, cleaned_text) where cleaned_text has the tag removed.
    Returns (None, text) if no tag found.
    """
    match = _PROJECT_TAG_RE.search(text)
    if match:
        project = match.group(1)
        cleaned = _PROJECT_TAG_STRIP_RE.sub('', text).strip()
        return project, cleaned
    return None, text


def atomic_write(path: Path, content: str):
    """Write content to a file atomically using write-to-temp + rename.

    Prevents data loss if the process crashes mid-write. Uses an exclusive
    lock on the temp file to serialize concurrent writers.
    """
    dir_path = path.parent
    fd, tmp = tempfile.mkstemp(dir=str(dir_path), prefix=".koan-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_known_projects() -> List[str]:
    """Return list of known project names from KOAN_PROJECTS or KOAN_PROJECT_PATH.

    Parses the KOAN_PROJECTS env var (format: 'name:path;name2:path2').
    Falls back to KOAN_PROJECT_PATH with name 'default'.
    Returns empty list if neither is set.
    """
    projects_env = os.environ.get("KOAN_PROJECTS", "")
    if projects_env:
        names = []
        for pair in projects_env.split(";"):
            pair = pair.strip()
            if ":" in pair:
                name = pair.split(":")[0].strip()
                if name:
                    names.append(name)
        return sorted(names)

    project_path = os.environ.get("KOAN_PROJECT_PATH", "")
    if project_path:
        return ["default"]

    return []


def insert_pending_mission(missions_path: Path, entry: str):
    """Insert a mission entry into the pending section of missions.md.

    Uses file locking for the entire read-modify-write cycle to prevent
    TOCTOU race conditions between awake.py and dashboard.py.
    Creates the file with default structure if it doesn't exist.
    """
    # Thread lock (in-process) + file lock (cross-process) for full protection
    with _MISSIONS_LOCK:
        if not missions_path.exists():
            missions_path.write_text(_MISSIONS_DEFAULT)

        with open(missions_path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            content = f.read()
            if not content.strip():
                content = _MISSIONS_DEFAULT

            marker = None
            for candidate in ("## Pending", "## En attente"):
                if candidate in content:
                    marker = candidate
                    break

            if marker:
                idx = content.index(marker) + len(marker)
                while idx < len(content) and content[idx] == "\n":
                    idx += 1
                content = content[:idx] + f"\n{entry}\n" + content[idx:]
            else:
                content += f"\n## Pending\n\n{entry}\n"

            from app.missions import normalize_content
            content = normalize_content(content)

            f.seek(0)
            f.truncate()
            f.write(content)
            fcntl.flock(f, fcntl.LOCK_UN)


def append_to_outbox(outbox_path: Path, content: str):
    """Append content to outbox.md with file locking.

    Safe to call from run.sh via: python3 -c "from app.utils import append_to_outbox; ..."
    or from Python directly.
    """
    with open(outbox_path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(content)
        fcntl.flock(f, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Backward-compatible re-exports
# ---------------------------------------------------------------------------
# These functions were extracted to dedicated modules but are re-exported here
# so existing `from app.utils import X` statements continue to work.
# New code should import from the dedicated modules directly.

from app.config import (  # noqa: E402, F401
    get_chat_tools,
    get_mission_tools,
    get_allowed_tools,
    get_tools_description,
    get_model_config,
    get_start_on_pause,
    get_max_runs,
    get_interval_seconds,
    get_fast_reply_model,
    get_contemplative_chance,
    build_claude_flags,
    get_claude_flags_for_role,
    get_auto_merge_config,
)

from app.journal import (  # noqa: E402, F401
    get_journal_file,
    read_all_journals,
    get_latest_journal,
    append_to_journal,
)

from app.telegram_history import (  # noqa: E402, F401
    save_telegram_message,
    load_recent_telegram_history,
    format_conversation_history,
    compact_telegram_history,
)
