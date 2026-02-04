"""Tests for pr_review.py — PR URL parsing, context fetching, prompt building, workflow."""

import json
import subprocess
from unittest.mock import patch, MagicMock, call

import pytest

from app.pr_review import (
    parse_pr_url,
    fetch_pr_context,
    build_pr_prompt,
    run_pr_review,
    _build_summary,
    _gh,
    _run_git,
    _truncate,
)


# ---------------------------------------------------------------------------
# parse_pr_url
# ---------------------------------------------------------------------------

class TestParsePrUrl:
    def test_standard_url(self):
        owner, repo, num = parse_pr_url("https://github.com/sukria/koan/pull/29")
        assert owner == "sukria"
        assert repo == "koan"
        assert num == "29"

    def test_url_with_fragment(self):
        owner, repo, num = parse_pr_url(
            "https://github.com/sukria/koan/pull/29#pullrequestreview-123"
        )
        assert owner == "sukria"
        assert repo == "koan"
        assert num == "29"

    def test_url_with_trailing_whitespace(self):
        owner, repo, num = parse_pr_url("  https://github.com/foo/bar/pull/1  ")
        assert owner == "foo"
        assert repo == "bar"
        assert num == "1"

    def test_http_url(self):
        owner, repo, num = parse_pr_url("http://github.com/a/b/pull/99")
        assert owner == "a"
        assert repo == "b"
        assert num == "99"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Invalid PR URL"):
            parse_pr_url("https://github.com/sukria/koan/issues/29")

    def test_not_github_raises(self):
        with pytest.raises(ValueError, match="Invalid PR URL"):
            parse_pr_url("https://gitlab.com/sukria/koan/pull/29")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Invalid PR URL"):
            parse_pr_url("")

    def test_no_pr_number_raises(self):
        with pytest.raises(ValueError, match="Invalid PR URL"):
            parse_pr_url("https://github.com/sukria/koan/pull/")


# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------

class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("hello", 100) == "hello"

    def test_exact_length_unchanged(self):
        assert _truncate("12345", 5) == "12345"

    def test_long_text_truncated(self):
        result = _truncate("a" * 20, 10)
        assert len(result) < 30
        assert "truncated" in result

    def test_empty_string(self):
        assert _truncate("", 100) == ""


# ---------------------------------------------------------------------------
# _gh
# ---------------------------------------------------------------------------

class TestGh:
    @patch("app.pr_review.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="output\n")
        result = _gh(["gh", "pr", "view", "1"])
        assert result == "output"

    @patch("app.pr_review.subprocess.run")
    def test_failure_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="not found")
        with pytest.raises(RuntimeError, match="gh command failed"):
            _gh(["gh", "pr", "view", "999"])


# ---------------------------------------------------------------------------
# _run_git
# ---------------------------------------------------------------------------

class TestRunGit:
    @patch("app.pr_review.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n")
        result = _run_git(["git", "status"])
        assert result == "ok"

    @patch("app.pr_review.subprocess.run")
    def test_failure_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        with pytest.raises(RuntimeError, match="git failed"):
            _run_git(["git", "checkout", "nope"])

    @patch("app.pr_review.subprocess.run")
    def test_cwd_passed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        _run_git(["git", "status"], cwd="/tmp/test")
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["cwd"] == "/tmp/test"


# ---------------------------------------------------------------------------
# _build_summary
# ---------------------------------------------------------------------------

class TestBuildSummary:
    def test_no_changes(self):
        result = _build_summary("some output", has_changes=False)
        assert "No code changes" in result

    def test_with_changes(self):
        result = _build_summary("Fixed the bug\nAll tests pass", has_changes=True)
        assert "Changes made" in result
        assert "Fixed the bug" in result

    def test_empty_output(self):
        result = _build_summary("", has_changes=True)
        assert "Changes were made" in result

    def test_long_output_truncated(self):
        long_output = "line\n" * 200
        result = _build_summary(long_output, has_changes=True)
        assert len(result) < 600


# ---------------------------------------------------------------------------
# fetch_pr_context
# ---------------------------------------------------------------------------

class TestFetchPrContext:
    @patch("app.pr_review._gh")
    def test_fetches_all_data(self, mock_gh):
        pr_meta = json.dumps({
            "title": "Add feature",
            "body": "Some description",
            "headRefName": "koan/feature",
            "baseRefName": "main",
            "state": "OPEN",
            "author": {"login": "dev"},
            "url": "https://github.com/o/r/pull/1",
        })
        mock_gh.side_effect = [
            pr_meta,           # PR metadata
            "diff content",    # diff
            "comment1",        # review comments
            "review1",         # reviews
            "discussion1",     # issue comments
        ]

        ctx = fetch_pr_context("owner", "repo", "1")
        assert ctx["title"] == "Add feature"
        assert ctx["branch"] == "koan/feature"
        assert ctx["base"] == "main"
        assert ctx["diff"] == "diff content"
        assert ctx["review_comments"] == "comment1"
        assert ctx["reviews"] == "review1"
        assert ctx["issue_comments"] == "discussion1"
        assert mock_gh.call_count == 5

    @patch("app.pr_review._gh")
    def test_handles_invalid_json(self, mock_gh):
        mock_gh.side_effect = ["not json", "", "", "", ""]
        ctx = fetch_pr_context("o", "r", "1")
        assert ctx["title"] == ""
        assert ctx["branch"] == ""


# ---------------------------------------------------------------------------
# build_pr_prompt
# ---------------------------------------------------------------------------

class TestBuildPrPrompt:
    def test_builds_prompt(self):
        ctx = {
            "title": "Test PR",
            "body": "Description",
            "branch": "fix-branch",
            "base": "main",
            "diff": "+some code",
            "review_comments": "fix this",
            "reviews": "needs work",
            "issue_comments": "thread",
        }
        prompt = build_pr_prompt(ctx)
        assert "Test PR" in prompt
        assert "fix-branch" in prompt
        assert "+some code" in prompt
        assert "fix this" in prompt
        assert "needs work" in prompt


# ---------------------------------------------------------------------------
# run_pr_review (integration-level with mocks)
# ---------------------------------------------------------------------------

class TestRunPrReview:
    @patch("app.pr_review.send_telegram")
    @patch("app.pr_review._gh")
    @patch("app.pr_review._run_git")
    @patch("app.pr_review.subprocess.run")
    @patch("app.pr_review.get_model_config")
    @patch("app.pr_review.build_claude_flags")
    def test_full_workflow_success(
        self, mock_flags, mock_models, mock_subproc, mock_git, mock_gh, mock_tg
    ):
        # Setup
        mock_flags.return_value = []
        mock_models.return_value = {"mission": "", "fallback": "sonnet"}

        pr_meta = json.dumps({
            "title": "Fix bug",
            "body": "Fixes #10",
            "headRefName": "koan/fix-bug",
            "baseRefName": "main",
            "state": "OPEN",
            "author": {"login": "dev"},
            "url": "https://github.com/o/r/pull/1",
        })
        mock_gh.side_effect = [
            pr_meta, "diff", "comments", "reviews", "thread",  # fetch_pr_context
            "",  # final comment
        ]

        # Claude returns success
        mock_subproc.side_effect = [
            MagicMock(returncode=0, stdout="Fixed the issue", stderr=""),  # claude
            MagicMock(returncode=0, stdout="M file.py\n"),  # git status --porcelain
        ]

        success, summary = run_pr_review("o", "r", "1", "/tmp/project")
        assert success is True
        assert "Fixed the issue" in summary or "Changes" in summary

    @patch("app.pr_review.send_telegram")
    @patch("app.pr_review.fetch_pr_context")
    def test_no_branch_fails(self, mock_fetch, mock_tg):
        mock_fetch.return_value = {
            "title": "X", "body": "", "branch": "", "base": "main",
            "state": "OPEN", "author": "", "url": "",
            "diff": "", "review_comments": "", "reviews": "", "issue_comments": "",
        }
        success, summary = run_pr_review("o", "r", "1", "/tmp/p")
        assert success is False
        assert "branch" in summary.lower()

    @patch("app.pr_review.send_telegram")
    @patch("app.pr_review.fetch_pr_context")
    def test_fetch_error_fails(self, mock_fetch, mock_tg):
        mock_fetch.side_effect = RuntimeError("API error")
        success, summary = run_pr_review("o", "r", "1", "/tmp/p")
        assert success is False
        assert "Failed to fetch" in summary
