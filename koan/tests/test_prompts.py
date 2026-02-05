"""Tests for prompts.py — system prompt template loader."""

import pytest
from pathlib import Path

from app.prompts import load_prompt, PROMPT_DIR


class TestLoadPrompt:
    """Tests for load_prompt()."""

    def test_load_existing_prompt(self):
        """Should load a known prompt template."""
        result = load_prompt("chat", SOUL="test soul", TOOLS_DESC="", PREFS="",
                             SUMMARY="", JOURNAL="", MISSIONS="")
        assert "test soul" in result
        assert "{SOUL}" not in result

    def test_placeholder_substitution(self):
        """Should replace all provided placeholders."""
        result = load_prompt("chat", SOUL="SOUL_VAL", TOOLS_DESC="TOOLS_VAL",
                             PREFS="PREFS_VAL", SUMMARY="SUM_VAL",
                             JOURNAL="JOURNAL_VAL", MISSIONS="MISS_VAL")
        assert "SOUL_VAL" in result
        assert "TOOLS_VAL" in result
        assert "PREFS_VAL" in result
        assert "{SOUL}" not in result
        assert "{TOOLS_DESC}" not in result

    def test_missing_prompt_raises(self):
        """Should raise FileNotFoundError for nonexistent prompt."""
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent-prompt-xyz")

    def test_no_kwargs_leaves_placeholders(self):
        """Without kwargs, placeholders remain in the template."""
        result = load_prompt("chat")
        assert "{SOUL}" in result

    def test_prompt_dir_exists(self):
        """PROMPT_DIR should point to the system-prompts directory."""
        assert PROMPT_DIR.exists()
        assert PROMPT_DIR.is_dir()
        assert (PROMPT_DIR / "chat.md").exists()

    def test_all_known_prompts_loadable(self):
        """All .md files in system-prompts/ should be loadable."""
        for md_file in PROMPT_DIR.glob("*.md"):
            name = md_file.stem
            result = load_prompt(name)
            assert isinstance(result, str)
            assert len(result) > 0
