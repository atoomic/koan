"""Tests for x_content.py — X (Twitter) content screening."""

import pytest

from app.x_content import screen_content, sanitize_for_tweet, reset_project_cache


@pytest.fixture(autouse=True)
def clean_cache():
    reset_project_cache()
    yield
    reset_project_cache()


# ---------------------------------------------------------------------------
# screen_content — allowed
# ---------------------------------------------------------------------------

class TestScreenContentAllowed:
    def test_simple_koan(self):
        ok, _ = screen_content("If the test passes but nothing changes, was it really a test?")
        assert ok is True

    def test_philosophical_text(self):
        ok, _ = screen_content("The agent that knows when to stop is wiser than the one that never starts.")
        assert ok is True

    def test_generic_programming_insight(self):
        ok, _ = screen_content("Three similar lines of code is better than a premature abstraction.")
        assert ok is True

    def test_short_tweet(self):
        ok, _ = screen_content("Hello world.")
        assert ok is True

    def test_emoji_tweet(self):
        ok, _ = screen_content("Session 88. Still learning. Still building.")
        assert ok is True

    def test_exactly_280_allowed(self):
        # Use realistic text (repeated single chars trigger base64 detection)
        text = ("The best code is the code you don't write. " * 7)[:280]
        ok, _ = screen_content(text)
        assert ok is True


# ---------------------------------------------------------------------------
# screen_content — blocked
# ---------------------------------------------------------------------------

class TestScreenContentBlocked:
    def test_empty_content(self):
        ok, reason = screen_content("")
        assert ok is False
        assert "Empty" in reason

    def test_too_long(self):
        ok, reason = screen_content("a" * 281)
        assert ok is False
        assert "Too long" in reason

    def test_github_token(self):
        ok, reason = screen_content("Check this ghp_" + "A" * 36)
        assert ok is False
        assert "GitHub token" in reason

    def test_api_key(self):
        ok, reason = screen_content("Key is sk-" + "a" * 30)
        assert ok is False
        assert "API key" in reason

    def test_aws_key(self):
        ok, reason = screen_content("AKIA" + "A" * 16 + " found")
        assert ok is False
        assert "AWS" in reason

    def test_slack_token(self):
        ok, reason = screen_content("Token: xoxb-" + "0" * 20)
        assert ok is False
        assert "Slack token" in reason

    def test_file_path_unix(self):
        ok, reason = screen_content("Found at /Users/nicolas/workspace/koan")
        assert ok is False
        assert "File path" in reason

    def test_file_path_home(self):
        ok, reason = screen_content("Check /home/user/.ssh/id_rsa")
        assert ok is False
        assert "File path" in reason

    def test_code_block(self):
        ok, reason = screen_content("```python\ndef foo(): pass\n```")
        assert ok is False
        assert "Code block" in reason

    def test_python_function(self):
        ok, reason = screen_content("def handle_message(text):")
        assert ok is False
        assert "Python function" in reason

    def test_class_definition(self):
        ok, reason = screen_content("class MyHandler(Base):")
        assert ok is False
        assert "Class definition" in reason

    def test_import_statement(self):
        ok, reason = screen_content("import subprocess")
        assert ok is False
        assert "Import statement" in reason

    def test_from_import(self):
        ok, reason = screen_content("from pathlib import Path")
        assert ok is False
        assert "import" in reason.lower()

    def test_env_var_assignment(self):
        ok, reason = screen_content("Set DEBUG_MODE=true to enable")
        assert ok is False
        assert "Environment variable" in reason

    def test_localhost_url(self):
        ok, reason = screen_content("Check http://localhost:5001/status")
        assert ok is False
        assert "Local URL" in reason

    def test_ip_url(self):
        ok, reason = screen_content("API at https://192.168.1.100:8080/api")
        assert ok is False
        assert "IP-based URL" in reason

    def test_repo_reference(self):
        ok, reason = screen_content("Check acme/widgets for details")
        assert ok is False
        assert "repo reference" in reason

    def test_jwt_like_token(self):
        part1 = "A" * 25
        part2 = "B" * 25
        part3 = "C" * 25
        ok, reason = screen_content(f"Token: {part1}.{part2}.{part3}")
        assert ok is False
        assert "JWT" in reason


class TestScreenContentEdgeCases:
    def test_allows_common_slash_patterns(self):
        # "AI/ML" should be allowed
        ok, _ = screen_content("Exploring the AI/ML space today.")
        assert ok is True

    def test_project_name_detection(self, monkeypatch):
        monkeypatch.setenv("KOAN_PROJECTS", "myproject:/path/to/it")
        reset_project_cache()
        ok, reason = screen_content("Working on myproject today")
        assert ok is False
        assert "project name" in reason


# ---------------------------------------------------------------------------
# sanitize_for_tweet
# ---------------------------------------------------------------------------

class TestSanitizeForTweet:
    def test_strips_markdown_bold(self):
        result = sanitize_for_tweet("This is **bold** text")
        assert result == "This is bold text"

    def test_strips_markdown_italic(self):
        result = sanitize_for_tweet("This is *italic* text")
        assert result == "This is italic text"

    def test_strips_markdown_headers(self):
        result = sanitize_for_tweet("## Section Title")
        assert result == "Section Title"

    def test_strips_markdown_links(self):
        result = sanitize_for_tweet("Check [this link](https://example.com)")
        assert result == "Check this link"

    def test_collapses_whitespace(self):
        result = sanitize_for_tweet("Hello   world\n\nnew paragraph")
        assert result == "Hello world new paragraph"

    def test_truncates_to_280(self):
        long_text = "x" * 300
        result = sanitize_for_tweet(long_text)
        assert len(result) <= 280
        assert result.endswith("...")

    def test_preserves_short_text(self):
        result = sanitize_for_tweet("Hello world")
        assert result == "Hello world"
