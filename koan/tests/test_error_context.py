"""Tests for error_context.py — error extraction from Claude CLI output."""

import json
import os
import tempfile

import pytest

from app.error_context import (
    extract_error_summary,
    format_failure_notification,
    _is_noise,
    _is_error_signal,
    _extract_from_json,
)


# --- _is_noise ---

class TestIsNoise:
    def test_blank_line(self):
        assert _is_noise("") is True
        assert _is_noise("   ") is True

    def test_box_drawing(self):
        assert _is_noise("╭─ Error ─╮") is True
        assert _is_noise("│ detail  │") is True
        assert _is_noise("╰─────────╯") is True

    def test_progress_bar(self):
        assert _is_noise("  45% complete") is True

    def test_koan_log(self):
        assert _is_noise("[koan] Something happened") is True

    def test_npm_warn(self):
        assert _is_noise("npm warn deprecated package@1.0") is True

    def test_js_stack_trace(self):
        assert _is_noise("    at Object.<anonymous> (file.js:1:2)") is True

    def test_normal_line(self):
        assert _is_noise("Error: something went wrong") is False
        assert _is_noise("Permission denied") is False


# --- _is_error_signal ---

class TestIsErrorSignal:
    def test_error_keyword(self):
        assert _is_error_signal("Error: connection refused") is True

    def test_failed_keyword(self):
        assert _is_error_signal("Build failed with exit code 1") is True

    def test_exception(self):
        assert _is_error_signal("RuntimeException: null pointer") is True

    def test_traceback(self):
        assert _is_error_signal("Traceback (most recent call last):") is True

    def test_permission_denied(self):
        assert _is_error_signal("Permission denied: /etc/shadow") is True

    def test_timeout(self):
        assert _is_error_signal("Connection timeout after 30s") is True

    def test_quota(self):
        assert _is_error_signal("API quota exceeded") is True

    def test_rate_limit(self):
        assert _is_error_signal("Rate limit reached, retry after 60s") is True

    def test_signal(self):
        assert _is_error_signal("Process killed by SIGTERM") is True

    def test_oom(self):
        assert _is_error_signal("Out of memory") is True
        assert _is_error_signal("OOM killer invoked") is True

    def test_auth(self):
        assert _is_error_signal("401 Unauthorized") is True
        assert _is_error_signal("403 Forbidden") is True

    def test_normal_line(self):
        assert _is_error_signal("All tests passed") is False
        assert _is_error_signal("Compiling main.rs") is False


# --- _extract_from_json ---

class TestExtractFromJson:
    def test_error_field(self):
        data = json.dumps({"error": "API key invalid"})
        assert _extract_from_json(data) == "API key invalid"

    def test_message_field(self):
        data = json.dumps({"message": "Rate limited"})
        assert _extract_from_json(data) == "Rate limited"

    def test_detail_field(self):
        data = json.dumps({"detail": "Quota exhausted"})
        assert _extract_from_json(data) == "Quota exhausted"

    def test_reason_field(self):
        data = json.dumps({"reason": "Token expired"})
        assert _extract_from_json(data) == "Token expired"

    def test_no_error_field(self):
        data = json.dumps({"result": "some text", "content": "output"})
        assert _extract_from_json(data) == ""

    def test_invalid_json(self):
        assert _extract_from_json("not json at all") == ""

    def test_empty_input(self):
        assert _extract_from_json("") == ""
        assert _extract_from_json(None) == ""

    def test_truncation(self):
        data = json.dumps({"error": "x" * 500})
        result = _extract_from_json(data)
        assert len(result) <= 200


# --- extract_error_summary ---

class TestExtractErrorSummary:
    def test_simple_stderr(self):
        stderr = "Error: file not found\n"
        result = extract_error_summary(stderr)
        assert "file not found" in result

    def test_stderr_with_noise(self):
        stderr = """[koan] Starting mission
╭─ Progress ─╮
│ loading... │
╰────────────╯
Error: permission denied accessing /etc/shadow
"""
        result = extract_error_summary(stderr)
        assert "permission denied" in result
        assert "[koan]" not in result
        assert "╭" not in result

    def test_multi_error_lines(self):
        stderr = """Some info line
Warning: deprecated API
Error: connection refused
Error: retry failed after 3 attempts
Fatal: giving up
"""
        result = extract_error_summary(stderr)
        assert "retry failed" in result or "giving up" in result

    def test_empty_stderr_uses_stdout(self):
        stdout = "Something went wrong: timeout\n"
        result = extract_error_summary("", stdout)
        assert "timeout" in result

    def test_both_empty(self):
        assert extract_error_summary("", "") == ""

    def test_json_stdout_error(self):
        stdout = json.dumps({"error": "API key revoked"})
        result = extract_error_summary("", stdout)
        assert "API key revoked" in result

    def test_json_stdout_with_stderr(self):
        stderr = "Error: something specific\n"
        stdout = json.dumps({"error": "generic error"})
        # JSON error is extracted first (more structured and intentional)
        result = extract_error_summary(stderr, stdout)
        assert "generic error" in result

    def test_stderr_used_when_json_has_no_error(self):
        stderr = "Error: real problem here\n"
        stdout = json.dumps({"result": "some output", "content": "text"})
        # No error field in JSON — falls back to stderr
        result = extract_error_summary(stderr, stdout)
        assert "real problem here" in result

    def test_all_noise_falls_back_to_raw(self):
        stderr = "[koan] line 1\n[koan] line 2\n[koan] line 3\n"
        result = extract_error_summary(stderr)
        # Should fall back to raw lines since all are noise
        assert "line" in result

    def test_max_lines_respected(self):
        stderr = "\n".join(f"Error line {i}" for i in range(20))
        result = extract_error_summary(stderr, max_lines=3)
        lines = result.strip().splitlines()
        assert len(lines) <= 3

    def test_line_truncation(self):
        stderr = "Error: " + "x" * 500 + "\n"
        result = extract_error_summary(stderr)
        lines = result.strip().splitlines()
        assert all(len(line) <= 200 for line in lines)

    def test_traceback_detected(self):
        stderr = """Traceback (most recent call last):
  File "main.py", line 42, in run
    do_thing()
ValueError: invalid literal for int()
"""
        result = extract_error_summary(stderr)
        assert "ValueError" in result or "Traceback" in result

    def test_quota_message(self):
        stderr = "You've run out of extra usage quota. Resets at 2026-02-05 00:00:00 UTC\n"
        result = extract_error_summary(stderr)
        assert "quota" in result.lower()


# --- format_failure_notification ---

class TestFormatFailureNotification:
    def test_mission_failure_with_context(self):
        result = format_failure_notification(
            mission_title="fix auth bug",
            project_name="web-app",
            run_num=3,
            max_runs=10,
            error_summary="Error: permission denied"
        )
        assert "Run 3/10" in result
        assert "[web-app]" in result
        assert "Mission failed: fix auth bug" in result
        assert "Reason: Error: permission denied" in result

    def test_mission_failure_no_context(self):
        result = format_failure_notification(
            mission_title="fix auth bug",
            project_name="web-app",
            run_num=3,
            max_runs=10,
            error_summary=""
        )
        assert "Run 3/10" in result
        assert "Mission failed: fix auth bug" in result
        assert "Reason" not in result

    def test_autonomous_failure(self):
        result = format_failure_notification(
            mission_title="",
            project_name="koan",
            run_num=5,
            max_runs=10,
            error_summary="Timeout after 300s"
        )
        assert "Run 5/10" in result
        assert "Run failed" in result
        assert "Reason: Timeout after 300s" in result

    def test_long_reason_truncated(self):
        long_error = "Error: " + "x" * 500
        result = format_failure_notification(
            mission_title="test",
            project_name="koan",
            run_num=1,
            max_runs=10,
            error_summary=long_error
        )
        # Reason line should be capped
        for line in result.splitlines():
            if line.startswith("Reason:"):
                assert len(line) <= 310  # "Reason: " + 300 + "..."

    def test_multi_line_error_joined(self):
        result = format_failure_notification(
            mission_title="deploy",
            project_name="app",
            run_num=2,
            max_runs=5,
            error_summary="Error: build failed\nCause: missing dependency"
        )
        assert "Reason:" in result


# --- CLI entry point ---

class TestCLI:
    def test_cli_with_stderr_file(self, tmp_path):
        stderr_file = tmp_path / "stderr.txt"
        stderr_file.write_text("Error: something broke\n")

        import subprocess
        result = subprocess.run(
            ["python3", "-m", "app.error_context", str(stderr_file)],
            capture_output=True, text=True,
            cwd=str(tmp_path.parent.parent / "koan" if "koan" in str(tmp_path) else "/Users/nicolas/workspace/koan/koan"),
            env={**os.environ, "PYTHONPATH": "/Users/nicolas/workspace/koan/koan"},
        )
        assert "something broke" in result.stdout

    def test_cli_with_empty_files(self, tmp_path):
        stderr_file = tmp_path / "stderr.txt"
        stderr_file.write_text("")

        import subprocess
        result = subprocess.run(
            ["python3", "-m", "app.error_context", str(stderr_file)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": "/Users/nicolas/workspace/koan/koan"},
        )
        assert "No error context" in result.stdout

    def test_cli_with_both_files(self, tmp_path):
        stderr_file = tmp_path / "stderr.txt"
        stderr_file.write_text("")
        stdout_file = tmp_path / "stdout.txt"
        stdout_file.write_text(json.dumps({"error": "API key expired"}))

        import subprocess
        result = subprocess.run(
            ["python3", "-m", "app.error_context", str(stderr_file), str(stdout_file)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": "/Users/nicolas/workspace/koan/koan"},
        )
        assert "API key expired" in result.stdout
