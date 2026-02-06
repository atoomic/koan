"""Tests for x_post.py — X (Twitter) posting, rate limiting, pending queue."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.x_post import (
    _get_x_config,
    can_post,
    is_duplicate,
    queue_tweet,
    post_approved_tweet,
    reject_pending_tweet,
    get_pending_count,
    get_next_pending,
    get_x_stats,
    delete_tweet,
    _load_cooldown,
    _save_cooldown,
    _prune_old_records,
    _content_hash,
    _trip_circuit_breaker,
    _reset_circuit_breaker,
    _load_circuit_breaker,
    _load_pending,
    _save_pending,
    _audit_log,
)


@pytest.fixture
def x_env(tmp_path, monkeypatch):
    """Set up isolated X posting environment."""
    monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
    monkeypatch.setattr("app.utils.KOAN_ROOT", tmp_path)
    (tmp_path / "instance").mkdir()
    # Config with X enabled
    config_path = tmp_path / "instance" / "config.yaml"
    config_path.write_text(
        "x:\n"
        "  enabled: true\n"
        "  max_per_day: 3\n"
        "  require_approval: true\n"
        "  content_screening: true\n"
    )
    return tmp_path


@pytest.fixture
def x_disabled_env(tmp_path, monkeypatch):
    """Set up X posting environment with X disabled."""
    monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
    monkeypatch.setattr("app.utils.KOAN_ROOT", tmp_path)
    (tmp_path / "instance").mkdir()
    config_path = tmp_path / "instance" / "config.yaml"
    config_path.write_text("x:\n  enabled: false\n")
    return tmp_path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestXConfig:
    def test_defaults_when_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
        (tmp_path / "instance").mkdir()
        (tmp_path / "instance" / "config.yaml").write_text("")
        config = _get_x_config()
        assert config["enabled"] is False
        assert config["max_per_day"] == 3
        assert config["require_approval"] is True

    def test_reads_enabled(self, x_env):
        config = _get_x_config()
        assert config["enabled"] is True


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    def test_empty_cooldown(self, x_env):
        records = _load_cooldown()
        assert records == []

    def test_save_and_load(self, x_env):
        records = [{"timestamp": time.time(), "content_hash": "abc"}]
        _save_cooldown(records)
        loaded = _load_cooldown()
        assert len(loaded) == 1
        assert loaded[0]["content_hash"] == "abc"

    def test_prune_old_records(self):
        old = {"timestamp": time.time() - 90000}
        recent = {"timestamp": time.time() - 100}
        result = _prune_old_records([old, recent])
        assert len(result) == 1

    def test_content_hash_consistent(self):
        h1 = _content_hash("hello world")
        h2 = _content_hash("hello world")
        assert h1 == h2
        assert len(h1) == 16

    def test_content_hash_differs(self):
        h1 = _content_hash("hello")
        h2 = _content_hash("world")
        assert h1 != h2


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    def test_no_duplicate_when_empty(self, x_env):
        assert is_duplicate("new tweet") is False

    def test_detects_duplicate(self, x_env):
        text = "test tweet content"
        records = [{"timestamp": time.time(), "content_hash": _content_hash(text)}]
        _save_cooldown(records)
        assert is_duplicate(text) is True

    def test_no_false_positive(self, x_env):
        records = [{"timestamp": time.time(), "content_hash": _content_hash("old tweet")}]
        _save_cooldown(records)
        assert is_duplicate("new tweet") is False


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_initial_state(self, x_env):
        state = _load_circuit_breaker()
        assert state["failures"] == 0

    def test_trips_after_two_failures(self, x_env):
        _trip_circuit_breaker()
        state = _load_circuit_breaker()
        assert state["failures"] == 1
        assert state.get("disabled_until", 0) == 0

        _trip_circuit_breaker()
        state = _load_circuit_breaker()
        assert state["failures"] == 2
        assert state["disabled_until"] > time.time()

    def test_reset_clears_state(self, x_env):
        _trip_circuit_breaker()
        _trip_circuit_breaker()
        _reset_circuit_breaker()
        state = _load_circuit_breaker()
        assert state["failures"] == 0
        assert state["disabled_until"] == 0


# ---------------------------------------------------------------------------
# can_post
# ---------------------------------------------------------------------------

class TestCanPost:
    def test_disabled(self, x_disabled_env):
        ok, reason = can_post()
        assert ok is False
        assert "not enabled" in reason

    @patch("app.x_post.is_configured", return_value=(True, "OK"))
    def test_allowed_when_configured(self, _mock, x_env):
        ok, _ = can_post()
        assert ok is True

    @patch("app.x_post.is_configured", return_value=(False, "No client ID"))
    def test_fails_without_credentials(self, _mock, x_env):
        ok, reason = can_post()
        assert ok is False
        assert "client ID" in reason.lower() or "No client" in reason

    @patch("app.x_post.is_configured", return_value=(True, "OK"))
    def test_rate_limited(self, _mock, x_env):
        # Fill up cooldown
        records = [{"timestamp": time.time(), "content_hash": f"h{i}"} for i in range(3)]
        _save_cooldown(records)
        ok, reason = can_post()
        assert ok is False
        assert "Rate limit" in reason

    @patch("app.x_post.is_configured", return_value=(True, "OK"))
    def test_circuit_breaker_blocks(self, _mock, x_env):
        _trip_circuit_breaker()
        _trip_circuit_breaker()
        ok, reason = can_post()
        assert ok is False
        assert "Circuit breaker" in reason


# ---------------------------------------------------------------------------
# Pending queue
# ---------------------------------------------------------------------------

class TestPendingQueue:
    def test_empty_queue(self, x_env):
        assert get_pending_count() == 0
        assert get_next_pending() is None

    def test_save_and_load_pending(self, x_env):
        entries = [
            {"trigger": "koan", "queued_at": "2026-02-05T20:00:00", "text": "First tweet"},
            {"trigger": "learning", "queued_at": "2026-02-05T20:01:00", "text": "Second tweet"},
        ]
        _save_pending(entries)
        assert get_pending_count() == 2
        first = get_next_pending()
        assert first["text"] == "First tweet"
        assert first["trigger"] == "koan"


# ---------------------------------------------------------------------------
# queue_tweet
# ---------------------------------------------------------------------------

class TestQueueTweet:
    def test_disabled_returns_error(self, x_disabled_env):
        status, msg = queue_tweet("koan", "Test tweet")
        assert status == "error"
        assert "not enabled" in msg

    def test_bad_trigger_rejected(self, x_env):
        status, msg = queue_tweet("spam", "Buy now!")
        assert status == "rejected"
        assert "not in allowed_triggers" in msg

    @patch("app.x_post.screen_content", return_value=(False, "Blocked: project name"))
    def test_screening_blocks(self, _mock, x_env):
        status, msg = queue_tweet("koan", "Some text")
        assert status == "rejected"
        assert "screening failed" in msg

    @patch("app.x_post.screen_content", return_value=(True, "OK"))
    @patch("app.x_post.sanitize_for_tweet", side_effect=lambda x: x)
    def test_queues_for_approval(self, _san, _screen, x_env):
        status, msg = queue_tweet("koan", "If tests pass but nothing changes, was it a test?")
        assert status == "queued"
        assert get_pending_count() == 1

    @patch("app.x_post.screen_content", return_value=(True, "OK"))
    @patch("app.x_post.sanitize_for_tweet", side_effect=lambda x: x)
    def test_duplicate_rejected(self, _san, _screen, x_env):
        text = "Same tweet content"
        records = [{"timestamp": time.time(), "content_hash": _content_hash(text)}]
        _save_cooldown(records)
        status, msg = queue_tweet("koan", text)
        assert status == "rejected"
        assert "Duplicate" in msg

    @patch("app.x_post._do_post", return_value=("posted", "12345"))
    @patch("app.x_post.screen_content", return_value=(True, "OK"))
    @patch("app.x_post.sanitize_for_tweet", side_effect=lambda x: x)
    def test_auto_post_when_no_approval(self, _san, _screen, _post, tmp_path, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
        monkeypatch.setattr("app.utils.KOAN_ROOT", tmp_path)
        (tmp_path / "instance").mkdir()
        (tmp_path / "instance" / "config.yaml").write_text(
            "x:\n  enabled: true\n  require_approval: false\n  max_per_day: 3\n"
        )
        status, msg = queue_tweet("koan", "Auto post test")
        assert status == "posted"
        assert msg == "12345"


# ---------------------------------------------------------------------------
# post_approved_tweet
# ---------------------------------------------------------------------------

class TestPostApprovedTweet:
    def test_empty_queue(self, x_env):
        status, msg = post_approved_tweet()
        assert status == "empty"

    @patch("app.x_post._do_post", return_value=("posted", "99999"))
    @patch("app.x_post.screen_content", return_value=(True, "OK"))
    def test_posts_and_removes_from_queue(self, _screen, _post, x_env):
        entries = [{"trigger": "koan", "queued_at": "2026-02-05T20:00:00", "text": "Zen tweet"}]
        _save_pending(entries)
        assert get_pending_count() == 1

        status, msg = post_approved_tweet()
        assert status == "posted"
        assert msg == "99999"
        assert get_pending_count() == 0

    @patch("app.x_post.screen_content", return_value=(False, "Blocked: too sensitive"))
    def test_rejects_if_screening_fails(self, _screen, x_env):
        entries = [{"trigger": "koan", "queued_at": "2026-02-05T20:00:00", "text": "Bad tweet"}]
        _save_pending(entries)

        status, msg = post_approved_tweet()
        assert status == "rejected"
        assert get_pending_count() == 0  # Removed from queue


# ---------------------------------------------------------------------------
# reject_pending_tweet
# ---------------------------------------------------------------------------

class TestRejectPendingTweet:
    def test_empty_queue(self, x_env):
        status, msg = reject_pending_tweet()
        assert status == "empty"

    def test_removes_first_entry(self, x_env):
        entries = [
            {"trigger": "koan", "queued_at": "2026-02-05T20:00:00", "text": "First"},
            {"trigger": "koan", "queued_at": "2026-02-05T20:01:00", "text": "Second"},
        ]
        _save_pending(entries)

        status, msg = reject_pending_tweet("Not good enough")
        assert status == "rejected"
        assert get_pending_count() == 1
        assert get_next_pending()["text"] == "Second"


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestXStats:
    def test_disabled_stats(self, x_disabled_env):
        stats = get_x_stats()
        assert stats["enabled"] is False

    @patch("app.x_post.is_configured", return_value=(True, "OK"))
    def test_enabled_stats(self, _mock, x_env):
        stats = get_x_stats()
        assert stats["enabled"] is True
        assert stats["posted_24h"] == 0
        assert stats["remaining"] == 3
        assert stats["pending"] == 0
        assert stats["require_approval"] is True
        assert stats["circuit_breaker_active"] is False

    @patch("app.x_post.is_configured", return_value=(True, "OK"))
    def test_stats_with_posts(self, _mock, x_env):
        records = [
            {"timestamp": time.time(), "content_hash": "h1"},
            {"timestamp": time.time(), "content_hash": "h2"},
        ]
        _save_cooldown(records)
        stats = get_x_stats()
        assert stats["posted_24h"] == 2
        assert stats["remaining"] == 1


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_writes_log_entry(self, x_env):
        _audit_log("12345", "Test tweet content", "koan")
        log_path = x_env / "instance" / "x-posted.log"
        assert log_path.exists()
        entry = json.loads(log_path.read_text().strip())
        assert entry["tweet_id"] == "12345"
        assert entry["trigger"] == "koan"

    def test_appends_multiple_entries(self, x_env):
        _audit_log("1", "First", "koan")
        _audit_log("2", "Second", "learning")
        log_path = x_env / "instance" / "x-posted.log"
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
