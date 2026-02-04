"""Tests for messaging_provider.py — messaging provider abstraction."""

from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from app.messaging_provider import (
    MessagingProvider,
    TelegramProvider,
    SlackProvider,
    get_messaging_provider,
    reset_provider,
    send_message,
    _get_messaging_provider_name,
    _PROVIDERS,
)


# ---------------------------------------------------------------------------
# TelegramProvider
# ---------------------------------------------------------------------------

class TestTelegramProvider:
    """Tests for TelegramProvider."""

    def setup_method(self):
        reset_provider()

    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "test-token", "KOAN_TELEGRAM_CHAT_ID": "12345"})
    def test_init_reads_env(self):
        p = TelegramProvider()
        assert p.bot_token == "test-token"
        assert p.chat_id == "12345"

    def test_provider_name(self):
        p = TelegramProvider()
        assert p.get_provider_name() == "telegram"

    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "", "KOAN_TELEGRAM_CHAT_ID": ""})
    def test_get_chat_id_empty(self):
        p = TelegramProvider()
        assert p.get_chat_id() == ""

    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "tok", "KOAN_TELEGRAM_CHAT_ID": "42"})
    def test_get_chat_id(self):
        p = TelegramProvider()
        assert p.get_chat_id() == "42"

    def test_max_message_length(self):
        p = TelegramProvider()
        assert p.max_message_length == 4000

    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "", "KOAN_TELEGRAM_CHAT_ID": ""})
    def test_send_message_no_credentials(self):
        p = TelegramProvider()
        assert p.send_message("hello") is False

    @patch("app.messaging_provider.requests.post")
    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "tok", "KOAN_TELEGRAM_CHAT_ID": "42"})
    def test_send_message_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        p = TelegramProvider()
        assert p.send_message("hello") is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["chat_id"] == "42"
        assert call_kwargs[1]["json"]["text"] == "hello"

    @patch("app.messaging_provider.requests.post")
    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "tok", "KOAN_TELEGRAM_CHAT_ID": "42"})
    def test_send_message_api_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False}
        mock_resp.text = "Bad Request"
        mock_post.return_value = mock_resp

        p = TelegramProvider()
        assert p.send_message("hello") is False

    @patch("app.messaging_provider.requests.post")
    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "tok", "KOAN_TELEGRAM_CHAT_ID": "42"})
    def test_send_message_chunks_long_text(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        p = TelegramProvider()
        long_text = "x" * 8500  # Should produce 3 chunks
        p.send_message(long_text)
        assert mock_post.call_count == 3

    @patch("app.messaging_provider.requests.post")
    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "tok", "KOAN_TELEGRAM_CHAT_ID": "42"})
    def test_send_message_network_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("timeout")

        p = TelegramProvider()
        assert p.send_message("hello") is False

    @patch("app.messaging_provider.requests.get")
    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "tok", "KOAN_TELEGRAM_CHAT_ID": "42"})
    def test_get_updates_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 100,
                    "message": {
                        "text": "hello",
                        "chat": {"id": 42},
                    },
                }
            ],
        }
        mock_get.return_value = mock_resp

        p = TelegramProvider()
        updates = p.get_updates()
        assert len(updates) == 1
        assert updates[0]["text"] == "hello"
        assert updates[0]["chat_id"] == "42"
        assert updates[0]["update_id"] == 100

    @patch("app.messaging_provider.requests.get")
    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "tok", "KOAN_TELEGRAM_CHAT_ID": "42"})
    def test_get_updates_with_offset(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": []}
        mock_get.return_value = mock_resp

        p = TelegramProvider()
        p.get_updates(offset=101)
        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["params"]["offset"] == 101

    @patch("app.messaging_provider.requests.get")
    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "tok", "KOAN_TELEGRAM_CHAT_ID": "42"})
    def test_get_updates_network_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("network down")

        p = TelegramProvider()
        assert p.get_updates() == []

    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "tok", "KOAN_TELEGRAM_CHAT_ID": "42"})
    def test_check_config_valid(self):
        p = TelegramProvider()
        p.check_config()  # Should not raise

    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "", "KOAN_TELEGRAM_CHAT_ID": ""})
    def test_check_config_missing(self):
        p = TelegramProvider()
        with pytest.raises(SystemExit):
            p.check_config()


# ---------------------------------------------------------------------------
# SlackProvider
# ---------------------------------------------------------------------------

class TestSlackProvider:
    """Tests for SlackProvider."""

    def setup_method(self):
        reset_provider()

    @patch.dict("os.environ", {
        "KOAN_SLACK_BOT_TOKEN": "xoxb-test",
        "KOAN_SLACK_CHANNEL_ID": "C123",
        "KOAN_SLACK_APP_TOKEN": "xapp-test",
    })
    def test_init_reads_env(self):
        p = SlackProvider()
        assert p.bot_token == "xoxb-test"
        assert p.channel_id == "C123"
        assert p.app_token == "xapp-test"

    def test_provider_name(self):
        p = SlackProvider()
        assert p.get_provider_name() == "slack"

    def test_max_message_length(self):
        p = SlackProvider()
        assert p.max_message_length == 3900

    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "", "KOAN_SLACK_CHANNEL_ID": ""})
    def test_send_message_no_credentials(self):
        p = SlackProvider()
        assert p.send_message("hello") is False

    @patch("app.messaging_provider.requests.post")
    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "xoxb-test", "KOAN_SLACK_CHANNEL_ID": "C123"})
    def test_send_message_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        p = SlackProvider()
        assert p.send_message("hello") is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["channel"] == "C123"
        assert call_kwargs[1]["json"]["text"] == "hello"
        assert "Bearer xoxb-test" in call_kwargs[1]["headers"]["Authorization"]

    @patch("app.messaging_provider.requests.post")
    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "xoxb-test", "KOAN_SLACK_CHANNEL_ID": "C123"})
    def test_send_message_api_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "error": "channel_not_found"}
        mock_post.return_value = mock_resp

        p = SlackProvider()
        assert p.send_message("hello") is False

    @patch("app.messaging_provider.requests.post")
    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "xoxb-test", "KOAN_SLACK_CHANNEL_ID": "C123"})
    def test_send_message_chunks_long_text(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        p = SlackProvider()
        long_text = "x" * 8000  # Should produce 3 chunks (3900 limit)
        p.send_message(long_text)
        assert mock_post.call_count == 3

    @patch("app.messaging_provider.requests.post")
    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "xoxb-test", "KOAN_SLACK_CHANNEL_ID": "C123"})
    def test_send_message_network_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("timeout")

        p = SlackProvider()
        assert p.send_message("hello") is False

    @patch("app.messaging_provider.requests.get")
    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "xoxb-test", "KOAN_SLACK_CHANNEL_ID": "C123"})
    def test_get_updates_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "messages": [
                {"text": "hello", "ts": "1234.5678", "user": "U123"},
                {"text": "bot reply", "ts": "1234.5679", "bot_id": "B123"},
            ],
        }
        mock_get.return_value = mock_resp

        p = SlackProvider()
        updates = p.get_updates()
        # Should filter out bot messages
        assert len(updates) == 1
        assert updates[0]["text"] == "hello"
        assert updates[0]["chat_id"] == "C123"
        assert updates[0]["update_id"] == "1234.5678"

    @patch("app.messaging_provider.requests.get")
    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "xoxb-test", "KOAN_SLACK_CHANNEL_ID": "C123"})
    def test_get_updates_with_offset(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "messages": []}
        mock_get.return_value = mock_resp

        p = SlackProvider()
        p.get_updates(offset="1234.5678")
        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["params"]["oldest"] == "1234.5678"

    @patch("app.messaging_provider.requests.get")
    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "xoxb-test", "KOAN_SLACK_CHANNEL_ID": "C123"})
    def test_get_updates_filters_subtypes(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "messages": [
                {"text": "joined channel", "ts": "1234.5678", "subtype": "channel_join"},
                {"text": "real message", "ts": "1234.5679", "user": "U123"},
            ],
        }
        mock_get.return_value = mock_resp

        p = SlackProvider()
        updates = p.get_updates()
        assert len(updates) == 1
        assert updates[0]["text"] == "real message"

    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "", "KOAN_SLACK_CHANNEL_ID": ""})
    def test_get_updates_no_credentials(self):
        p = SlackProvider()
        assert p.get_updates() == []

    @patch("app.messaging_provider.requests.get")
    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "xoxb-test", "KOAN_SLACK_CHANNEL_ID": "C123"})
    def test_get_updates_api_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "error": "not_authed"}
        mock_get.return_value = mock_resp

        p = SlackProvider()
        assert p.get_updates() == []

    @patch("app.messaging_provider.requests.get")
    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "xoxb-test", "KOAN_SLACK_CHANNEL_ID": "C123"})
    def test_get_updates_network_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("network down")

        p = SlackProvider()
        assert p.get_updates() == []

    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "xoxb-test", "KOAN_SLACK_CHANNEL_ID": "C123"})
    def test_check_config_valid(self):
        p = SlackProvider()
        p.check_config()  # Should not raise

    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "", "KOAN_SLACK_CHANNEL_ID": ""})
    def test_check_config_missing(self):
        p = SlackProvider()
        with pytest.raises(SystemExit):
            p.check_config()

    @patch.dict("os.environ", {"KOAN_SLACK_BOT_TOKEN": "xoxb-test", "KOAN_SLACK_CHANNEL_ID": "C123"})
    def test_get_chat_id(self):
        p = SlackProvider()
        assert p.get_chat_id() == "C123"


# ---------------------------------------------------------------------------
# Factory / singleton
# ---------------------------------------------------------------------------

class TestFactory:
    """Tests for provider factory and singleton."""

    def setup_method(self):
        reset_provider()

    def teardown_method(self):
        reset_provider()

    @patch.dict("os.environ", {
        "KOAN_MESSAGING_PROVIDER": "telegram",
        "KOAN_TELEGRAM_TOKEN": "tok",
        "KOAN_TELEGRAM_CHAT_ID": "42",
    })
    def test_env_selects_telegram(self):
        name = _get_messaging_provider_name()
        assert name == "telegram"

    @patch.dict("os.environ", {
        "KOAN_MESSAGING_PROVIDER": "slack",
        "KOAN_SLACK_BOT_TOKEN": "xoxb-test",
        "KOAN_SLACK_CHANNEL_ID": "C123",
    })
    def test_env_selects_slack(self):
        name = _get_messaging_provider_name()
        assert name == "slack"

    @patch.dict("os.environ", {"KOAN_MESSAGING_PROVIDER": ""})
    @patch("app.utils.load_config", return_value={"messaging_provider": "slack"})
    def test_config_yaml_fallback(self, mock_config):
        name = _get_messaging_provider_name()
        assert name == "slack"

    @patch.dict("os.environ", {"KOAN_MESSAGING_PROVIDER": ""})
    @patch("app.utils.load_config", return_value={})
    def test_default_is_telegram(self, mock_config):
        name = _get_messaging_provider_name()
        assert name == "telegram"

    @patch.dict("os.environ", {"KOAN_MESSAGING_PROVIDER": "TELEGRAM"})
    def test_env_case_insensitive(self):
        name = _get_messaging_provider_name()
        assert name == "telegram"

    @patch.dict("os.environ", {
        "KOAN_MESSAGING_PROVIDER": "telegram",
        "KOAN_TELEGRAM_TOKEN": "tok",
        "KOAN_TELEGRAM_CHAT_ID": "42",
    })
    def test_singleton_returns_same_instance(self):
        p1 = get_messaging_provider()
        p2 = get_messaging_provider()
        assert p1 is p2

    @patch.dict("os.environ", {
        "KOAN_MESSAGING_PROVIDER": "telegram",
        "KOAN_TELEGRAM_TOKEN": "tok",
        "KOAN_TELEGRAM_CHAT_ID": "42",
    })
    def test_reset_clears_singleton(self):
        p1 = get_messaging_provider()
        reset_provider()
        p2 = get_messaging_provider()
        assert p1 is not p2

    @patch.dict("os.environ", {
        "KOAN_MESSAGING_PROVIDER": "telegram",
        "KOAN_TELEGRAM_TOKEN": "tok",
        "KOAN_TELEGRAM_CHAT_ID": "42",
    })
    def test_get_provider_returns_telegram(self):
        p = get_messaging_provider()
        assert isinstance(p, TelegramProvider)

    @patch.dict("os.environ", {
        "KOAN_MESSAGING_PROVIDER": "slack",
        "KOAN_SLACK_BOT_TOKEN": "xoxb-test",
        "KOAN_SLACK_CHANNEL_ID": "C123",
    })
    def test_get_provider_returns_slack(self):
        p = get_messaging_provider()
        assert isinstance(p, SlackProvider)

    @patch.dict("os.environ", {
        "KOAN_MESSAGING_PROVIDER": "unknown_provider",
        "KOAN_TELEGRAM_TOKEN": "tok",
        "KOAN_TELEGRAM_CHAT_ID": "42",
    })
    def test_unknown_provider_falls_back_to_telegram(self):
        p = get_messaging_provider()
        assert isinstance(p, TelegramProvider)

    def test_providers_registry(self):
        assert "telegram" in _PROVIDERS
        assert "slack" in _PROVIDERS
        assert _PROVIDERS["telegram"] is TelegramProvider
        assert _PROVIDERS["slack"] is SlackProvider


# ---------------------------------------------------------------------------
# send_message convenience function
# ---------------------------------------------------------------------------

class TestSendMessage:
    """Tests for the send_message convenience function."""

    def setup_method(self):
        reset_provider()

    def teardown_method(self):
        reset_provider()

    @patch("app.messaging_provider.requests.post")
    @patch.dict("os.environ", {
        "KOAN_MESSAGING_PROVIDER": "telegram",
        "KOAN_TELEGRAM_TOKEN": "tok",
        "KOAN_TELEGRAM_CHAT_ID": "42",
    })
    def test_send_message_delegates_to_provider(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        assert send_message("hello") is True
        mock_post.assert_called_once()


# ---------------------------------------------------------------------------
# Abstract base class contract
# ---------------------------------------------------------------------------

class TestAbstractContract:
    """Verify both providers implement the full interface."""

    @patch.dict("os.environ", {"KOAN_TELEGRAM_TOKEN": "t", "KOAN_TELEGRAM_CHAT_ID": "1"})
    def test_telegram_implements_interface(self):
        p = TelegramProvider()
        assert hasattr(p, "send_message")
        assert hasattr(p, "get_updates")
        assert hasattr(p, "check_config")
        assert hasattr(p, "get_provider_name")
        assert hasattr(p, "get_chat_id")
        assert hasattr(p, "max_message_length")

    def test_slack_implements_interface(self):
        p = SlackProvider()
        assert hasattr(p, "send_message")
        assert hasattr(p, "get_updates")
        assert hasattr(p, "check_config")
        assert hasattr(p, "get_provider_name")
        assert hasattr(p, "get_chat_id")
        assert hasattr(p, "max_message_length")

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            MessagingProvider()
