#!/usr/bin/env python3
"""
Koan -- X (Twitter) posting

Core module for posting tweets from Koan's account.

Features:
- Rate limiting (max_per_day, rolling 24h window)
- Duplicate detection (content hash)
- Pending queue with human approval (x-pending.md)
- Audit logging (x-posted.log)
- Circuit breaker (auto-disable on consecutive failures)
- Content screening (delegates to x_content.py)

Security:
- All posts screened before sending
- Default: require_approval = true (human reviews via /x approve)
- Single account only (Koan's dedicated X account)
- Audit trail of everything posted

Config (config.yaml):
    x:
      enabled: false
      max_per_day: 3
      require_approval: true
      allowed_triggers:
        - koan
        - learning
        - reflection
        - milestone

Env vars (.env):
    KOAN_X_CLIENT_ID, KOAN_X_CLIENT_SECRET, KOAN_X_REFRESH_TOKEN

Usage from Python:
    from app.x_post import queue_tweet, post_approved_tweet
    queue_tweet("koan", "If the test passes but nothing changes, was it really a test?")

Usage from shell:
    python3 -m app.x_post queue "koan" "The zen text here"
    python3 -m app.x_post approve
    python3 -m app.x_post status
"""

import fcntl
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from app.utils import load_config, load_dotenv
from app.x_auth import get_auth_header, is_configured
from app.x_content import screen_content, sanitize_for_tweet

# X API v2 endpoints
TWEET_URL = "https://api.twitter.com/2/tweets"
DELETE_TWEET_URL = "https://api.twitter.com/2/tweets/{tweet_id}"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _get_x_config() -> dict:
    """Get X posting config from config.yaml with defaults."""
    config = load_config()
    defaults = {
        "enabled": False,
        "max_per_day": 3,
        "require_approval": True,
        "allowed_triggers": ["koan", "learning", "reflection", "milestone"],
        "content_screening": True,
        "audit_log": True,
    }
    x_cfg = config.get("x", {})
    return {k: x_cfg.get(k, v) for k, v in defaults.items()}


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _instance_dir() -> Path:
    koan_root = Path(os.environ.get("KOAN_ROOT", "."))
    return koan_root / "instance"


def _cooldown_path() -> Path:
    return _instance_dir() / ".x-cooldown.json"


def _pending_path() -> Path:
    return _instance_dir() / "x-pending.jsonl"


def _posted_log_path() -> Path:
    return _instance_dir() / "x-posted.log"


def _circuit_breaker_path() -> Path:
    return _instance_dir() / ".x-circuit-breaker.json"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _load_cooldown() -> list:
    """Load posting cooldown records."""
    path = _cooldown_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_cooldown(records: list):
    path = _cooldown_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2))


def _prune_old_records(records: list) -> list:
    """Remove records older than 24 hours."""
    cutoff = time.time() - 86400
    return [r for r in records if r.get("timestamp", 0) > cutoff]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

def _load_circuit_breaker() -> dict:
    path = _circuit_breaker_path()
    if not path.exists():
        return {"failures": 0, "disabled_until": 0}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"failures": 0, "disabled_until": 0}


def _save_circuit_breaker(state: dict):
    path = _circuit_breaker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def _trip_circuit_breaker():
    """Record a failure and potentially disable posting."""
    state = _load_circuit_breaker()
    state["failures"] = state.get("failures", 0) + 1
    if state["failures"] >= 2:
        # Disable for 24 hours
        state["disabled_until"] = time.time() + 86400
        print("[x] Circuit breaker tripped — posting disabled for 24h", file=sys.stderr)
    _save_circuit_breaker(state)


def _reset_circuit_breaker():
    """Reset circuit breaker after a successful post."""
    _save_circuit_breaker({"failures": 0, "disabled_until": 0})


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

def can_post() -> Tuple[bool, str]:
    """Check if posting is allowed right now.

    Returns:
        (allowed, reason)
    """
    config = _get_x_config()

    if not config["enabled"]:
        return False, "X posting not enabled in config.yaml"

    ok, msg = is_configured()
    if not ok:
        return False, msg

    # Circuit breaker
    cb = _load_circuit_breaker()
    if cb.get("disabled_until", 0) > time.time():
        remaining = int((cb["disabled_until"] - time.time()) / 3600)
        return False, f"Circuit breaker active (~{remaining}h remaining)"

    # Rate limit
    records = _prune_old_records(_load_cooldown())
    max_per_day = config["max_per_day"]
    if len(records) >= max_per_day:
        return False, f"Rate limit reached ({max_per_day} posts per 24h)"

    return True, "OK"


def is_duplicate(text: str) -> bool:
    """Check if this text was already posted in the last 24 hours."""
    records = _prune_old_records(_load_cooldown())
    h = _content_hash(text)
    return any(r.get("content_hash") == h for r in records)


# ---------------------------------------------------------------------------
# Pending queue (x-pending.md)
# ---------------------------------------------------------------------------

def _load_pending() -> List[dict]:
    """Load pending tweets from x-pending.jsonl (one JSON object per line)."""
    path = _pending_path()
    if not path.exists():
        return []

    entries = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        return []
    return entries


def _save_pending(entries: List[dict]):
    """Save pending tweets to x-pending.jsonl atomically."""
    path = _pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    content = "\n".join(json.dumps(e) for e in entries) + "\n" if entries else ""

    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent))
    try:
        os.write(tmp_fd, content.encode())
        os.close(tmp_fd)
        os.rename(tmp_path, str(path))
    except OSError:
        try:
            os.close(tmp_fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_pending_count() -> int:
    """Return number of pending tweets."""
    return len(_load_pending())


def get_next_pending() -> Optional[dict]:
    """Return the next pending tweet (FIFO), or None."""
    entries = _load_pending()
    return entries[0] if entries else None


def _remove_first_pending():
    """Remove the first pending tweet from the queue."""
    entries = _load_pending()
    if entries:
        _save_pending(entries[1:])


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def _audit_log(tweet_id: str, text: str, trigger: str):
    """Append to x-posted.log."""
    config = _get_x_config()
    if not config["audit_log"]:
        return

    path = _posted_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "tweet_id": tweet_id,
        "trigger": trigger,
        "content_hash": _content_hash(text),
        "text": text[:100],
    }

    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(entry) + "\n")
        fcntl.flock(f, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Core posting
# ---------------------------------------------------------------------------

def _post_to_x(text: str) -> Tuple[bool, str]:
    """Post a tweet to X API v2.

    Returns:
        (success, tweet_id_or_error)
    """
    ok, auth_result = get_auth_header()
    if not ok:
        return False, f"Auth failed: {auth_result}"

    headers = auth_result
    headers["Content-Type"] = "application/json"

    payload = json.dumps({"text": text}).encode()
    req = urllib.request.Request(TWEET_URL, data=payload, method="POST", headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
        tweet_id = result.get("data", {}).get("id", "")
        if tweet_id:
            return True, tweet_id
        return False, f"No tweet ID in response: {json.dumps(result)[:200]}"

    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return False, f"X API error (HTTP {e.code}): {body[:200]}"
    except (urllib.error.URLError, OSError) as e:
        return False, f"X API connection error: {e}"


def queue_tweet(trigger: str, text: str) -> Tuple[str, str]:
    """Queue a tweet for posting (with optional approval).

    Returns:
        (status, message) where status is "queued", "posted", "rejected", or "error"
    """
    config = _get_x_config()

    if not config["enabled"]:
        return "error", "X posting not enabled in config.yaml"

    # Check trigger is allowed
    if trigger not in config["allowed_triggers"]:
        return "rejected", f"Trigger '{trigger}' not in allowed_triggers"

    # Sanitize
    text = sanitize_for_tweet(text)

    # Screen content
    if config["content_screening"]:
        allowed, reason = screen_content(text)
        if not allowed:
            print(f"[x] Content blocked: {reason}", file=sys.stderr)
            return "rejected", f"Content screening failed: {reason}"

    # Duplicate check
    if is_duplicate(text):
        return "rejected", "Duplicate content (already posted in last 24h)"

    # If require_approval, queue for human review
    if config["require_approval"]:
        entries = _load_pending()
        entries.append({
            "trigger": trigger,
            "queued_at": datetime.now(tz=timezone.utc).isoformat(),
            "text": text,
        })
        _save_pending(entries)
        return "queued", f"Queued for approval ({len(entries)} pending)"

    # Auto-post
    return _do_post(text, trigger)


def _do_post(text: str, trigger: str) -> Tuple[str, str]:
    """Actually post a tweet (after all checks passed).

    Returns:
        (status, message)
    """
    allowed, reason = can_post()
    if not allowed:
        return "error", reason

    ok, result = _post_to_x(text)
    if ok:
        tweet_id = result
        # Record in cooldown
        records = _prune_old_records(_load_cooldown())
        records.append({
            "timestamp": time.time(),
            "content_hash": _content_hash(text),
            "tweet_id": tweet_id,
        })
        _save_cooldown(records)

        # Audit log
        _audit_log(tweet_id, text, trigger)

        # Reset circuit breaker on success
        _reset_circuit_breaker()

        print(f"[x] Posted tweet {tweet_id}: {text[:60]}...", file=sys.stderr)
        return "posted", tweet_id
    else:
        _trip_circuit_breaker()
        print(f"[x] Failed to post: {result}", file=sys.stderr)
        return "error", result


def post_approved_tweet() -> Tuple[str, str]:
    """Post the next pending tweet (called by /x approve).

    Returns:
        (status, message) — "posted", "error", or "empty"
    """
    pending = get_next_pending()
    if not pending:
        return "empty", "No pending tweets"

    text = pending["text"]
    trigger = pending.get("trigger", "unknown")

    # Re-screen before posting (content rules may have changed)
    config = _get_x_config()
    if config["content_screening"]:
        allowed, reason = screen_content(text)
        if not allowed:
            _remove_first_pending()
            return "rejected", f"Content no longer passes screening: {reason}"

    status, msg = _do_post(text, trigger)
    if status == "posted":
        _remove_first_pending()
    return status, msg


def reject_pending_tweet(reason: str = "") -> Tuple[str, str]:
    """Reject the next pending tweet.

    Returns:
        (status, message) — "rejected" or "empty"
    """
    pending = get_next_pending()
    if not pending:
        return "empty", "No pending tweets"

    _remove_first_pending()
    log_msg = f"Rejected: {pending['text'][:60]}"
    if reason:
        log_msg += f" — reason: {reason}"
    print(f"[x] {log_msg}", file=sys.stderr)
    return "rejected", log_msg


def delete_tweet(tweet_id: str) -> Tuple[bool, str]:
    """Delete a posted tweet by ID.

    Returns:
        (success, message)
    """
    ok, auth_result = get_auth_header()
    if not ok:
        return False, f"Auth failed: {auth_result}"

    url = DELETE_TWEET_URL.format(tweet_id=tweet_id)
    headers = auth_result
    req = urllib.request.Request(url, method="DELETE", headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
        if result.get("data", {}).get("deleted"):
            return True, f"Tweet {tweet_id} deleted"
        return False, f"Unexpected response: {json.dumps(result)[:200]}"

    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return False, f"Delete failed (HTTP {e.code}): {body[:200]}"
    except (urllib.error.URLError, OSError) as e:
        return False, f"Delete connection error: {e}"


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_x_stats() -> dict:
    """Return X posting statistics."""
    config = _get_x_config()
    records = _prune_old_records(_load_cooldown())
    max_per_day = config["max_per_day"]
    last_posted = max((r.get("timestamp", 0) for r in records), default=None) if records else None

    cb = _load_circuit_breaker()
    cb_active = cb.get("disabled_until", 0) > time.time()

    return {
        "enabled": config["enabled"],
        "posted_24h": len(records),
        "remaining": max(0, max_per_day - len(records)),
        "max_per_day": max_per_day,
        "last_posted": last_posted,
        "pending": get_pending_count(),
        "require_approval": config["require_approval"],
        "circuit_breaker_active": cb_active,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  x_post.py queue <trigger> <text>", file=sys.stderr)
        print("  x_post.py approve", file=sys.stderr)
        print("  x_post.py reject [reason]", file=sys.stderr)
        print("  x_post.py status", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]

    if action == "queue" and len(sys.argv) >= 4:
        trigger = sys.argv[2]
        text = sys.argv[3]
        status, msg = queue_tweet(trigger, text)
        print(f"{status}: {msg}")
        sys.exit(0 if status in ("queued", "posted") else 1)

    elif action == "approve":
        status, msg = post_approved_tweet()
        print(f"{status}: {msg}")
        sys.exit(0 if status == "posted" else 1)

    elif action == "reject":
        reason = sys.argv[2] if len(sys.argv) > 2 else ""
        status, msg = reject_pending_tweet(reason)
        print(f"{status}: {msg}")
        sys.exit(0)

    elif action == "status":
        stats = get_x_stats()
        print(json.dumps(stats, indent=2))
        sys.exit(0)

    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)
