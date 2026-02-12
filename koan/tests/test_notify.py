"""Tests for notify.py — message sending, chunking, error handling, format_and_send."""

from unittest.mock import patch, MagicMock

import pytest
import requests

from app.notify import send_telegram, format_and_send, reset_flood_state


class TestSendTelegram:
    def setup_method(self):
        reset_flood_state()

    @patch("app.notify.requests.post")
    def test_short_message(self, mock_post):
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        assert send_telegram("hello") is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["text"] == "hello"

    @patch("app.notify.requests.post")
    def test_long_message_chunked(self, mock_post):
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        long_msg = "x" * 8500  # Should be split into 3 chunks (4000+4000+500)
        assert send_telegram(long_msg) is True
        assert mock_post.call_count == 3

    @patch("app.notify.requests.post")
    def test_exact_boundary_no_extra_chunk(self, mock_post):
        """Message of exactly 4000 chars should produce 1 chunk, not 2."""
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        assert send_telegram("x" * 4000) is True
        assert mock_post.call_count == 1

    @patch("app.notify.requests.post")
    def test_just_over_boundary(self, mock_post):
        """Message of 4001 chars should produce 2 chunks."""
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        assert send_telegram("x" * 4001) is True
        assert mock_post.call_count == 2

    @patch("app.notify.requests.post")
    def test_empty_message_sends_nothing(self, mock_post):
        """Empty string produces zero chunks — no API call, returns True."""
        assert send_telegram("") is True
        mock_post.assert_not_called()

    @patch("app.notify.requests.post")
    def test_partial_failure_returns_false(self, mock_post):
        """If one chunk fails but others succeed, return False."""
        responses = [
            MagicMock(json=lambda: {"ok": True}),
            MagicMock(json=lambda: {"ok": False, "description": "rate limit"}, text="rate limit"),
        ]
        mock_post.side_effect = responses
        assert send_telegram("a" * 5000) is False
        assert mock_post.call_count == 2

    @patch("app.notify.requests.post")
    def test_api_error(self, mock_post):
        mock_post.return_value = MagicMock(
            json=lambda: {"ok": False, "description": "bad request"},
            text='{"ok":false}',
        )
        assert send_telegram("test") is False

    @patch("app.notify.requests.post", side_effect=requests.RequestException("network error"))
    def test_network_error(self, mock_post):
        assert send_telegram("test") is False

    @patch("app.notify.requests.post", side_effect=ValueError("bad json"))
    def test_json_decode_error(self, mock_post):
        """ValueError from resp.json() is caught."""
        assert send_telegram("test") is False

    def test_no_token(self, monkeypatch):
        monkeypatch.delenv("KOAN_TELEGRAM_TOKEN", raising=False)
        assert send_telegram("test") is False

    def test_no_chat_id(self, monkeypatch):
        monkeypatch.delenv("KOAN_TELEGRAM_CHAT_ID", raising=False)
        assert send_telegram("test") is False


class TestFormatAndSend:
    @patch("app.notify.send_telegram", return_value=True)
    def test_with_instance_dir(self, mock_send, instance_dir):
        """format_and_send with explicit instance_dir loads soul/prefs and formats."""
        with patch("app.format_outbox.format_message", return_value="formatted msg") as mock_fmt, \
             patch("app.format_outbox.load_soul", return_value="soul"), \
             patch("app.format_outbox.load_human_prefs", return_value="prefs"), \
             patch("app.format_outbox.load_memory_context", return_value="memory"):
            result = format_and_send("raw msg", instance_dir=str(instance_dir))

        assert result is True
        mock_fmt.assert_called_once_with("raw msg", "soul", "prefs", "memory")
        mock_send.assert_called_once_with("formatted msg")

    @patch("app.notify.send_telegram", return_value=True)
    def test_fallback_on_format_error(self, mock_send, instance_dir):
        """If formatting raises, fallback to basic cleanup."""
        with patch("app.format_outbox.load_soul", side_effect=OSError("boom")), \
             patch("app.format_outbox.fallback_format", return_value="clean msg") as mock_fb:
            result = format_and_send("raw", instance_dir=str(instance_dir))

        assert result is True
        mock_fb.assert_called_once_with("raw")
        mock_send.assert_called_once_with("clean msg")

    @patch("app.notify.send_telegram", return_value=True)
    @patch("app.notify.load_dotenv")
    def test_no_koan_root_sends_fallback(self, mock_dotenv, mock_send, monkeypatch):
        """Without KOAN_ROOT and no instance_dir, sends basic fallback."""
        monkeypatch.delenv("KOAN_ROOT", raising=False)
        result = format_and_send("raw technical msg")

        assert result is True
        # Should have called send_telegram with some version of the message
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][0]
        assert len(sent_text) > 0  # fallback_format produces non-empty output

    @patch("app.notify.send_telegram", return_value=True)
    def test_koan_root_auto_detect(self, mock_send, tmp_path, monkeypatch):
        """With KOAN_ROOT set, instance_dir is auto-detected."""
        monkeypatch.setenv("KOAN_ROOT", str(tmp_path))

        with patch("app.format_outbox.load_soul", return_value="s"), \
             patch("app.format_outbox.load_human_prefs", return_value="p"), \
             patch("app.format_outbox.load_memory_context", return_value="m"), \
             patch("app.format_outbox.format_message", return_value="fmt"):
            result = format_and_send("raw")

        assert result is True
        mock_send.assert_called_once_with("fmt")

    @patch("app.notify.send_telegram", return_value=True)
    def test_project_name_passed_to_memory(self, mock_send, instance_dir):
        """project_name argument is forwarded to load_memory_context."""
        with patch("app.format_outbox.load_soul", return_value="s"), \
             patch("app.format_outbox.load_human_prefs", return_value="p"), \
             patch("app.format_outbox.load_memory_context", return_value="m") as mock_mem, \
             patch("app.format_outbox.format_message", return_value="fmt"):
            format_and_send("raw", instance_dir=str(instance_dir),
                           project_name="myproject")

        mock_mem.assert_called_once()
        assert mock_mem.call_args[0][1] == "myproject"


class TestNotifyCLI:
    """Tests for __main__ CLI entry point (lines 97-119)."""

    def test_cli_send_message(self, monkeypatch):
        from tests._helpers import run_module
        monkeypatch.setattr("sys.argv", ["notify.py", "Hello", "world"])
        with patch("app.notify.requests.post") as mock_post, \
             pytest.raises(SystemExit) as exc_info:
            mock_post.return_value = MagicMock(json=lambda: {"ok": True})
            run_module("app.notify", run_name="__main__")
        assert exc_info.value.code == 0

    def test_cli_format_flag(self, monkeypatch):
        from tests._helpers import run_module
        monkeypatch.setattr("sys.argv", ["notify.py", "--format", "Raw msg"])
        with patch("app.notify.requests.post") as mock_post, \
             patch("app.format_outbox.subprocess.run") as mock_sub, \
             pytest.raises(SystemExit) as exc_info:
            mock_post.return_value = MagicMock(json=lambda: {"ok": True})
            mock_sub.return_value = MagicMock(returncode=0, stdout="Formatted", stderr="")
            run_module("app.notify", run_name="__main__")
        assert exc_info.value.code == 0

    def test_cli_format_passes_project_name(self, monkeypatch):
        """CLI --format reads KOAN_CURRENT_PROJECT env var."""
        from tests._helpers import run_module
        monkeypatch.setattr("sys.argv", ["notify.py", "--format", "Raw msg"])
        monkeypatch.setenv("KOAN_CURRENT_PROJECT", "myproject")
        with patch("app.notify.requests.post") as mock_post, \
             patch("app.format_outbox.subprocess.run") as mock_sub, \
             pytest.raises(SystemExit) as exc_info:
            mock_post.return_value = MagicMock(json=lambda: {"ok": True})
            mock_sub.return_value = MagicMock(returncode=0, stdout="Formatted", stderr="")
            run_module("app.notify", run_name="__main__")
        assert exc_info.value.code == 0
        # Verify Claude was called (format_and_send path was used)
        mock_sub.assert_called_once()

    def test_cli_no_args(self, monkeypatch):
        from tests._helpers import run_module
        monkeypatch.setattr("sys.argv", ["notify.py"])
        with pytest.raises(SystemExit) as exc_info:
            run_module("app.notify", run_name="__main__")
        assert exc_info.value.code == 1

    def test_cli_format_no_message(self, monkeypatch):
        from tests._helpers import run_module
        monkeypatch.setattr("sys.argv", ["notify.py", "--format"])
        with pytest.raises(SystemExit) as exc_info:
            run_module("app.notify", run_name="__main__")
        assert exc_info.value.code == 1

    def test_cli_failure_exit_code(self, monkeypatch):
        from tests._helpers import run_module
        monkeypatch.setattr("sys.argv", ["notify.py", "msg"])
        with patch("app.notify.send_telegram", return_value=False), \
             pytest.raises(SystemExit) as exc_info:
            run_module("app.notify", run_name="__main__")
        assert exc_info.value.code == 1


class TestFloodProtection:
    """Tests for duplicate message flood protection in send_telegram()."""

    def setup_method(self):
        reset_flood_state()

    @patch("app.notify.time.time", return_value=1000.0)
    @patch("app.notify.requests.post")
    def test_first_message_passes(self, mock_post, mock_time):
        """First message is always sent through."""
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        assert send_telegram("hello") is True
        assert mock_post.call_count == 1

    @patch("app.notify.requests.post")
    def test_second_identical_triggers_warning(self, mock_post):
        """Second identical message within window triggers a flood warning."""
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        with patch("app.notify.time.time", return_value=1000.0):
            send_telegram("hello")
        with patch("app.notify.time.time", return_value=1010.0):
            result = send_telegram("hello")

        assert result is True
        # 1 for original message + 1 for flood warning
        assert mock_post.call_count == 2
        warning_text = mock_post.call_args_list[1][1]["json"]["text"]
        assert "flood" in warning_text.lower()

    @patch("app.notify.requests.post")
    def test_third_duplicate_silently_suppressed(self, mock_post):
        """Third and subsequent duplicates are silently suppressed (no API calls)."""
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        with patch("app.notify.time.time", return_value=1000.0):
            send_telegram("hello")
        with patch("app.notify.time.time", return_value=1010.0):
            send_telegram("hello")  # triggers warning
        with patch("app.notify.time.time", return_value=1020.0):
            result = send_telegram("hello")  # silently suppressed

        assert result is True
        # Only 2 API calls: original + warning (third is suppressed)
        assert mock_post.call_count == 2

    @patch("app.notify.requests.post")
    def test_different_message_resets(self, mock_post):
        """A different message resets flood state and goes through."""
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        with patch("app.notify.time.time", return_value=1000.0):
            send_telegram("hello")
        with patch("app.notify.time.time", return_value=1010.0):
            send_telegram("hello")  # triggers warning
        with patch("app.notify.time.time", return_value=1020.0):
            result = send_telegram("world")  # different message

        assert result is True
        # 3 API calls: original + warning + new message
        assert mock_post.call_count == 3

    @patch("app.notify.requests.post")
    def test_window_expiry_allows_resend(self, mock_post):
        """Same message after 5-minute window expires is allowed through."""
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        with patch("app.notify.time.time", return_value=1000.0):
            send_telegram("hello")
        with patch("app.notify.time.time", return_value=1000.0 + 301):
            result = send_telegram("hello")  # after window expires

        assert result is True
        # Both messages sent (no flood suppression)
        assert mock_post.call_count == 2
        # Both are the actual message, not a warning
        for call in mock_post.call_args_list:
            assert call[1]["json"]["text"] == "hello"

    @patch("app.notify.requests.post")
    def test_flood_with_chunked_message(self, mock_post):
        """Flood protection works correctly with multi-chunk messages."""
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        long_msg = "x" * 5000  # 2 chunks
        with patch("app.notify.time.time", return_value=1000.0):
            send_telegram(long_msg)
        with patch("app.notify.time.time", return_value=1010.0):
            result = send_telegram(long_msg)  # duplicate

        assert result is True
        # 2 chunks for first message + 1 for flood warning
        assert mock_post.call_count == 3

    @patch("app.notify.requests.post")
    def test_api_failure_still_updates_state(self, mock_post):
        """Failed send still tracks message for flood detection (prevents retry spam)."""
        mock_post.return_value = MagicMock(
            json=lambda: {"ok": False, "description": "error"},
            text='{"ok":false}',
        )
        with patch("app.notify.time.time", return_value=1000.0):
            send_telegram("hello")  # fails
        with patch("app.notify.time.time", return_value=1010.0):
            result = send_telegram("hello")  # still detected as duplicate

        assert result is True
        # 1 for failed original + 1 for flood warning
        assert mock_post.call_count == 2
