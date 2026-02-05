"""Tests for cost_tracker.py — Per-mission token cost tracking."""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app.cost_tracker import (
    _extract_tokens,
    _format_tokens,
    _load_history,
    _prune_old_entries,
    _save_history,
    get_cost_summary,
    record_mission_cost,
    COST_FILE,
    MAX_HISTORY_DAYS,
)


@pytest.fixture
def instance_dir(tmp_path):
    return tmp_path / "instance"


@pytest.fixture
def instance(instance_dir):
    instance_dir.mkdir()
    return instance_dir


@pytest.fixture
def claude_json(tmp_path):
    f = tmp_path / "claude_out.json"
    f.write_text(json.dumps({
        "result": "Done.",
        "input_tokens": 1500,
        "output_tokens": 500,
    }))
    return f


@pytest.fixture
def claude_json_nested(tmp_path):
    f = tmp_path / "claude_nested.json"
    f.write_text(json.dumps({
        "result": "Done.",
        "usage": {"input_tokens": 3000, "output_tokens": 1000},
    }))
    return f


@pytest.fixture
def claude_json_no_tokens(tmp_path):
    f = tmp_path / "claude_no_tokens.json"
    f.write_text(json.dumps({"result": "Hello."}))
    return f


@pytest.fixture
def claude_json_invalid(tmp_path):
    f = tmp_path / "claude_bad.json"
    f.write_text("not json at all")
    return f


class TestExtractTokens:
    def test_top_level_fields(self, claude_json):
        result = _extract_tokens(claude_json)
        assert result == {"input_tokens": 1500, "output_tokens": 500}

    def test_nested_usage(self, claude_json_nested):
        result = _extract_tokens(claude_json_nested)
        assert result == {"input_tokens": 3000, "output_tokens": 1000}

    def test_stats_fallback(self, tmp_path):
        f = tmp_path / "stats.json"
        f.write_text(json.dumps({
            "result": "ok",
            "stats": {"input_tokens": 100, "output_tokens": 50},
        }))
        result = _extract_tokens(f)
        assert result == {"input_tokens": 100, "output_tokens": 50}

    def test_no_tokens(self, claude_json_no_tokens):
        assert _extract_tokens(claude_json_no_tokens) is None

    def test_invalid_json(self, claude_json_invalid):
        assert _extract_tokens(claude_json_invalid) is None

    def test_missing_file(self, tmp_path):
        assert _extract_tokens(tmp_path / "nonexistent.json") is None


class TestFormatTokens:
    def test_small_number(self):
        assert _format_tokens(500) == "500"

    def test_thousands(self):
        assert _format_tokens(1500) == "1.5k"

    def test_exact_thousand(self):
        assert _format_tokens(1000) == "1.0k"

    def test_millions(self):
        assert _format_tokens(2_500_000) == "2.5M"

    def test_zero(self):
        assert _format_tokens(0) == "0"


class TestHistoryIO:
    def test_load_empty(self, instance):
        assert _load_history(instance) == []

    def test_save_and_load(self, instance):
        data = [{"timestamp": "2026-01-01T00:00:00", "project": "test", "total_tokens": 100}]
        _save_history(instance, data)
        assert _load_history(instance) == data

    def test_load_corrupt_json(self, instance):
        (instance / COST_FILE).write_text("not json")
        assert _load_history(instance) == []

    def test_prune_old(self):
        old = (datetime.now() - timedelta(days=MAX_HISTORY_DAYS + 1)).isoformat()
        recent = datetime.now().isoformat()
        history = [
            {"timestamp": old, "project": "old"},
            {"timestamp": recent, "project": "new"},
        ]
        pruned = _prune_old_entries(history)
        assert len(pruned) == 1
        assert pruned[0]["project"] == "new"


class TestRecordMissionCost:
    def test_records_top_level(self, claude_json, instance):
        record_mission_cost(claude_json, instance, "koan", "fix tests")
        history = _load_history(instance)
        assert len(history) == 1
        entry = history[0]
        assert entry["project"] == "koan"
        assert entry["mission"] == "fix tests"
        assert entry["input_tokens"] == 1500
        assert entry["output_tokens"] == 500
        assert entry["total_tokens"] == 2000
        assert "timestamp" in entry

    def test_records_nested(self, claude_json_nested, instance):
        record_mission_cost(claude_json_nested, instance, "webapp")
        history = _load_history(instance)
        assert len(history) == 1
        assert history[0]["total_tokens"] == 4000
        assert history[0]["mission"] == "(autonomous)"

    def test_no_tokens_no_record(self, claude_json_no_tokens, instance):
        record_mission_cost(claude_json_no_tokens, instance, "koan", "test")
        assert _load_history(instance) == []

    def test_invalid_json_no_record(self, claude_json_invalid, instance):
        record_mission_cost(claude_json_invalid, instance, "koan", "test")
        assert _load_history(instance) == []

    def test_multiple_records_accumulate(self, claude_json, instance):
        record_mission_cost(claude_json, instance, "koan", "mission 1")
        record_mission_cost(claude_json, instance, "koan", "mission 2")
        history = _load_history(instance)
        assert len(history) == 2

    def test_prunes_old_on_record(self, claude_json, instance):
        old = (datetime.now() - timedelta(days=MAX_HISTORY_DAYS + 1)).isoformat()
        _save_history(instance, [
            {"timestamp": old, "project": "old", "mission": "old", "input_tokens": 0,
             "output_tokens": 0, "total_tokens": 0},
        ])
        record_mission_cost(claude_json, instance, "koan", "new")
        history = _load_history(instance)
        assert len(history) == 1
        assert history[0]["mission"] == "new"


class TestGetCostSummary:
    def _make_entry(self, project="koan", mission="test mission", total=2000,
                    inp=1500, out=500, days_ago=0):
        ts = (datetime.now() - timedelta(days=days_ago)).isoformat()
        return {
            "timestamp": ts,
            "project": project,
            "mission": mission,
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens": total,
        }

    def test_empty_history(self, instance):
        result = get_cost_summary(instance)
        assert "No cost data yet" in result

    def test_no_recent_data(self, instance):
        _save_history(instance, [self._make_entry(days_ago=10)])
        result = get_cost_summary(instance, days=3)
        assert "No cost data" in result
        assert "last 3 days" in result

    def test_today_breakdown(self, instance):
        _save_history(instance, [
            self._make_entry(mission="fix auth bug", total=3000, inp=2000, out=1000),
            self._make_entry(mission="add tests", total=1500, inp=1000, out=500),
        ])
        result = get_cost_summary(instance)
        assert "fix auth bug" in result
        assert "add tests" in result
        assert "3.0k total" in result
        assert "1.5k total" in result
        assert "2 runs" in result

    def test_project_filter(self, instance):
        _save_history(instance, [
            self._make_entry(project="koan", mission="koan task"),
            self._make_entry(project="webapp", mission="webapp task"),
        ])
        result = get_cost_summary(instance, project="koan")
        assert "koan task" in result
        assert "webapp task" not in result
        assert "(koan)" in result

    def test_multi_project_summary(self, instance):
        _save_history(instance, [
            self._make_entry(project="koan", total=2000),
            self._make_entry(project="webapp", total=3000),
        ])
        result = get_cost_summary(instance)
        assert "By project:" in result
        assert "koan:" in result
        assert "webapp:" in result

    def test_long_mission_truncated(self, instance):
        long_name = "x" * 60
        _save_history(instance, [self._make_entry(mission=long_name)])
        result = get_cost_summary(instance)
        assert "..." in result
        assert long_name not in result

    def test_days_parameter(self, instance):
        _save_history(instance, [
            self._make_entry(days_ago=0, mission="today"),
            self._make_entry(days_ago=5, mission="5 days ago"),
            self._make_entry(days_ago=20, mission="20 days ago"),
        ])
        result = get_cost_summary(instance, days=7)
        assert "today" in result
        assert "5 days ago" in result
        assert "20 days ago" not in result
        assert "2 runs" in result

    def test_total_tokens(self, instance):
        _save_history(instance, [
            self._make_entry(total=2000),
            self._make_entry(total=3000),
        ])
        result = get_cost_summary(instance)
        assert "5.0k tokens" in result


class TestCLI:
    def test_record_command(self, claude_json, instance, monkeypatch):
        import app.cost_tracker as mod
        monkeypatch.setattr("sys.argv", [
            "cost_tracker.py", "record",
            str(claude_json), str(instance), "koan", "test mission",
        ])
        mod.main()
        history = _load_history(instance)
        assert len(history) == 1
        assert history[0]["mission"] == "test mission"

    def test_record_no_mission(self, claude_json, instance, monkeypatch):
        import app.cost_tracker as mod
        monkeypatch.setattr("sys.argv", [
            "cost_tracker.py", "record",
            str(claude_json), str(instance), "koan",
        ])
        mod.main()
        history = _load_history(instance)
        assert len(history) == 1
        assert history[0]["mission"] == "(autonomous)"

    def test_unknown_command(self, monkeypatch):
        import app.cost_tracker as mod
        monkeypatch.setattr("sys.argv", ["cost_tracker.py", "unknown"])
        with pytest.raises(SystemExit):
            mod.main()

    def test_missing_args(self, monkeypatch):
        import app.cost_tracker as mod
        monkeypatch.setattr("sys.argv", ["cost_tracker.py", "record"])
        with pytest.raises(SystemExit):
            mod.main()
