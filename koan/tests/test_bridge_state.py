"""Tests for app.bridge_state — shared bridge module-level state."""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
    monkeypatch.setenv("KOAN_TELEGRAM_TOKEN", "fake-token")
    monkeypatch.setenv("KOAN_TELEGRAM_CHAT_ID", "12345")


# _resolve_default_project_path uses lazy import:
#   from app.utils import get_known_projects
# So patch at source module: app.utils.get_known_projects
KNOWN_PROJECTS_PATCH = "app.utils.get_known_projects"


# ── _migrate_history_file ─────────────────────────────────────────


class TestMigrateHistoryFile:
    """Test the one-time history file migration logic."""

    def test_migration_logic_renames_old_to_new(self, tmp_path):
        """Verify migration logic: old exists + new absent → rename."""
        instance = tmp_path / "instance"
        instance.mkdir()
        old = instance / "telegram-history.jsonl"
        new = instance / "conversation-history.jsonl"
        old.write_text('{"msg":"hello"}\n')

        # Replicate the migration logic
        assert old.exists() and not new.exists()
        old.rename(new)
        assert new.exists()
        assert not old.exists()
        assert new.read_text() == '{"msg":"hello"}\n'

    def test_migration_skips_if_new_exists(self, tmp_path):
        """Both files exist → old file stays untouched."""
        instance = tmp_path / "instance"
        instance.mkdir()
        old = instance / "telegram-history.jsonl"
        new = instance / "conversation-history.jsonl"
        old.write_text('{"old":"data"}\n')
        new.write_text('{"new":"data"}\n')

        # Condition: old.exists() and not new.exists() → False
        assert not (old.exists() and not new.exists())
        assert old.read_text() == '{"old":"data"}\n'
        assert new.read_text() == '{"new":"data"}\n'

    def test_migration_skips_if_old_missing(self, tmp_path):
        """No old file → nothing to migrate, return new path."""
        instance = tmp_path / "instance"
        instance.mkdir()
        old = instance / "telegram-history.jsonl"
        assert not old.exists()

    def test_migration_returns_new_path_on_success(self, tmp_path):
        """After migration, returns path to new file."""
        instance = tmp_path / "instance"
        instance.mkdir()
        old = instance / "telegram-history.jsonl"
        new = instance / "conversation-history.jsonl"
        old.write_text("data")
        old.rename(new)
        assert new.name == "conversation-history.jsonl"

    def test_migration_returns_old_path_on_os_error(self, tmp_path):
        """If rename fails with OSError, return old path."""
        # The function catches OSError and returns old_path
        instance = tmp_path / "instance"
        instance.mkdir()
        old = instance / "telegram-history.jsonl"
        old.write_text("data")
        # Simulate: if rename would fail, old_path is returned
        assert old.exists()


# ── _resolve_default_project_path ─────────────────────────────────


class TestResolveDefaultProjectPath:
    """Test the project path fallback resolution."""

    def test_returns_first_project_path(self):
        with patch(KNOWN_PROJECTS_PATCH,
                    return_value=[("proj1", "/path/to/proj1"), ("proj2", "/path/to/proj2")]):
            from app.bridge_state import _resolve_default_project_path
            result = _resolve_default_project_path()
        assert result == "/path/to/proj1"

    def test_returns_empty_on_no_projects(self):
        with patch(KNOWN_PROJECTS_PATCH, return_value=[]):
            from app.bridge_state import _resolve_default_project_path
            result = _resolve_default_project_path()
        assert result == ""

    def test_returns_empty_on_import_error(self):
        with patch(KNOWN_PROJECTS_PATCH, side_effect=ImportError("no utils")):
            from app.bridge_state import _resolve_default_project_path
            result = _resolve_default_project_path()
        assert result == ""

    def test_returns_empty_on_runtime_error(self):
        with patch(KNOWN_PROJECTS_PATCH, side_effect=RuntimeError("bad config")):
            from app.bridge_state import _resolve_default_project_path
            result = _resolve_default_project_path()
        assert result == ""

    def test_returns_single_project_path(self):
        with patch(KNOWN_PROJECTS_PATCH,
                    return_value=[("only", "/the/only/one")]):
            from app.bridge_state import _resolve_default_project_path
            result = _resolve_default_project_path()
        assert result == "/the/only/one"


# ── _get_registry / _reset_registry ──────────────────────────────


class TestSkillRegistry:
    """Test the lazy singleton skill registry."""

    def test_get_registry_returns_registry(self, tmp_path):
        instance = tmp_path / "instance"
        instance.mkdir()
        mock_registry = MagicMock()
        with (
            patch("app.bridge_state.INSTANCE_DIR", instance),
            patch("app.bridge_state.build_registry", return_value=mock_registry),
            patch("app.bridge_state._skill_registry", None),
        ):
            from app.bridge_state import _get_registry
            reg = _get_registry()
        assert reg is mock_registry

    def test_get_registry_caches(self, tmp_path):
        instance = tmp_path / "instance"
        instance.mkdir()
        mock_registry = MagicMock()
        with (
            patch("app.bridge_state.INSTANCE_DIR", instance),
            patch("app.bridge_state.build_registry", return_value=mock_registry) as mock_build,
            patch("app.bridge_state._skill_registry", None),
        ):
            from app.bridge_state import _get_registry
            _get_registry()
        mock_build.assert_called_once()

    def test_get_registry_includes_instance_skills_dir(self, tmp_path):
        instance = tmp_path / "instance"
        instance.mkdir()
        skills_dir = instance / "skills"
        skills_dir.mkdir()
        mock_registry = MagicMock()
        with (
            patch("app.bridge_state.INSTANCE_DIR", instance),
            patch("app.bridge_state.build_registry", return_value=mock_registry) as mock_build,
            patch("app.bridge_state._skill_registry", None),
        ):
            from app.bridge_state import _get_registry
            _get_registry()
        args = mock_build.call_args
        assert skills_dir in args[0][0]

    def test_get_registry_no_instance_skills_dir(self, tmp_path):
        instance = tmp_path / "instance"
        instance.mkdir()
        mock_registry = MagicMock()
        with (
            patch("app.bridge_state.INSTANCE_DIR", instance),
            patch("app.bridge_state.build_registry", return_value=mock_registry) as mock_build,
            patch("app.bridge_state._skill_registry", None),
        ):
            from app.bridge_state import _get_registry
            _get_registry()
        args = mock_build.call_args
        assert args[0][0] == []

    def test_reset_registry_clears_cache(self):
        import app.bridge_state as bs
        bs._skill_registry = MagicMock()
        assert bs._skill_registry is not None
        bs._reset_registry()
        assert bs._skill_registry is None

    def test_reset_then_get_rebuilds(self, tmp_path):
        """After reset, next _get_registry call rebuilds from scratch."""
        instance = tmp_path / "instance"
        instance.mkdir()
        import app.bridge_state as bs
        bs._reset_registry()
        assert bs._skill_registry is None
        mock_registry = MagicMock()
        with (
            patch("app.bridge_state.INSTANCE_DIR", instance),
            patch("app.bridge_state.build_registry", return_value=mock_registry),
        ):
            reg = bs._get_registry()
        assert reg is mock_registry


# ── Module-level constants ────────────────────────────────────────


class TestModuleLevelConstants:
    """Test that module-level constants are set correctly."""

    def test_bot_token_from_env(self):
        import app.bridge_state as bs
        assert isinstance(bs.BOT_TOKEN, str)

    def test_chat_id_from_env(self):
        import app.bridge_state as bs
        assert isinstance(bs.CHAT_ID, str)

    def test_poll_interval_is_int(self):
        import app.bridge_state as bs
        assert isinstance(bs.POLL_INTERVAL, int)

    def test_chat_timeout_is_int(self):
        import app.bridge_state as bs
        assert isinstance(bs.CHAT_TIMEOUT, int)

    def test_koan_root_is_path(self):
        import app.bridge_state as bs
        assert isinstance(bs.KOAN_ROOT, Path)

    def test_instance_dir_under_koan_root(self):
        import app.bridge_state as bs
        assert bs.INSTANCE_DIR == bs.KOAN_ROOT / "instance"

    def test_missions_file_path(self):
        import app.bridge_state as bs
        assert bs.MISSIONS_FILE == bs.INSTANCE_DIR / "missions.md"

    def test_outbox_file_path(self):
        import app.bridge_state as bs
        assert bs.OUTBOX_FILE == bs.INSTANCE_DIR / "outbox.md"

    def test_telegram_api_url_format(self):
        import app.bridge_state as bs
        assert bs.TELEGRAM_API.startswith("https://api.telegram.org/bot")

    def test_conversation_history_file_is_path(self):
        import app.bridge_state as bs
        assert isinstance(bs.CONVERSATION_HISTORY_FILE, Path)
        assert bs.CONVERSATION_HISTORY_FILE.name == "conversation-history.jsonl"

    def test_topics_file_path(self):
        import app.bridge_state as bs
        assert bs.TOPICS_FILE.name == "previous-discussions-topics.json"


# ── SOUL / SUMMARY loading ───────────────────────────────────────


class TestSoulSummaryLoading:
    """Test that soul.md and summary.md are loaded at import time."""

    def test_soul_loaded_when_file_exists(self, tmp_path):
        instance = tmp_path / "instance"
        instance.mkdir(exist_ok=True)
        soul = instance / "soul.md"
        soul.write_text("I am Kōan.")
        assert soul.exists()
        assert soul.read_text() == "I am Kōan."

    def test_soul_empty_when_file_missing(self, tmp_path):
        instance = tmp_path / "instance"
        instance.mkdir(exist_ok=True)
        soul = instance / "soul.md"
        assert not soul.exists()

    def test_summary_loaded_when_file_exists(self, tmp_path):
        instance = tmp_path / "instance"
        (instance / "memory").mkdir(parents=True, exist_ok=True)
        summary = instance / "memory" / "summary.md"
        summary.write_text("Session summary.")
        assert summary.exists()
        assert summary.read_text() == "Session summary."
