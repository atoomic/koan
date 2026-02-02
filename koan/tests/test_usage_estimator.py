"""Tests for usage_estimator.py — Token accumulation and usage % estimation."""

import json
import time
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app.usage_estimator import (
    _extract_tokens,
    _fresh_state,
    _load_state,
    _maybe_reset,
    _write_usage_md,
    _get_limits,
    cmd_update,
    cmd_refresh,
    SESSION_DURATION_HOURS,
)


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "usage_state.json"


@pytest.fixture
def usage_md(tmp_path):
    return tmp_path / "usage.md"


@pytest.fixture
def claude_json(tmp_path):
    """Claude --output-format json output with token counts."""
    f = tmp_path / "claude_out.json"
    f.write_text(json.dumps({
        "result": "Hello, I completed the task.",
        "input_tokens": 1500,
        "output_tokens": 500,
    }))
    return f


@pytest.fixture
def claude_json_nested(tmp_path):
    """Claude JSON with nested usage object."""
    f = tmp_path / "claude_nested.json"
    f.write_text(json.dumps({
        "result": "Done.",
        "usage": {"input_tokens": 3000, "output_tokens": 1000},
    }))
    return f


class TestExtractTokens:
    def test_top_level_fields(self, claude_json):
        assert _extract_tokens(claude_json) == 2000

    def test_nested_usage(self, claude_json_nested):
        assert _extract_tokens(claude_json_nested) == 4000

    def test_no_tokens(self, tmp_path):
        f = tmp_path / "no_tokens.json"
        f.write_text(json.dumps({"result": "hello"}))
        assert _extract_tokens(f) is None

    def test_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json at all")
        assert _extract_tokens(f) is None

    def test_missing_file(self, tmp_path):
        assert _extract_tokens(tmp_path / "nonexistent.json") is None


class TestMaybeReset:
    def test_no_reset_within_session(self):
        state = _fresh_state()
        result = _maybe_reset(state)
        assert result["session_tokens"] == 0

    def test_session_resets_after_5h(self):
        state = _fresh_state()
        state["session_tokens"] = 100000
        state["runs"] = 5
        # Set session start to 6 hours ago
        state["session_start"] = (datetime.now() - timedelta(hours=6)).isoformat()
        result = _maybe_reset(state)
        assert result["session_tokens"] == 0
        assert result["runs"] == 0

    def test_weekly_resets_after_7_days(self):
        state = _fresh_state()
        state["weekly_tokens"] = 500000
        state["weekly_start"] = (datetime.now() - timedelta(days=8)).isoformat()
        result = _maybe_reset(state)
        assert result["weekly_tokens"] == 0


class TestWriteUsageMd:
    def test_writes_parseable_format(self, tmp_path, usage_md):
        state = {
            "session_start": datetime.now().isoformat(),
            "session_tokens": 125000,
            "weekly_start": datetime.now().isoformat(),
            "weekly_tokens": 1250000,
            "runs": 5,
        }
        config = {"usage": {"session_token_limit": 500000, "weekly_token_limit": 5000000}}
        _write_usage_md(state, usage_md, config)

        content = usage_md.read_text()
        assert "Session (5hr) : 25%" in content
        assert "Weekly (7 day) : 25%" in content
        assert "reset in" in content

    def test_caps_at_100_percent(self, tmp_path, usage_md):
        state = {
            "session_start": datetime.now().isoformat(),
            "session_tokens": 999999,
            "weekly_start": datetime.now().isoformat(),
            "weekly_tokens": 999999,
            "runs": 10,
        }
        config = {"usage": {"session_token_limit": 100, "weekly_token_limit": 100}}
        _write_usage_md(state, usage_md, config)

        content = usage_md.read_text()
        assert "100%" in content


class TestCmdUpdate:
    @patch("app.usage_estimator.load_config", return_value={
        "usage": {"session_token_limit": 500000, "weekly_token_limit": 5000000}
    })
    def test_accumulates_tokens(self, mock_config, claude_json, state_file, usage_md):
        cmd_update(claude_json, state_file, usage_md)

        state = json.loads(state_file.read_text())
        assert state["session_tokens"] == 2000
        assert state["weekly_tokens"] == 2000
        assert state["runs"] == 1

        # Second run accumulates
        cmd_update(claude_json, state_file, usage_md)
        state = json.loads(state_file.read_text())
        assert state["session_tokens"] == 4000
        assert state["runs"] == 2

    @patch("app.usage_estimator.load_config", return_value={})
    def test_handles_no_tokens_gracefully(self, mock_config, tmp_path, state_file, usage_md):
        f = tmp_path / "empty.json"
        f.write_text(json.dumps({"result": "done"}))
        cmd_update(f, state_file, usage_md)

        state = json.loads(state_file.read_text())
        assert state["session_tokens"] == 0


class TestCmdRefresh:
    @patch("app.usage_estimator.load_config", return_value={
        "usage": {"session_token_limit": 500000, "weekly_token_limit": 5000000}
    })
    def test_creates_usage_md(self, mock_config, state_file, usage_md):
        # Write some state
        state = _fresh_state()
        state["session_tokens"] = 50000
        state["weekly_tokens"] = 250000
        state_file.write_text(json.dumps(state))

        cmd_refresh(state_file, usage_md)

        content = usage_md.read_text()
        assert "Session (5hr) : 10%" in content
        assert "Weekly (7 day) : 5%" in content

    @patch("app.usage_estimator.load_config", return_value={})
    def test_fresh_state_if_no_file(self, mock_config, state_file, usage_md):
        cmd_refresh(state_file, usage_md)
        assert usage_md.exists()
        content = usage_md.read_text()
        assert "0%" in content


class TestGetLimits:
    def test_defaults(self):
        session, weekly = _get_limits({})
        assert session == 500000
        assert weekly == 5000000

    def test_custom(self):
        config = {"usage": {"session_token_limit": 100000, "weekly_token_limit": 1000000}}
        session, weekly = _get_limits(config)
        assert session == 100000
        assert weekly == 1000000
