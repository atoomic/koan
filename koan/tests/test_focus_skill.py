"""Tests for the /focus and /unfocus skill handlers."""

import json
from unittest.mock import MagicMock

from app.skills import SkillContext


def _make_ctx(command_name, koan_root, args=""):
    """Create a minimal SkillContext for testing."""
    ctx = MagicMock(spec=SkillContext)
    ctx.command_name = command_name
    ctx.koan_root = koan_root
    ctx.args = args
    return ctx


class TestFocusCommand:
    """Tests for /focus command."""

    def test_focus_creates_marker_file(self, tmp_path):
        from skills.core.focus.handler import handle

        ctx = _make_ctx("focus", tmp_path)
        result = handle(ctx)

        assert "ON" in result or "🎯" in result
        marker = tmp_path / ".koan-focus"
        assert marker.exists()

    def test_focus_default_duration(self, tmp_path):
        from skills.core.focus.handler import handle

        ctx = _make_ctx("focus", tmp_path)
        result = handle(ctx)

        # Default is 5h — must show exact "5h00m", not "4h59m" (regression: PR #204)
        assert "5h00m" in result
        marker = tmp_path / ".koan-focus"
        assert marker.exists()

    def test_focus_custom_duration(self, tmp_path):
        from skills.core.focus.handler import handle

        ctx = _make_ctx("focus", tmp_path, args="3h")
        result = handle(ctx)

        assert "3h" in result or "3 h" in result
        marker = tmp_path / ".koan-focus"
        assert marker.exists()

    def test_focus_duration_with_minutes(self, tmp_path):
        from skills.core.focus.handler import handle

        ctx = _make_ctx("focus", tmp_path, args="2h30m")
        result = handle(ctx)

        assert "ON" in result
        marker = tmp_path / ".koan-focus"
        assert marker.exists()

    def test_focus_invalid_duration(self, tmp_path):
        from skills.core.focus.handler import handle

        ctx = _make_ctx("focus", tmp_path, args="invalid")
        result = handle(ctx)

        assert "Invalid" in result or "❌" in result
        marker = tmp_path / ".koan-focus"
        assert not marker.exists()

    def test_focus_shows_full_duration_despite_time_drift(self, tmp_path):
        """Regression test: handler must show full duration, not remaining-after-drift.

        Previously, create_focus() called time.time() and remaining_display()
        called time.time() again — a 1s drift on slow CI produced "4h59m"
        instead of "5h00m". Fix: handler passes now=state.activated_at.
        """
        from unittest.mock import patch

        from skills.core.focus.handler import handle

        # Simulate 2s drift between create_focus and remaining_display
        call_count = 0
        base_time = 1700000000

        def drifting_time():
            nonlocal call_count
            call_count += 1
            # Each time.time() call returns a slightly later timestamp
            return base_time + call_count

        with patch("app.focus_manager.time") as mock_time:
            mock_time.time.side_effect = drifting_time
            ctx = _make_ctx("focus", tmp_path, args="5h")
            result = handle(ctx)

        # Must show "5h00m" — the full requested duration
        assert "5h00m" in result

    def test_focus_response_mentions_missions_only(self, tmp_path):
        from skills.core.focus.handler import handle

        ctx = _make_ctx("focus", tmp_path)
        result = handle(ctx)

        assert "mission" in result.lower()


class TestUnfocusCommand:
    """Tests for /unfocus command."""

    def test_unfocus_removes_marker(self, tmp_path):
        from skills.core.focus.handler import handle

        # First create focus state
        marker = tmp_path / ".koan-focus"
        marker.write_text(json.dumps({"end_time": 9999999999}))

        ctx = _make_ctx("unfocus", tmp_path)
        result = handle(ctx)

        assert "OFF" in result or "🎯" in result
        assert not marker.exists()

    def test_unfocus_when_not_focused(self, tmp_path):
        from skills.core.focus.handler import handle

        # No marker file exists
        ctx = _make_ctx("unfocus", tmp_path)
        result = handle(ctx)

        assert "Not" in result or "not" in result


class TestFocusUnfocusToggle:
    """Test toggling between focus and unfocus modes."""

    def test_toggle_focus_then_unfocus(self, tmp_path):
        from skills.core.focus.handler import handle

        marker = tmp_path / ".koan-focus"

        # Enable focus
        ctx_focus = _make_ctx("focus", tmp_path)
        handle(ctx_focus)
        assert marker.exists()

        # Disable with unfocus
        ctx_unfocus = _make_ctx("unfocus", tmp_path)
        handle(ctx_unfocus)
        assert not marker.exists()

    def test_focus_overwrites_existing(self, tmp_path):
        from skills.core.focus.handler import handle

        marker = tmp_path / ".koan-focus"

        # Enable focus with 2h
        ctx1 = _make_ctx("focus", tmp_path, args="2h")
        handle(ctx1)
        assert marker.exists()

        # Enable again with 4h - should overwrite
        ctx2 = _make_ctx("focus", tmp_path, args="4h")
        result = handle(ctx2)

        assert marker.exists()
        assert "4h" in result or "4 h" in result
