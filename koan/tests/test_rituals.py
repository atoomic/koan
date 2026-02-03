"""Tests for rituals module."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.rituals import load_template, should_run_morning, should_run_evening, run_ritual


@pytest.fixture
def instance_dir(tmp_path):
    """Create a minimal instance directory for testing."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True)
    (tmp_path / "soul.md").write_text("You are Koan.")
    return tmp_path


@pytest.fixture
def koan_root(tmp_path, instance_dir):
    """Create a minimal koan root with templates."""
    koan_dir = tmp_path / "koan" / "system-prompts"
    koan_dir.mkdir(parents=True)

    # Create templates
    (koan_dir / "morning-brief.md").write_text(
        "Morning brief template. Instance: {INSTANCE}"
    )
    (koan_dir / "evening-debrief.md").write_text(
        "Evening debrief template. Instance: {INSTANCE}"
    )

    return tmp_path


class TestShouldRunMorning:
    def test_first_run_triggers_morning(self):
        assert should_run_morning(1) is True

    def test_second_run_no_morning(self):
        assert should_run_morning(2) is False

    def test_later_run_no_morning(self):
        assert should_run_morning(5) is False


class TestShouldRunEvening:
    def test_last_run_triggers_evening(self):
        assert should_run_evening(10, 10) is True

    def test_not_last_run_no_evening(self):
        assert should_run_evening(5, 10) is False

    def test_first_run_no_evening_unless_max_is_1(self):
        assert should_run_evening(1, 10) is False
        assert should_run_evening(1, 1) is True


class TestLoadTemplate:
    def test_loads_morning_template(self, koan_root, instance_dir, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(koan_root))
        template = load_template("morning-brief", instance_dir)
        assert "Morning brief template" in template
        assert str(instance_dir) in template

    def test_loads_evening_template(self, koan_root, instance_dir, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(koan_root))
        template = load_template("evening-debrief", instance_dir)
        assert "Evening debrief template" in template
        assert str(instance_dir) in template

    def test_replaces_instance_placeholder(self, koan_root, instance_dir, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(koan_root))
        template = load_template("morning-brief", instance_dir)
        assert "{INSTANCE}" not in template
        assert str(instance_dir) in template

    def test_raises_for_missing_template(self, koan_root, instance_dir, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(koan_root))
        with pytest.raises(FileNotFoundError):
            load_template("nonexistent", instance_dir)


class TestRunRitual:
    @patch("app.rituals.subprocess.run")
    def test_morning_calls_claude(self, mock_run, koan_root, instance_dir, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(koan_root))
        mock_run.return_value = MagicMock(returncode=0, stdout="Morning message", stderr="")

        result = run_ritual("morning", instance_dir)

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "claude"
        assert "-p" in call_args

    @patch("app.rituals.subprocess.run")
    def test_evening_calls_claude(self, mock_run, koan_root, instance_dir, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(koan_root))
        mock_run.return_value = MagicMock(returncode=0, stdout="Evening message", stderr="")

        result = run_ritual("evening", instance_dir)

        assert result is True
        mock_run.assert_called_once()

    @patch("app.rituals.subprocess.run")
    def test_handles_claude_failure(self, mock_run, koan_root, instance_dir, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(koan_root))
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")

        result = run_ritual("morning", instance_dir)

        assert result is False

    @patch("app.rituals.subprocess.run")
    def test_handles_timeout(self, mock_run, koan_root, instance_dir, monkeypatch):
        import subprocess
        monkeypatch.setenv("KOAN_ROOT", str(koan_root))
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=90)

        result = run_ritual("morning", instance_dir)

        assert result is False

    def test_returns_false_for_missing_template(self, tmp_path, instance_dir, monkeypatch):
        # Point to a koan_root without templates
        monkeypatch.setenv("KOAN_ROOT", str(tmp_path))

        result = run_ritual("morning", instance_dir)

        assert result is False
