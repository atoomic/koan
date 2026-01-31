#!/usr/bin/env python3
"""
Kōan Telegram Bridge

Polls Telegram for incoming messages → appends to instance/missions.md
Polls instance/outbox.md for bot messages → sends to Telegram, then clears.
"""

import os
import sys
import time
import requests
from pathlib import Path

# Configuration — override via environment variables
BOT_TOKEN = os.environ.get("KOAN_TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("KOAN_TELEGRAM_CHAT_ID", "")
POLL_INTERVAL = int(os.environ.get("KOAN_BRIDGE_INTERVAL", "10"))

INSTANCE_DIR = Path(__file__).parent / "instance"
MISSIONS_FILE = INSTANCE_DIR / "missions.md"
OUTBOX_FILE = INSTANCE_DIR / "outbox.md"
USAGE_FILE = INSTANCE_DIR / "usage.md"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def check_config():
    if not BOT_TOKEN or not CHAT_ID:
        print("Error: Set KOAN_TELEGRAM_TOKEN and KOAN_TELEGRAM_CHAT_ID env vars.")
        sys.exit(1)
    if not INSTANCE_DIR.exists():
        print("Error: No instance/ directory. Run: cp -r instance.example instance")
        sys.exit(1)


def get_updates(offset=None):
    """Poll Telegram for new messages."""
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(f"{TELEGRAM_API}/getUpdates", params=params, timeout=35)
        return resp.json().get("result", [])
    except Exception as e:
        print(f"[bridge] Error polling Telegram: {e}")
        return []


def send_message(text):
    """Send a message to the configured Telegram chat."""
    try:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"[bridge] Error sending message: {e}")


def handle_message(text):
    """Route incoming Telegram message to the right file."""
    text = text.strip()

    # /usage paste → write to usage.md
    if "opus" in text.lower() or "sonnet" in text.lower() or "usage" in text.lower():
        USAGE_FILE.write_text(f"# Usage\n\n```\n{text}\n```\n")
        send_message("Usage updated.")
        return

    # /status command
    if text.lower() == "/status":
        missions = MISSIONS_FILE.read_text() if MISSIONS_FILE.exists() else "No missions file."
        send_message(f"Current missions:\n\n{missions}")
        return

    # /stop command
    if text.lower() == "/stop":
        Path("/tmp/koan-stop").write_text("STOP")
        send_message("Stop signal sent. Kōan will finish current mission then halt.")
        return

    # Default: add as new mission
    missions = MISSIONS_FILE.read_text() if MISSIONS_FILE.exists() else "# Missions\n\n## Pending\n\n## In Progress\n\n## Done\n"
    missions = missions.replace("## Pending\n", f"## Pending\n- [ ] {text}\n", 1)
    MISSIONS_FILE.write_text(missions)
    send_message(f"Mission added: {text}")


def check_outbox():
    """Send any pending outbox messages to Telegram."""
    if not OUTBOX_FILE.exists():
        return
    content = OUTBOX_FILE.read_text().strip()
    lines = [l for l in content.split("\n") if l.strip() and not l.startswith("# Outbox")]
    if lines:
        send_message("\n".join(lines))
        OUTBOX_FILE.write_text("# Outbox\n\nMessages here will be sent to Telegram by bridge.py, then cleared.\n")


def main():
    check_config()
    print(f"[bridge] Running. Polling every {POLL_INTERVAL}s.")
    offset = None

    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if chat_id == CHAT_ID and text:
                print(f"[bridge] Received: {text[:50]}...")
                handle_message(text)

        check_outbox()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
