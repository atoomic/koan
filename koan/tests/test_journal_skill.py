"""Tests for the journal skill handler (/log command)."""

import importlib.util
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


def _load_handler():
    """Load the journal skill handler module."""
    handler_path = (
        Path(__file__).parent.parent / "skills" / "core" / "journal" / "handler.py"
    )
    spec = importlib.util.spec_from_file_location("journal_handler", str(handler_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_ctx(tmp_path, args=""):
    """Create a minimal SkillContext for testing."""
    from app.skills import SkillContext

    return SkillContext(koan_root=tmp_path, instance_dir=tmp_path, args=args)


class TestReadPendingProgress:
    """Tests for _read_pending_progress helper."""

    def test_no_pending_file(self, tmp_path):
        mod = _load_handler()
        (tmp_path / "journal").mkdir()
        result = mod._read_pending_progress(tmp_path)
        assert result is None

    def test_pending_without_separator(self, tmp_path):
        mod = _load_handler()
        pending = tmp_path / "journal" / "pending.md"
        pending.parent.mkdir(parents=True)
        pending.write_text("# Mission\nSome content without separator")
        result = mod._read_pending_progress(tmp_path)
        assert result is None

    def test_pending_with_empty_progress(self, tmp_path):
        mod = _load_handler()
        pending = tmp_path / "journal" / "pending.md"
        pending.parent.mkdir(parents=True)
        pending.write_text("# Mission\n---\n\n  \n")
        result = mod._read_pending_progress(tmp_path)
        assert result is None

    def test_pending_with_progress_lines(self, tmp_path):
        mod = _load_handler()
        pending = tmp_path / "journal" / "pending.md"
        pending.parent.mkdir(parents=True)
        pending.write_text(
            "# Mission\n---\n09:00 — Reading code\n09:05 — Writing tests"
        )
        result = mod._read_pending_progress(tmp_path)
        assert result is not None
        assert "Live progress" in result
        assert "Reading code" in result
        assert "Writing tests" in result

    def test_pending_max_lines(self, tmp_path):
        mod = _load_handler()
        pending = tmp_path / "journal" / "pending.md"
        pending.parent.mkdir(parents=True)
        lines = "\n".join(f"09:{i:02d} — Step {i}" for i in range(10))
        pending.write_text(f"# Mission\n---\n{lines}")
        result = mod._read_pending_progress(tmp_path, max_lines=3)
        assert "Step 7" in result
        assert "Step 8" in result
        assert "Step 9" in result
        assert "Step 0" not in result


class TestHandleLogLayout:
    """Tests for /log output layout — Live Progress at the bottom."""

    def test_progress_appears_after_journal(self, tmp_path):
        """Live progress section should be at the bottom, after journal content."""
        mod = _load_handler()
        today = date.today().strftime("%Y-%m-%d")
        journal_dir = tmp_path / "journal" / today
        journal_dir.mkdir(parents=True)
        (journal_dir / "koan.md").write_text("## Session 101\nJournal content here.")

        pending = tmp_path / "journal" / "pending.md"
        pending.write_text("# Mission\n---\n10:00 — Working on stuff")

        ctx = _make_ctx(tmp_path, args="koan")
        with patch.object(mod, "get_latest_journal", create=True):
            result = mod.handle(ctx)

        journal_pos = result.find("Journal content")
        progress_pos = result.find("Live progress")
        assert journal_pos != -1, "Journal content should be in output"
        assert progress_pos != -1, "Live progress should be in output"
        assert journal_pos < progress_pos, (
            "Journal content should appear BEFORE Live progress"
        )

    def test_no_progress_shows_journal_only(self, tmp_path):
        """When no pending.md exists, only journal is returned."""
        mod = _load_handler()
        today = date.today().strftime("%Y-%m-%d")
        journal_dir = tmp_path / "journal" / today
        journal_dir.mkdir(parents=True)
        (journal_dir / "koan.md").write_text("Just journal content.")

        ctx = _make_ctx(tmp_path, args="koan")
        result = mod.handle(ctx)
        assert "Just journal content" in result
        assert "Live progress" not in result

    def test_yesterday_never_shows_progress(self, tmp_path):
        """Progress is only for today — /log yesterday should not include it."""
        mod = _load_handler()
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        journal_dir = tmp_path / "journal" / yesterday
        journal_dir.mkdir(parents=True)
        (journal_dir / "koan.md").write_text("Yesterday's work.")

        pending = tmp_path / "journal" / "pending.md"
        pending.write_text("# Mission\n---\n10:00 — Current work")

        ctx = _make_ctx(tmp_path, args="koan yesterday")
        result = mod.handle(ctx)
        assert "Yesterday's work" in result
        assert "Live progress" not in result

    def test_date_arg_never_shows_progress(self, tmp_path):
        """Progress should not appear when a specific date is given."""
        mod = _load_handler()
        journal_dir = tmp_path / "journal" / "2026-01-15"
        journal_dir.mkdir(parents=True)
        (journal_dir / "koan.md").write_text("Old journal.")

        pending = tmp_path / "journal" / "pending.md"
        pending.write_text("# Mission\n---\n10:00 — Current work")

        ctx = _make_ctx(tmp_path, args="koan 2026-01-15")
        result = mod.handle(ctx)
        assert "Old journal" in result
        assert "Live progress" not in result

    def test_progress_at_bottom_with_all_projects(self, tmp_path):
        """Progress at bottom also works with no project filter."""
        mod = _load_handler()
        today = date.today().strftime("%Y-%m-%d")
        journal_dir = tmp_path / "journal" / today
        journal_dir.mkdir(parents=True)
        (journal_dir / "koan.md").write_text("Koan stuff")
        (journal_dir / "web-app.md").write_text("Web stuff")

        pending = tmp_path / "journal" / "pending.md"
        pending.write_text("# Mission\n---\n10:00 — Doing things")

        ctx = _make_ctx(tmp_path)
        result = mod.handle(ctx)

        journal_pos = result.find("Journal")  # header from get_latest_journal
        progress_pos = result.find("Live progress")
        assert progress_pos != -1, "Live progress should be present"
        # Progress should be after journal content
        koan_pos = result.find("Koan stuff")
        assert koan_pos < progress_pos, (
            "Journal content should be before Live progress"
        )

    def test_no_journal_with_progress(self, tmp_path):
        """When no journal exists but progress does, both appear."""
        mod = _load_handler()
        (tmp_path / "journal").mkdir(parents=True)

        pending = tmp_path / "journal" / "pending.md"
        pending.write_text("# Mission\n---\n10:00 — Starting fresh")

        ctx = _make_ctx(tmp_path, args="koan")
        result = mod.handle(ctx)
        assert "No journal" in result
        assert "Live progress" in result
        # Even with "no journal" message, progress should come after
        no_journal_pos = result.find("No journal")
        progress_pos = result.find("Live progress")
        assert no_journal_pos < progress_pos


class TestHandleLogArgs:
    """Tests for argument parsing."""

    def test_date_as_first_arg(self, tmp_path):
        mod = _load_handler()
        journal_dir = tmp_path / "journal" / "2026-02-01"
        journal_dir.mkdir(parents=True)
        (journal_dir / "koan.md").write_text("Feb 1 work")

        ctx = _make_ctx(tmp_path, args="2026-02-01")
        result = mod.handle(ctx)
        assert "Feb 1 work" in result

    def test_project_and_date(self, tmp_path):
        mod = _load_handler()
        journal_dir = tmp_path / "journal" / "2026-02-01"
        journal_dir.mkdir(parents=True)
        (journal_dir / "koan.md").write_text("Feb 1 koan work")

        ctx = _make_ctx(tmp_path, args="koan 2026-02-01")
        result = mod.handle(ctx)
        assert "Feb 1 koan work" in result

    def test_empty_args(self, tmp_path):
        mod = _load_handler()
        today = date.today().strftime("%Y-%m-%d")
        journal_dir = tmp_path / "journal" / today
        journal_dir.mkdir(parents=True)
        (journal_dir / "koan.md").write_text("Today's work")

        ctx = _make_ctx(tmp_path)
        result = mod.handle(ctx)
        assert "Today's work" in result
