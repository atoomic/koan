#!/usr/bin/env python3
"""
Kōan — Messaging notification helper

Standalone module to send messages via the configured messaging provider
(Telegram, Slack, etc.) from any process (awake.py, run.sh, workers).

Usage from shell:
    python3 notify.py "Mission completed: security audit"

Usage from Python:
    from app.notify import send_message
    send_message("Mission completed: security audit")
"""

import os
import subprocess
import sys
from pathlib import Path

from app.utils import load_dotenv


def send_message(text: str) -> bool:
    """Send a message via the configured messaging provider. Returns True on success."""
    from app.messaging_provider import get_messaging_provider
    return get_messaging_provider().send_message(text)


# Backward-compatible alias — all existing call sites use send_telegram()
send_telegram = send_message


def format_and_send(raw_message: str, instance_dir: str = None,
                     project_name: str = "") -> bool:
    """Format a message through Claude with Kōan's personality, then send.

    Every message sent should go through this function to ensure
    consistent personality and readability on mobile.

    Args:
        raw_message: The raw/technical message to format
        instance_dir: Path to instance directory (auto-detected from KOAN_ROOT if None)
        project_name: Optional project name for scoped memory context

    Returns:
        True if message was sent successfully
    """
    from app.format_outbox import (
        format_for_telegram, load_soul, load_human_prefs,
        load_memory_context, fallback_format
    )

    if not instance_dir:
        load_dotenv()
        koan_root = os.environ.get("KOAN_ROOT", "")
        if koan_root:
            instance_dir = str(Path(koan_root) / "instance")
        else:
            # Can't format without instance dir — send raw with basic cleanup
            return send_message(fallback_format(raw_message))

    instance_path = Path(instance_dir)
    try:
        soul = load_soul(instance_path)
        prefs = load_human_prefs(instance_path)
        memory = load_memory_context(instance_path, project_name)
        formatted = format_for_telegram(raw_message, soul, prefs, memory)
        return send_message(formatted)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"[notify] Format error, sending fallback: {e}", file=sys.stderr)
        return send_message(fallback_format(raw_message))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [--format] <message>", file=sys.stderr)
        print(f"  --format: Format through Claude before sending", file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]
    use_format = False
    if args[0] == "--format":
        use_format = True
        args = args[1:]

    if not args:
        print(f"Usage: {sys.argv[0]} [--format] <message>", file=sys.stderr)
        sys.exit(1)

    message = " ".join(args)

    if use_format:
        project_name = os.environ.get("KOAN_CURRENT_PROJECT", "")
        success = format_and_send(message, project_name=project_name)
    else:
        success = send_message(message)
    sys.exit(0 if success else 1)
