"""Tests for ASCII art banner module."""

import io
from unittest.mock import patch

from app.banners import (
    BLUE,
    BOLD,
    CYAN,
    GREEN,
    MAGENTA,
    RESET,
    WHITE,
    YELLOW,
    _read_art,
    colorize_agent,
    colorize_bridge,
    colorize_startup,
    print_agent_banner,
    print_bridge_banner,
    print_startup_banner,
)


class TestReadArt:
    def test_reads_agent_art(self):
        art = _read_art("agent.txt")
        assert art
        assert "K Ō A N" in art

    def test_reads_bridge_art(self):
        art = _read_art("bridge.txt")
        assert art
        assert "A W A K E" in art

    def test_missing_file_returns_empty(self):
        art = _read_art("nonexistent.txt")
        assert art == ""

    def test_agent_art_within_size_limit(self):
        art = _read_art("agent.txt")
        lines = [l for l in art.split("\n") if l.strip()]
        assert len(lines) <= 16, f"Agent art has {len(lines)} lines, max is 16"
        for line in lines:
            assert len(line) <= 16, f"Line too wide ({len(line)}): {line!r}"

    def test_bridge_art_within_size_limit(self):
        art = _read_art("bridge.txt")
        lines = [l for l in art.split("\n") if l.strip()]
        assert len(lines) <= 16, f"Bridge art has {len(lines)} lines, max is 16"
        for line in lines:
            assert len(line) <= 24, f"Line too wide ({len(line)}): {line!r}"


class TestColorize:
    def test_agent_colors_eyes(self):
        result = colorize_agent("◉ test ◉")
        assert CYAN in result
        assert RESET in result

    def test_agent_colors_radioactive(self):
        result = colorize_agent("──☢──")
        assert YELLOW in result

    def test_bridge_colors_diamonds(self):
        result = colorize_bridge("◇ signal ◇")
        assert CYAN in result

    def test_bridge_colors_arrows(self):
        result = colorize_bridge("→→ data ←←")
        assert "\033[32m" in result  # GREEN

    def test_plain_text_gets_base_color(self):
        result = colorize_agent("plain line")
        assert BLUE in result
        result = colorize_bridge("plain line")
        assert MAGENTA in result


class TestPrintBanners:
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_print_agent_banner(self, mock_stdout):
        print_agent_banner()
        output = mock_stdout.getvalue()
        assert "K" in output  # Part of "K Ō A N"

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_print_agent_banner_with_version(self, mock_stdout):
        print_agent_banner("v1.0 — test")
        output = mock_stdout.getvalue()
        assert "v1.0" in output

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_print_bridge_banner(self, mock_stdout):
        print_bridge_banner()
        output = mock_stdout.getvalue()
        assert "A W A K E" in output

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_print_bridge_banner_with_version(self, mock_stdout):
        print_bridge_banner("v1.0 — bridge")
        output = mock_stdout.getvalue()
        assert "v1.0" in output

    @patch("app.banners._read_art", return_value="")
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_missing_art_prints_nothing(self, mock_stdout, mock_read):
        print_agent_banner("version")
        assert mock_stdout.getvalue() == ""

    @patch("app.banners._read_art", return_value="")
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_missing_bridge_art_prints_nothing(self, mock_stdout, mock_read):
        print_bridge_banner("version")
        assert mock_stdout.getvalue() == ""


class TestStartupBanner:
    def test_reads_startup_art(self):
        art = _read_art("startup.txt")
        assert art
        assert "K   Ō   A   N" in art

    def test_startup_art_contains_both_motifs(self):
        art = _read_art("startup.txt")
        # Agent robot elements
        assert "◉" in art
        assert "☢" in art
        # Bridge signal elements
        assert "◇" in art
        assert "◆" in art

    def test_colorize_startup_applies_agent_colors(self):
        result = colorize_startup("◉ robot ☢")
        assert CYAN in result
        assert YELLOW in result

    def test_colorize_startup_applies_bridge_colors(self):
        result = colorize_startup("◇ signal ◆ →←")
        assert CYAN in result
        assert GREEN in result

    def test_colorize_startup_box_frame(self):
        result = colorize_startup("╔═══╗")
        assert BOLD in result
        assert CYAN in result

    def test_colorize_startup_title(self):
        result = colorize_startup("K   Ō   A   N")
        assert WHITE in result
        assert BOLD in result

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_print_startup_banner(self, mock_stdout):
        print_startup_banner()
        output = mock_stdout.getvalue()
        assert "K" in output

    @patch("app.banners._read_art", return_value="")
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_missing_startup_art_prints_nothing(self, mock_stdout, mock_read):
        print_startup_banner()
        assert mock_stdout.getvalue() == ""


class TestStartScript:
    """Tests for the unified start.sh launcher script."""

    def test_start_script_exists(self):
        from pathlib import Path
        script = Path(__file__).parent.parent / "start.sh"
        assert script.exists(), "start.sh must exist in koan/"

    def test_start_script_is_executable(self):
        import os
        from pathlib import Path
        script = Path(__file__).parent.parent / "start.sh"
        assert os.access(script, os.X_OK), "start.sh must be executable"

    def test_start_script_has_shebang(self):
        from pathlib import Path
        script = Path(__file__).parent.parent / "start.sh"
        content = script.read_text()
        assert content.startswith("#!/bin/bash"), "start.sh must have bash shebang"

    def test_start_script_has_trap(self):
        from pathlib import Path
        script = Path(__file__).parent.parent / "start.sh"
        content = script.read_text()
        assert "trap cleanup INT TERM" in content, "Must trap INT and TERM signals"

    def test_start_script_launches_both_processes(self):
        from pathlib import Path
        script = Path(__file__).parent.parent / "start.sh"
        content = script.read_text()
        assert "awake.py" in content, "Must launch awake.py"
        assert "run.sh" in content, "Must launch run.sh"

    def test_start_script_prefixes_output(self):
        from pathlib import Path
        script = Path(__file__).parent.parent / "start.sh"
        content = script.read_text()
        assert "[bridge]" in content, "Must prefix bridge output"
        assert "[agent]" in content, "Must prefix agent output"
