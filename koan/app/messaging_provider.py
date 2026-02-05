"""
Messaging provider abstraction for Kōan.

Allows switching between Telegram and Slack (or future backends)
as the messaging transport. Each provider implements:
- send_message(): deliver a message to the configured channel
- get_updates(): poll for incoming messages (bridge mode)
- check_config(): validate credentials are set

Configuration:
    config.yaml:  messaging_provider: "telegram"   (default)
    env var:      KOAN_MESSAGING_PROVIDER=slack     (overrides config.yaml)

Environment variables per provider:
    Telegram: KOAN_TELEGRAM_TOKEN, KOAN_TELEGRAM_CHAT_ID
    Slack:    KOAN_SLACK_BOT_TOKEN, KOAN_SLACK_CHANNEL_ID, KOAN_SLACK_APP_TOKEN
"""

import os
import sys
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

import requests


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class MessagingProvider(ABC):
    """Abstract messaging backend."""

    @abstractmethod
    def send_message(self, text: str) -> bool:
        """Send a message to the configured channel.

        Handles chunking for providers with message size limits.

        Returns:
            True if all chunks sent successfully.
        """

    @abstractmethod
    def get_updates(self, offset: Optional[str] = None) -> List[Dict]:
        """Poll for new messages.

        Args:
            offset: Provider-specific cursor/offset for pagination.

        Returns:
            List of message dicts with keys:
                - text: message content
                - chat_id: sender/channel identifier
                - update_id: provider-specific ID for offset tracking
        """

    @abstractmethod
    def check_config(self) -> None:
        """Validate that required credentials are set.

        Raises:
            SystemExit if configuration is missing.
        """

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider name (for logging and display)."""

    @abstractmethod
    def get_chat_id(self) -> str:
        """Return the configured channel/chat ID."""

    @property
    def max_message_length(self) -> int:
        """Maximum message length before chunking."""
        return 4000


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

class TelegramProvider(MessagingProvider):
    """Telegram Bot API messaging provider."""

    def __init__(self):
        self.bot_token = os.environ.get("KOAN_TELEGRAM_TOKEN", "")
        self.chat_id = os.environ.get("KOAN_TELEGRAM_CHAT_ID", "")
        self._api_base = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(self, text: str) -> bool:
        if not self.bot_token or not self.chat_id:
            print("[messaging] KOAN_TELEGRAM_TOKEN or KOAN_TELEGRAM_CHAT_ID not set.",
                  file=sys.stderr)
            return False

        ok = True
        for chunk in [text[i:i + 4000] for i in range(0, len(text), 4000)]:
            try:
                resp = requests.post(
                    f"{self._api_base}/sendMessage",
                    json={"chat_id": self.chat_id, "text": chunk},
                    timeout=10,
                )
                data = resp.json()
                if not data.get("ok"):
                    print(f"[messaging] Telegram API error: {resp.text[:200]}",
                          file=sys.stderr)
                    ok = False
            except (requests.RequestException, ValueError) as e:
                print(f"[messaging] Telegram send error: {e}", file=sys.stderr)
                ok = False
        return ok

    def get_updates(self, offset=None):
        params = {"timeout": 30}
        if offset:
            params["offset"] = offset
        try:
            resp = requests.get(
                f"{self._api_base}/getUpdates",
                params=params,
                timeout=35,
            )
            data = resp.json()
            results = data.get("result", [])
            # Normalize to common format
            normalized = []
            for update in results:
                msg = update.get("message", {})
                normalized.append({
                    "text": msg.get("text", ""),
                    "chat_id": str(msg.get("chat", {}).get("id", "")),
                    "update_id": update["update_id"],
                })
            return normalized
        except (requests.RequestException, ValueError) as e:
            print(f"[messaging] Telegram poll error: {e}")
            return []

    def check_config(self):
        if not self.bot_token or not self.chat_id:
            print("Error: Set KOAN_TELEGRAM_TOKEN and KOAN_TELEGRAM_CHAT_ID env vars.")
            sys.exit(1)

    def get_provider_name(self) -> str:
        return "telegram"

    def get_chat_id(self) -> str:
        return self.chat_id

    @property
    def max_message_length(self) -> int:
        return 4000


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------

class SlackProvider(MessagingProvider):
    """Slack Web API messaging provider.

    Requires:
        KOAN_SLACK_BOT_TOKEN: Bot User OAuth Token (xoxb-...)
        KOAN_SLACK_CHANNEL_ID: Channel ID (C...)
        KOAN_SLACK_APP_TOKEN: App-Level Token (xapp-...) for Socket Mode polling

    The bot needs scopes: chat:write, channels:history, channels:read
    For Socket Mode: connections:write on the app token
    """

    def __init__(self):
        self.bot_token = os.environ.get("KOAN_SLACK_BOT_TOKEN", "")
        self.channel_id = os.environ.get("KOAN_SLACK_CHANNEL_ID", "")
        self.app_token = os.environ.get("KOAN_SLACK_APP_TOKEN", "")
        self._api_base = "https://slack.com/api"
        self._last_ts: Optional[str] = None  # Timestamp cursor for polling

    def send_message(self, text: str) -> bool:
        if not self.bot_token or not self.channel_id:
            print("[messaging] KOAN_SLACK_BOT_TOKEN or KOAN_SLACK_CHANNEL_ID not set.",
                  file=sys.stderr)
            return False

        ok = True
        # Slack limit is 4000 chars per message (mrkdwn blocks can be longer
        # but plain text messages are capped)
        for chunk in [text[i:i + 3900] for i in range(0, len(text), 3900)]:
            try:
                resp = requests.post(
                    f"{self._api_base}/chat.postMessage",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    json={
                        "channel": self.channel_id,
                        "text": chunk,
                    },
                    timeout=10,
                )
                data = resp.json()
                if not data.get("ok"):
                    print(f"[messaging] Slack API error: {data.get('error', 'unknown')}",
                          file=sys.stderr)
                    ok = False
            except (requests.RequestException, ValueError) as e:
                print(f"[messaging] Slack send error: {e}", file=sys.stderr)
                ok = False
        return ok

    def get_updates(self, offset=None):
        """Poll Slack channel history for new messages.

        Uses conversations.history API with oldest= parameter for pagination.
        This is a simple polling approach. For production use, Socket Mode
        or Events API would be more efficient.
        """
        if not self.bot_token or not self.channel_id:
            return []

        params = {
            "channel": self.channel_id,
            "limit": 10,
        }
        # Use offset (timestamp) to only get newer messages
        if offset:
            params["oldest"] = offset
        elif self._last_ts:
            params["oldest"] = self._last_ts

        try:
            resp = requests.get(
                f"{self._api_base}/conversations.history",
                headers={"Authorization": f"Bearer {self.bot_token}"},
                params=params,
                timeout=10,
            )
            data = resp.json()
            if not data.get("ok"):
                print(f"[messaging] Slack history error: {data.get('error', 'unknown')}")
                return []

            messages = data.get("messages", [])
            # Filter out bot messages (don't process our own messages)
            normalized = []
            for msg in reversed(messages):  # oldest first
                if msg.get("bot_id") or msg.get("subtype"):
                    continue
                ts = msg.get("ts", "")
                normalized.append({
                    "text": msg.get("text", ""),
                    "chat_id": self.channel_id,
                    "update_id": ts,
                })
                self._last_ts = ts

            return normalized
        except (requests.RequestException, ValueError) as e:
            print(f"[messaging] Slack poll error: {e}")
            return []

    def check_config(self):
        if not self.bot_token or not self.channel_id:
            print("Error: Set KOAN_SLACK_BOT_TOKEN and KOAN_SLACK_CHANNEL_ID env vars.")
            sys.exit(1)

    def get_provider_name(self) -> str:
        return "slack"

    def get_chat_id(self) -> str:
        return self.channel_id

    @property
    def max_message_length(self) -> int:
        return 3900


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _get_messaging_provider_name() -> str:
    """Read provider name from env or config.yaml."""
    # Env var overrides config
    env_provider = os.environ.get("KOAN_MESSAGING_PROVIDER", "")
    if env_provider:
        return env_provider.lower().strip()

    # Fall back to config.yaml
    try:
        from app.utils import load_config
        config = load_config()
        return config.get("messaging_provider", "telegram").lower().strip()
    except Exception:
        return "telegram"


_PROVIDERS = {
    "telegram": TelegramProvider,
    "slack": SlackProvider,
}

# Singleton instance
_provider_instance: Optional[MessagingProvider] = None


def get_messaging_provider() -> MessagingProvider:
    """Get the configured messaging provider (singleton).

    Returns:
        MessagingProvider instance based on config.
    """
    global _provider_instance
    if _provider_instance is None:
        name = _get_messaging_provider_name()
        cls = _PROVIDERS.get(name)
        if cls is None:
            print(f"[messaging] Unknown provider '{name}', falling back to telegram",
                  file=sys.stderr)
            cls = TelegramProvider
        _provider_instance = cls()
    return _provider_instance


def reset_provider():
    """Reset the singleton (for testing or config reload)."""
    global _provider_instance
    _provider_instance = None


def send_message(text: str) -> bool:
    """Convenience: send a message via the configured provider.

    This is the drop-in replacement for send_telegram().
    """
    return get_messaging_provider().send_message(text)
