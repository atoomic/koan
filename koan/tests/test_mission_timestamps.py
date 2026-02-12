"""Tests for mission lifecycle timestamp tracking."""

import re
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.missions import (
    _QUEUED_MARKER,
    _STARTED_MARKER,
    _TS_FORMAT,
    DEFAULT_SKELETON,
    complete_mission,
    extract_timestamps,
    fail_mission,
    format_duration,
    insert_mission,
    mission_timing_display,
    stamp_queued,
    stamp_started,
    start_mission,
    strip_timestamps,
)


# ---------------------------------------------------------------------------
# stamp_queued / stamp_started
# ---------------------------------------------------------------------------


class TestStampQueued:
    def test_appends_timestamp(self):
        entry = "- [project:koan] fix bug"
        result = stamp_queued(entry)
        assert result.startswith(entry)
        assert "⏳(" in result
        # Verify timestamp format
        m = re.search(r"⏳\((\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\)", result)
        assert m is not None
        datetime.strptime(m.group(1), _TS_FORMAT)

    def test_uses_current_time(self):
        now = time.strftime(_TS_FORMAT)
        result = stamp_queued("- test")
        assert now in result


class TestStampStarted:
    def test_appends_timestamp(self):
        entry = "- [project:koan] fix bug ⏳(2026-02-12T04:15)"
        result = stamp_started(entry)
        assert "▶(" in result
        m = re.search(r"▶\((\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\)", result)
        assert m is not None

    def test_preserves_queued_timestamp(self):
        entry = "- fix bug ⏳(2026-02-12T04:15)"
        result = stamp_started(entry)
        assert "⏳(2026-02-12T04:15)" in result
        assert "▶(" in result


# ---------------------------------------------------------------------------
# extract_timestamps
# ---------------------------------------------------------------------------


class TestExtractTimestamps:
    @pytest.mark.parametrize("text, expected_queued, expected_started, expected_completed", [
        # Queued only
        ("- fix bug ⏳(2026-02-12T04:15)",
         datetime(2026, 2, 12, 4, 15), None, None),

        # Queued and started
        ("- fix bug ⏳(2026-02-12T04:15) ▶(2026-02-12T04:20)",
         datetime(2026, 2, 12, 4, 15), datetime(2026, 2, 12, 4, 20), None),

        # Full lifecycle (completed)
        ("- fix bug ⏳(2026-02-12T04:15) ▶(2026-02-12T04:20) ✅ (2026-02-12 04:30)",
         datetime(2026, 2, 12, 4, 15), datetime(2026, 2, 12, 4, 20), datetime(2026, 2, 12, 4, 30)),

        # Failed mission
        ("- fix bug ⏳(2026-02-12T04:15) ▶(2026-02-12T04:20) ❌ (2026-02-12 04:25)",
         datetime(2026, 2, 12, 4, 15), datetime(2026, 2, 12, 4, 20), datetime(2026, 2, 12, 4, 25)),

        # No timestamps
        ("- fix bug", None, None, None),

        # Legacy done format (no queued/started)
        ("- fix bug ✅ (2026-02-12 04:30)",
         None, None, datetime(2026, 2, 12, 4, 30)),
    ])
    def test_extract_timestamps(self, text, expected_queued, expected_started, expected_completed):
        ts = extract_timestamps(text)
        assert ts["queued"] == expected_queued
        assert ts["started"] == expected_started
        assert ts["completed"] == expected_completed

    def test_malformed_timestamp_returns_none(self):
        """Corrupted timestamps should not crash."""
        text = "- fix bug ⏳(not-a-date) ▶(also-bad)"
        ts = extract_timestamps(text)
        assert ts["queued"] is None
        assert ts["started"] is None


# ---------------------------------------------------------------------------
# format_duration — negative and edge cases
# ---------------------------------------------------------------------------


class TestFormatDurationEdgeCases:
    def test_negative_returns_less_than_1m(self):
        assert format_duration(-100) == "< 1m"


# ---------------------------------------------------------------------------
# mission_timing_display — negative elapsed
# ---------------------------------------------------------------------------


class TestMissionTimingNegativeElapsed:
    def test_negative_duration_returns_empty(self):
        """Timestamps out of order should not show negative times."""
        text = "- bug ⏳(2026-02-12T04:20) ▶(2026-02-12T04:15) ✅ (2026-02-12 04:10)"
        assert mission_timing_display(text) == ""

# ---------------------------------------------------------------------------


class TestFormatDuration:
    @pytest.mark.parametrize("seconds, expected", [
        (0, "< 1m"),
        (30, "< 1m"),
        (60, "1m"),
        (300, "5m"),
        (3600, "1h"),
        (5400, "1h 30m"),
    ])
    def test_format_duration(self, seconds, expected):
        assert format_duration(seconds) == expected


# ---------------------------------------------------------------------------
# mission_timing_display
# ---------------------------------------------------------------------------


class TestMissionTimingDisplay:
    def test_no_timestamps_returns_empty(self):
        assert mission_timing_display("- fix bug") == ""

    def test_queued_shows_waiting(self):
        now = datetime.now()
        queued = (now - timedelta(minutes=5)).strftime(_TS_FORMAT)
        text = f"- fix bug ⏳({queued})"
        display = mission_timing_display(text)
        assert "waiting" in display

    def test_started_shows_running(self):
        now = datetime.now()
        started = (now - timedelta(minutes=12)).strftime(_TS_FORMAT)
        text = f"- fix bug ▶({started})"
        display = mission_timing_display(text)
        assert "running" in display

    def test_completed_shows_took(self):
        text = "- fix bug ⏳(2026-02-12T04:00) ▶(2026-02-12T04:05) ✅ (2026-02-12 04:35)"
        display = mission_timing_display(text)
        assert "took 30m" in display
        assert "waited 5m" in display

    def test_completed_short_wait_omitted(self):
        """Wait time < 1m is not shown."""
        text = "- fix bug ⏳(2026-02-12T04:00) ▶(2026-02-12T04:00) ✅ (2026-02-12 04:30)"
        display = mission_timing_display(text)
        assert "took 30m" in display
        assert "waited" not in display

    def test_completed_without_queued(self):
        """Legacy missions without queued timestamp."""
        text = "- fix bug ▶(2026-02-12T04:05) ✅ (2026-02-12 04:35)"
        display = mission_timing_display(text)
        assert "took 30m" in display


# ---------------------------------------------------------------------------
# strip_timestamps
# ---------------------------------------------------------------------------


class TestStripTimestamps:
    @pytest.mark.parametrize("text, expected", [
        ("- fix bug ⏳(2026-02-12T04:15)", "- fix bug"),
        ("- fix bug ▶(2026-02-12T04:20)", "- fix bug"),
        ("- fix bug ⏳(2026-02-12T04:15) ▶(2026-02-12T04:20)", "- fix bug"),
        ("- fix bug", "- fix bug"),
    ])
    def test_strip_timestamps(self, text, expected):
        assert strip_timestamps(text) == expected

    def test_preserves_completion_marker(self):
        """Completion markers (✅/❌) should be preserved."""
        text = "- fix bug ⏳(2026-02-12T04:15) ✅ (2026-02-12 04:30)"
        result = strip_timestamps(text)
        assert "✅" in result
        assert "⏳" not in result


# ---------------------------------------------------------------------------
# insert_mission — queued timestamp integration
# ---------------------------------------------------------------------------


class TestInsertMissionTimestamp:
    def test_insert_adds_queued_timestamp(self):
        content = DEFAULT_SKELETON
        result = insert_mission(content, "- [project:koan] fix bug")
        assert "⏳(" in result
        # The entry should be in the pending section
        assert "fix bug" in result

    def test_insert_does_not_double_stamp(self):
        """If entry already has a queued timestamp, don't add another."""
        content = DEFAULT_SKELETON
        entry = "- fix bug ⏳(2026-02-12T04:00)"
        result = insert_mission(content, entry)
        assert result.count("⏳") == 1

    def test_urgent_insert_adds_timestamp(self):
        content = DEFAULT_SKELETON
        result = insert_mission(content, "- urgent fix", urgent=True)
        assert "⏳(" in result


# ---------------------------------------------------------------------------
# start_mission — started timestamp integration
# ---------------------------------------------------------------------------


class TestStartMissionTimestamp:
    def test_start_adds_started_timestamp(self):
        content = (
            "# Missions\n\n"
            "## Pending\n\n"
            "- fix bug ⏳(2026-02-12T04:15)\n\n"
            "## In Progress\n\n"
            "## Done\n"
        )
        result = start_mission(content, "fix bug")
        assert "▶(" in result
        # Should be in In Progress
        lines = result.splitlines()
        in_progress_idx = next(
            i for i, l in enumerate(lines) if "## In Progress" in l
        )
        done_idx = next(i for i, l in enumerate(lines) if "## Done" in l)
        for i in range(in_progress_idx + 1, done_idx):
            if "fix bug" in lines[i]:
                assert "▶(" in lines[i]
                break
        else:
            pytest.fail("Mission not found in In Progress section")

    def test_start_preserves_queued_timestamp(self):
        content = (
            "# Missions\n\n"
            "## Pending\n\n"
            "- fix bug ⏳(2026-02-12T04:15)\n\n"
            "## In Progress\n\n"
            "## Done\n"
        )
        result = start_mission(content, "fix bug")
        assert "⏳(2026-02-12T04:15)" in result
        assert "▶(" in result


# ---------------------------------------------------------------------------
# complete_mission — preserves all timestamps
# ---------------------------------------------------------------------------


class TestCompleteMissionTimestamps:
    def test_complete_preserves_lifecycle_timestamps(self):
        content = (
            "# Missions\n\n"
            "## Pending\n\n"
            "## In Progress\n\n"
            "- fix bug ⏳(2026-02-12T04:15) ▶(2026-02-12T04:20)\n\n"
            "## Done\n"
        )
        result = complete_mission(content, "fix bug")
        assert "⏳(2026-02-12T04:15)" in result
        assert "▶(2026-02-12T04:20)" in result
        assert "✅" in result

    def test_fail_preserves_lifecycle_timestamps(self):
        content = (
            "# Missions\n\n"
            "## Pending\n\n"
            "## In Progress\n\n"
            "- fix bug ⏳(2026-02-12T04:15) ▶(2026-02-12T04:20)\n\n"
            "## Done\n\n"
            "## Failed\n"
        )
        result = fail_mission(content, "fix bug")
        assert "⏳(2026-02-12T04:15)" in result
        assert "▶(2026-02-12T04:20)" in result
        assert "❌" in result


# ---------------------------------------------------------------------------
# Full lifecycle integration
# ---------------------------------------------------------------------------


class TestFullLifecycleTimestamps:
    @patch("app.missions.time.strftime")
    def test_full_lifecycle_tracking(self, mock_strftime):
        """Insert → Start → Complete preserves all timestamps."""
        # Phase 1: Insert (queued)
        mock_strftime.return_value = "2026-02-12T10:00"
        content = DEFAULT_SKELETON
        content = insert_mission(content, "- [project:koan] add feature")
        assert "⏳(2026-02-12T10:00)" in content

        # Phase 2: Start (started)
        mock_strftime.return_value = "2026-02-12T10:05"
        content = start_mission(content, "add feature")
        assert "⏳(2026-02-12T10:00)" in content
        assert "▶(2026-02-12T10:05)" in content

        # Phase 3: Complete
        mock_strftime.return_value = "2026-02-12 10:35"
        content = complete_mission(content, "add feature")
        assert "⏳(2026-02-12T10:00)" in content
        assert "▶(2026-02-12T10:05)" in content
        assert "✅ (2026-02-12 10:35)" in content

        # Verify we can extract all timestamps
        done_line = [
            l for l in content.splitlines() if "add feature" in l
        ][0]
        ts = extract_timestamps(done_line)
        assert ts["queued"] == datetime(2026, 2, 12, 10, 0)
        assert ts["started"] == datetime(2026, 2, 12, 10, 5)
        assert ts["completed"] == datetime(2026, 2, 12, 10, 35)

    def test_backward_compat_no_timestamps(self):
        """Legacy missions without timestamps still work correctly."""
        content = (
            "# Missions\n\n"
            "## Pending\n\n"
            "- [project:koan] old mission\n\n"
            "## In Progress\n\n"
            "## Done\n"
        )
        # Start should still work and add started timestamp
        result = start_mission(content, "old mission")
        assert "old mission" in result
        assert "▶(" in result

        # Complete should work
        result = complete_mission(result, "old mission")
        assert "✅" in result
