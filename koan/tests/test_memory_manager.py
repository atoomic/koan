"""Tests for memory_manager.py — scoped summary, compaction, learnings dedup."""

import pytest

from app.memory_manager import (
    parse_summary_sessions,
    scoped_summary,
    compact_summary,
    cleanup_learnings,
    run_cleanup,
    _extract_project_hint,
)


# ---------------------------------------------------------------------------
# _extract_project_hint
# ---------------------------------------------------------------------------

class TestExtractProjectHint:

    def test_parenthesized_french(self):
        assert _extract_project_hint("Session 1 (projet: koan) : blah") == "koan"

    def test_parenthesized_english(self):
        assert _extract_project_hint("Session 1 (project: koan) : blah") == "koan"

    def test_no_parens(self):
        assert _extract_project_hint("Session 1 projet:koan blah") == "koan"

    def test_case_insensitive(self):
        assert _extract_project_hint("Session 1 (Projet: Koan)") == "koan"

    def test_no_hint(self):
        assert _extract_project_hint("Session 1 : did some work") == ""

    def test_hyphenated_project(self):
        assert _extract_project_hint("(project: anantys-back)") == "anantys-back"


# ---------------------------------------------------------------------------
# parse_summary_sessions
# ---------------------------------------------------------------------------

class TestParseSummarySessions:

    def test_single_date_single_session(self):
        content = "# Summary\n\n## 2026-01-31\n\nSession 1 (projet: koan) : did stuff\n"
        sessions = parse_summary_sessions(content)
        assert len(sessions) == 1
        assert sessions[0][0] == "## 2026-01-31"
        assert "Session 1" in sessions[0][1]
        assert sessions[0][2] == "koan"

    def test_two_sessions_same_date(self):
        content = (
            "## 2026-02-01\n\n"
            "Session 1 (projet: koan) : A\n\n"
            "Session 2 (project: anantys-back) : B\n"
        )
        sessions = parse_summary_sessions(content)
        assert len(sessions) == 2
        assert sessions[0][2] == "koan"
        assert sessions[1][2] == "anantys-back"

    def test_sessions_across_dates(self):
        content = (
            "## 2026-01-31\n\nSession 1 : A\n\n"
            "## 2026-02-01\n\nSession 2 (projet: koan) : B\n"
        )
        sessions = parse_summary_sessions(content)
        assert len(sessions) == 2
        assert sessions[0][0] == "## 2026-01-31"
        assert sessions[1][0] == "## 2026-02-01"

    def test_empty_content(self):
        assert parse_summary_sessions("") == []

    def test_title_only(self):
        assert parse_summary_sessions("# Summary\n") == []

    def test_no_project_hint(self):
        content = "## 2026-01-31\n\nSession 1 : did stuff without tag\n"
        sessions = parse_summary_sessions(content)
        assert len(sessions) == 1
        assert sessions[0][2] == ""


# ---------------------------------------------------------------------------
# scoped_summary
# ---------------------------------------------------------------------------

class TestScopedSummary:

    def test_filters_by_project(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "summary.md").write_text(
            "# Summary\n\n## 2026-02-01\n\n"
            "Session 1 (projet: koan) : koan work\n\n"
            "Session 2 (project: anantys-back) : anantys work\n"
        )
        result = scoped_summary(str(tmp_path), "koan")
        assert "koan work" in result
        assert "anantys work" not in result

    def test_includes_untagged_sessions(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "summary.md").write_text(
            "## 2026-01-31\n\nSession 1 : old untagged work\n\n"
            "## 2026-02-01\n\nSession 2 (projet: koan) : koan work\n"
        )
        result = scoped_summary(str(tmp_path), "koan")
        assert "old untagged" in result
        assert "koan work" in result

    def test_missing_file_returns_empty(self, tmp_path):
        assert scoped_summary(str(tmp_path), "koan") == ""

    def test_preserves_title(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "summary.md").write_text(
            "# Résumé des sessions\n\n## 2026-02-01\n\nSession 1 (projet: koan) : work\n"
        )
        result = scoped_summary(str(tmp_path), "koan")
        assert result.startswith("# Résumé des sessions")


# ---------------------------------------------------------------------------
# compact_summary
# ---------------------------------------------------------------------------

class TestCompactSummary:

    def test_removes_old_sessions(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        lines = ["# Summary\n"]
        for i in range(1, 16):
            lines.append(f"\n## 2026-02-{i:02d}\n\nSession {i} (projet: koan) : work {i}\n")
        (mem / "summary.md").write_text("".join(lines))

        removed = compact_summary(str(tmp_path), max_sessions=5)
        assert removed == 10
        content = (mem / "summary.md").read_text()
        assert "Session 15" in content
        assert "Session 11" in content
        assert "Session 1 " not in content

    def test_no_compaction_needed(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "summary.md").write_text(
            "# Summary\n\n## 2026-02-01\n\nSession 1 : work\n"
        )
        assert compact_summary(str(tmp_path), max_sessions=10) == 0

    def test_missing_file(self, tmp_path):
        assert compact_summary(str(tmp_path)) == 0

    def test_exact_count_no_removal(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        lines = ["# Summary\n"]
        for i in range(1, 6):
            lines.append(f"\n## 2026-02-{i:02d}\n\nSession {i} : work\n")
        (mem / "summary.md").write_text("".join(lines))
        assert compact_summary(str(tmp_path), max_sessions=5) == 0


# ---------------------------------------------------------------------------
# cleanup_learnings
# ---------------------------------------------------------------------------

class TestCleanupLearnings:

    def _write_learnings(self, tmp_path, project, content):
        p = tmp_path / "memory" / "projects" / project
        p.mkdir(parents=True, exist_ok=True)
        (p / "learnings.md").write_text(content)
        return p / "learnings.md"

    def test_removes_duplicates(self, tmp_path):
        path = self._write_learnings(tmp_path, "koan",
            "# Learnings\n\n- fact A\n- fact B\n- fact A\n- fact C\n")
        removed = cleanup_learnings(str(tmp_path), "koan")
        assert removed == 1
        content = path.read_text()
        assert content.count("fact A") == 1
        assert "fact B" in content
        assert "fact C" in content

    def test_preserves_headers_and_blanks(self, tmp_path):
        path = self._write_learnings(tmp_path, "koan",
            "# Learnings\n\n## Section A\n\n- item\n\n## Section A\n\n- item\n")
        removed = cleanup_learnings(str(tmp_path), "koan")
        assert removed == 1
        content = path.read_text()
        # Headers are preserved even if duplicated
        assert content.count("## Section A") == 2

    def test_no_duplicates(self, tmp_path):
        self._write_learnings(tmp_path, "koan",
            "# Learnings\n\n- unique A\n- unique B\n")
        assert cleanup_learnings(str(tmp_path), "koan") == 0

    def test_missing_file(self, tmp_path):
        assert cleanup_learnings(str(tmp_path), "koan") == 0

    def test_empty_file(self, tmp_path):
        self._write_learnings(tmp_path, "koan", "")
        assert cleanup_learnings(str(tmp_path), "koan") == 0


# ---------------------------------------------------------------------------
# run_cleanup
# ---------------------------------------------------------------------------

class TestRunCleanup:

    def test_runs_all_tasks(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        # Summary with 12 sessions
        lines = ["# Summary\n"]
        for i in range(1, 13):
            lines.append(f"\n## 2026-02-{i:02d}\n\nSession {i} : work\n")
        (mem / "summary.md").write_text("".join(lines))

        # Learnings with dupes
        proj = mem / "projects" / "koan"
        proj.mkdir(parents=True)
        (proj / "learnings.md").write_text("# L\n\n- dup\n- dup\n- unique\n")

        stats = run_cleanup(str(tmp_path), max_sessions=5)
        assert stats["summary_compacted"] == 7
        assert stats["learnings_dedup_koan"] == 1

    def test_no_projects_dir(self, tmp_path):
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "summary.md").write_text("# Summary\n\n## 2026-02-01\n\nSession 1 : work\n")
        stats = run_cleanup(str(tmp_path))
        assert stats["summary_compacted"] == 0
