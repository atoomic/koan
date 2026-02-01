"""Tests for recover.py — crash recovery of stale in-progress missions."""

from unittest.mock import patch

import pytest

from recover import recover_missions


def _missions(pending="", in_progress="", done=""):
    """Build a missions.md content string."""
    return (
        f"# Missions\n\n"
        f"## En attente\n\n{pending}\n\n"
        f"## En cours\n\n{in_progress}\n\n"
        f"## Terminées\n\n{done}\n"
    )


class TestRecoverMissions:

    def test_no_stale_missions(self, instance_dir):
        assert recover_missions(str(instance_dir)) == 0

    def test_missing_missions_file(self, tmp_path):
        assert recover_missions(str(tmp_path / "nonexistent")) == 0

    def test_recover_simple_mission(self, instance_dir):
        missions = instance_dir / "missions.md"
        missions.write_text(_missions(in_progress="- Fix the bug"))

        count = recover_missions(str(instance_dir))
        assert count == 1

        content = missions.read_text()
        lines = content.splitlines()
        pending_idx = next(i for i, l in enumerate(lines) if "en attente" in l.lower())
        in_prog_idx = next(i for i, l in enumerate(lines) if "en cours" in l.lower())
        between = "\n".join(lines[pending_idx + 1 : in_prog_idx])
        assert "Fix the bug" in between

    def test_no_duplicate_lines(self, instance_dir):
        """Regression: recovered missions must not duplicate existing lines."""
        missions = instance_dir / "missions.md"
        missions.write_text(
            "# Missions\n\n"
            "## En attente\n\n"
            "- Existing task\n\n"
            "## En cours\n\n"
            "- Stale task\n\n"
            "## Terminées\n\n"
        )

        recover_missions(str(instance_dir))
        content = missions.read_text()

        # "Existing task" must appear exactly once
        assert content.count("Existing task") == 1
        # "Stale task" must appear exactly once (moved to pending)
        assert content.count("Stale task") == 1

    def test_aucune_placeholder_removed(self, instance_dir):
        """(aucune) placeholder is removed when missions are recovered."""
        missions = instance_dir / "missions.md"
        missions.write_text(_missions(pending="(aucune)", in_progress="- A task"))

        recover_missions(str(instance_dir))
        content = missions.read_text()
        assert "(aucune)" not in content
        assert "A task" in content

    def test_complex_missions_kept(self, instance_dir):
        """### header missions stay in progress."""
        missions = instance_dir / "missions.md"
        missions.write_text(_missions(
            in_progress="### Big project\n- ~~step 1~~ done\n- step 2\n\n- Simple task"
        ))

        count = recover_missions(str(instance_dir))
        assert count == 1  # Only "Simple task" recovered

        content = missions.read_text()
        lines = content.splitlines()
        in_prog_idx = next(i for i, l in enumerate(lines) if "en cours" in l.lower())
        after_in_prog = "\n".join(lines[in_prog_idx:])
        assert "Big project" in after_in_prog

    def test_strikethrough_not_recovered(self, instance_dir):
        """Fully struck-through items are not recovered."""
        missions = instance_dir / "missions.md"
        missions.write_text(_missions(in_progress="- ~~Done task~~\n- Active task"))

        count = recover_missions(str(instance_dir))
        assert count == 1

        content = missions.read_text()
        lines = content.splitlines()
        pending_idx = next(i for i, l in enumerate(lines) if "en attente" in l.lower())
        in_prog_idx = next(i for i, l in enumerate(lines) if "en cours" in l.lower())
        between = "\n".join(lines[pending_idx:in_prog_idx])
        assert "Active task" in between
        assert "Done task" not in between

    def test_no_section_headers_duplicated(self, instance_dir):
        """Section headers must not be duplicated after recovery."""
        missions = instance_dir / "missions.md"
        missions.write_text(_missions(in_progress="- Task A\n- Task B"))

        recover_missions(str(instance_dir))
        content = missions.read_text()

        assert content.count("## En attente") == 1
        assert content.count("## En cours") == 1
        assert content.count("## Terminées") == 1
