"""Tests for Ollama REST API client (app.ollama_client)."""

import json
from unittest.mock import patch, MagicMock

import pytest

from app.ollama_client import (
    _get_ollama_host,
    _api_get,
    _model_matches_any,
    is_server_ready,
    get_version,
    list_models,
    list_running_models,
    is_model_available,
    get_model_info,
    check_server_and_model,
    format_model_list,
    DEFAULT_OLLAMA_HOST,
)


# ---------------------------------------------------------------------------
# Host resolution
# ---------------------------------------------------------------------------


class TestGetOllamaHost:
    """Tests for _get_ollama_host() — deriving native API host from config."""

    def test_default_host(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _get_ollama_host() == DEFAULT_OLLAMA_HOST

    def test_env_var_override(self):
        with patch.dict("os.environ", {"OLLAMA_HOST": "http://remote:11434"}):
            assert _get_ollama_host() == "http://remote:11434"

    def test_base_url_strips_v1_suffix(self):
        result = _get_ollama_host("http://localhost:11434/v1")
        assert result == "http://localhost:11434"

    def test_base_url_strips_v1_trailing_slash(self):
        result = _get_ollama_host("http://localhost:11434/v1/")
        assert result == "http://localhost:11434"

    def test_base_url_without_v1(self):
        result = _get_ollama_host("http://myserver:8080")
        assert result == "http://myserver:8080"

    def test_base_url_takes_priority_over_env(self):
        with patch.dict("os.environ", {"OLLAMA_HOST": "http://env:11434"}):
            result = _get_ollama_host("http://explicit:11434/v1")
            assert result == "http://explicit:11434"

    def test_base_url_strips_trailing_slash(self):
        result = _get_ollama_host("http://localhost:11434/")
        assert result == "http://localhost:11434"

    def test_custom_port_preserved(self):
        result = _get_ollama_host("http://gpu-box:8080/v1")
        assert result == "http://gpu-box:8080"


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------


class TestApiGet:
    """Tests for _api_get() — low-level GET wrapper."""

    def test_successful_get(self):
        response_data = {"version": "0.16.0"}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _api_get("http://localhost:11434", "/api/version")
            assert result == {"version": "0.16.0"}

    def test_http_error_raises(self):
        import urllib.error

        error = urllib.error.HTTPError(
            "http://localhost:11434/api/tags", 500, "Internal Server Error",
            {}, MagicMock(read=MagicMock(return_value=b"error body"))
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with pytest.raises(RuntimeError, match="API error 500"):
                _api_get("http://localhost:11434", "/api/tags")

    def test_connection_refused_raises(self):
        import urllib.error

        error = urllib.error.URLError("Connection refused")
        with patch("urllib.request.urlopen", side_effect=error):
            with pytest.raises(RuntimeError, match="Cannot connect"):
                _api_get("http://localhost:11434", "/api/tags")

    def test_timeout_raises(self):
        import socket

        with patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            with pytest.raises(RuntimeError, match="request failed"):
                _api_get("http://localhost:11434", "/api/tags")


# ---------------------------------------------------------------------------
# Model matching
# ---------------------------------------------------------------------------


class TestModelMatchesAny:
    """Tests for _model_matches_any() — fuzzy model name matching."""

    SAMPLE_MODELS = [
        {"name": "qwen2.5-coder:14b", "model": "qwen2.5-coder:14b"},
        {"name": "llama3.2:latest", "model": "llama3.2:latest"},
        {"name": "codestral:22b-v0.1-q4_K_M", "model": "codestral:22b-v0.1-q4_K_M"},
    ]

    def test_exact_match(self):
        assert _model_matches_any("qwen2.5-coder:14b", self.SAMPLE_MODELS) is True

    def test_name_without_tag_matches_latest(self):
        assert _model_matches_any("llama3.2", self.SAMPLE_MODELS) is True

    def test_name_without_tag_matches_any_tag(self):
        assert _model_matches_any("qwen2.5-coder", self.SAMPLE_MODELS) is True

    def test_no_match(self):
        assert _model_matches_any("mistral", self.SAMPLE_MODELS) is False

    def test_empty_name(self):
        assert _model_matches_any("", self.SAMPLE_MODELS) is False

    def test_empty_model_list(self):
        assert _model_matches_any("qwen2.5-coder", []) is False

    def test_model_field_used_when_name_missing(self):
        models = [{"model": "glm4:latest"}]
        assert _model_matches_any("glm4", models) is True

    def test_partial_name_no_match(self):
        """Partial base name should not match."""
        assert _model_matches_any("qwen2.5", self.SAMPLE_MODELS) is False

    def test_wrong_tag_no_match(self):
        assert _model_matches_any("llama3.2:7b", self.SAMPLE_MODELS) is False

    def test_with_whitespace(self):
        assert _model_matches_any("  llama3.2  ", self.SAMPLE_MODELS) is True


# ---------------------------------------------------------------------------
# Server health
# ---------------------------------------------------------------------------


class TestIsServerReady:
    """Tests for is_server_ready() — lightweight health probe."""

    def test_server_responding(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert is_server_ready() is True

    def test_server_returns_error_still_ready(self):
        """Even HTTP errors mean the server is running."""
        import urllib.error

        error = urllib.error.HTTPError(
            "http://localhost:11434/", 503, "Service Unavailable",
            {}, MagicMock(read=MagicMock(return_value=b""))
        )
        with patch("urllib.request.urlopen", side_effect=error):
            assert is_server_ready() is True

    def test_server_not_responding(self):
        import urllib.error

        error = urllib.error.URLError("Connection refused")
        with patch("urllib.request.urlopen", side_effect=error):
            assert is_server_ready() is False

    def test_timeout(self):
        import socket

        with patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            assert is_server_ready() is False


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


class TestGetVersion:
    """Tests for get_version() — server version retrieval."""

    def test_returns_version_string(self):
        with patch("app.ollama_client._api_get", return_value={"version": "0.16.0"}):
            assert get_version() == "0.16.0"

    def test_returns_none_on_error(self):
        with patch("app.ollama_client._api_get", side_effect=RuntimeError("offline")):
            assert get_version() is None

    def test_returns_none_if_missing_key(self):
        with patch("app.ollama_client._api_get", return_value={}):
            assert get_version() is None


# ---------------------------------------------------------------------------
# List models
# ---------------------------------------------------------------------------


class TestListModels:
    """Tests for list_models() — model listing."""

    SAMPLE_RESPONSE = {
        "models": [
            {
                "name": "qwen2.5-coder:14b",
                "model": "qwen2.5-coder:14b",
                "size": 9_000_000_000,
                "details": {"parameter_size": "14B", "quantization_level": "Q4_K_M"},
            },
            {
                "name": "llama3.2:latest",
                "model": "llama3.2:latest",
                "size": 2_000_000_000,
                "details": {"parameter_size": "3B"},
            },
        ]
    }

    def test_returns_model_list(self):
        with patch("app.ollama_client._api_get", return_value=self.SAMPLE_RESPONSE):
            models = list_models()
            assert len(models) == 2
            assert models[0]["name"] == "qwen2.5-coder:14b"

    def test_returns_empty_on_error(self):
        with patch("app.ollama_client._api_get", side_effect=RuntimeError("offline")):
            assert list_models() == []

    def test_returns_empty_if_no_models_key(self):
        with patch("app.ollama_client._api_get", return_value={}):
            assert list_models() == []


# ---------------------------------------------------------------------------
# List running models
# ---------------------------------------------------------------------------


class TestListRunningModels:
    """Tests for list_running_models() — loaded model listing."""

    def test_returns_running_models(self):
        data = {"models": [{"name": "qwen2.5-coder:14b", "size_vram": 8_000_000_000}]}
        with patch("app.ollama_client._api_get", return_value=data):
            models = list_running_models()
            assert len(models) == 1
            assert models[0]["name"] == "qwen2.5-coder:14b"

    def test_returns_empty_on_error(self):
        with patch("app.ollama_client._api_get", side_effect=RuntimeError("offline")):
            assert list_running_models() == []


# ---------------------------------------------------------------------------
# Model availability
# ---------------------------------------------------------------------------


class TestIsModelAvailable:
    """Tests for is_model_available() — model presence check."""

    MODELS = {
        "models": [
            {"name": "qwen2.5-coder:14b", "model": "qwen2.5-coder:14b"},
            {"name": "llama3.2:latest", "model": "llama3.2:latest"},
        ]
    }

    def test_model_found(self):
        with patch("app.ollama_client._api_get", return_value=self.MODELS):
            assert is_model_available("qwen2.5-coder:14b") is True

    def test_model_found_no_tag(self):
        with patch("app.ollama_client._api_get", return_value=self.MODELS):
            assert is_model_available("llama3.2") is True

    def test_model_not_found(self):
        with patch("app.ollama_client._api_get", return_value=self.MODELS):
            assert is_model_available("mistral") is False

    def test_returns_false_on_error(self):
        with patch("app.ollama_client._api_get", side_effect=RuntimeError("offline")):
            assert is_model_available("qwen2.5-coder:14b") is False


# ---------------------------------------------------------------------------
# Get model info
# ---------------------------------------------------------------------------


class TestGetModelInfo:
    """Tests for get_model_info() — model detail lookup."""

    MODELS = {
        "models": [
            {
                "name": "qwen2.5-coder:14b",
                "model": "qwen2.5-coder:14b",
                "size": 9_000_000_000,
                "details": {"parameter_size": "14B"},
            },
        ]
    }

    def test_returns_model_dict(self):
        with patch("app.ollama_client._api_get", return_value=self.MODELS):
            info = get_model_info("qwen2.5-coder:14b")
            assert info is not None
            assert info["size"] == 9_000_000_000

    def test_returns_none_not_found(self):
        with patch("app.ollama_client._api_get", return_value=self.MODELS):
            assert get_model_info("mistral") is None

    def test_returns_none_empty_name(self):
        with patch("app.ollama_client._api_get", return_value=self.MODELS):
            assert get_model_info("") is None

    def test_fuzzy_match_no_tag(self):
        with patch("app.ollama_client._api_get", return_value=self.MODELS):
            info = get_model_info("qwen2.5-coder")
            assert info is not None


# ---------------------------------------------------------------------------
# Combined check
# ---------------------------------------------------------------------------


class TestCheckServerAndModel:
    """Tests for check_server_and_model() — full readiness check."""

    def test_all_ok(self):
        with patch("app.ollama_client.is_server_ready", return_value=True), \
             patch("app.ollama_client.is_model_available", return_value=True):
            ok, detail = check_server_and_model("qwen2.5-coder:14b")
            assert ok is True
            assert detail == ""

    def test_server_not_responding(self):
        with patch("app.ollama_client.is_server_ready", return_value=False):
            ok, detail = check_server_and_model("qwen2.5-coder:14b")
            assert ok is False
            assert "not responding" in detail

    def test_no_model_configured(self):
        with patch("app.ollama_client.is_server_ready", return_value=True):
            ok, detail = check_server_and_model("")
            assert ok is False
            assert "No model configured" in detail

    def test_model_not_available(self):
        with patch("app.ollama_client.is_server_ready", return_value=True), \
             patch("app.ollama_client.is_model_available", return_value=False):
            ok, detail = check_server_and_model("missing-model")
            assert ok is False
            assert "not found locally" in detail
            assert "ollama pull" in detail

    def test_custom_base_url(self):
        with patch("app.ollama_client.is_server_ready", return_value=True) as mock_ready, \
             patch("app.ollama_client.is_model_available", return_value=True):
            check_server_and_model("model", base_url="http://gpu:11434/v1")
            mock_ready.assert_called_once_with(base_url="http://gpu:11434/v1", timeout=5.0)

    def test_server_not_responding_default_host_shows_hint(self):
        """When using default host, error includes config variable hints."""
        with patch("app.ollama_client.is_server_ready", return_value=False):
            ok, detail = check_server_and_model("model")
            assert ok is False
            assert "OLLAMA_HOST" in detail or "KOAN_LOCAL_LLM_BASE_URL" in detail

    def test_server_not_responding_custom_host_no_hint(self):
        """When using explicit base_url, error doesn't suggest env vars."""
        with patch("app.ollama_client.is_server_ready", return_value=False):
            ok, detail = check_server_and_model("model", base_url="http://gpu:11434/v1")
            assert ok is False
            assert "gpu:11434" in detail
            assert "OLLAMA_HOST" not in detail


# ---------------------------------------------------------------------------
# Format model list
# ---------------------------------------------------------------------------


class TestFormatModelList:
    """Tests for format_model_list() — human-readable output."""

    def test_formats_models_with_details(self):
        models = [
            {
                "name": "qwen2.5-coder:14b",
                "size": 9_663_676_416,
                "details": {"parameter_size": "14B", "quantization_level": "Q4_K_M"},
            },
            {
                "name": "llama3.2:latest",
                "size": 2_147_483_648,
                "details": {"parameter_size": "3B"},
            },
        ]
        with patch("app.ollama_client.list_models", return_value=models):
            output = format_model_list()
            assert "qwen2.5-coder:14b" in output
            assert "(14B)" in output
            assert "[Q4_K_M]" in output
            assert "llama3.2:latest" in output
            assert "(3B)" in output

    def test_no_models(self):
        with patch("app.ollama_client.list_models", return_value=[]):
            output = format_model_list()
            assert "No models available" in output

    def test_model_without_details(self):
        models = [{"name": "custom-model:v1", "size": 0, "details": {}}]
        with patch("app.ollama_client.list_models", return_value=models):
            output = format_model_list()
            assert "custom-model:v1" in output


# ---------------------------------------------------------------------------
# Provider integration
# ---------------------------------------------------------------------------


class TestLocalProviderIntegration:
    """Tests for ollama_client integration with LocalLLMProvider."""

    def test_is_available_checks_server(self):
        """is_available() should probe the server, not just check config."""
        from app.provider.local import LocalLLMProvider

        provider = LocalLLMProvider()
        with patch.dict("os.environ", {"KOAN_LOCAL_LLM_MODEL": "test-model"}), \
             patch("app.ollama_client.is_server_ready", return_value=True):
            assert provider.is_available() is True

    def test_is_available_false_when_server_down(self):
        from app.provider.local import LocalLLMProvider

        provider = LocalLLMProvider()
        with patch.dict("os.environ", {"KOAN_LOCAL_LLM_MODEL": "test-model"}), \
             patch("app.ollama_client.is_server_ready", return_value=False):
            assert provider.is_available() is False

    def test_is_available_false_when_no_model(self):
        from app.provider.local import LocalLLMProvider

        provider = LocalLLMProvider()
        with patch.dict("os.environ", {}, clear=True), \
             patch("app.utils.load_config", return_value={}):
            assert provider.is_available() is False

    def test_check_quota_verifies_server_and_model(self):
        from app.provider.local import LocalLLMProvider

        provider = LocalLLMProvider()
        with patch.dict("os.environ", {
            "KOAN_LOCAL_LLM_MODEL": "test-model",
            "KOAN_LOCAL_LLM_BASE_URL": "http://localhost:11434/v1",
        }), \
             patch("app.ollama_client.check_server_and_model", return_value=(True, "")) as mock:
            ok, detail = provider.check_quota_available("/tmp/project")
            assert ok is True
            mock.assert_called_once_with(
                model_name="test-model",
                base_url="http://localhost:11434/v1",
                timeout=15.0,
            )

    def test_check_quota_returns_error_detail(self):
        from app.provider.local import LocalLLMProvider

        provider = LocalLLMProvider()
        with patch.dict("os.environ", {"KOAN_LOCAL_LLM_MODEL": "missing"}), \
             patch("app.ollama_client.check_server_and_model",
                   return_value=(False, "Model 'missing' not found locally")):
            ok, detail = provider.check_quota_available("/tmp/project")
            assert ok is False
            assert "not found" in detail

    def test_is_available_logs_no_model(self, caplog):
        """is_available() logs why it returns False when no model configured."""
        import logging
        from app.provider.local import LocalLLMProvider

        provider = LocalLLMProvider()
        with patch.dict("os.environ", {}, clear=True), \
             patch("app.utils.load_config", return_value={}), \
             caplog.at_level(logging.DEBUG, logger="koan.provider"):
            result = provider.is_available()
            assert result is False
            assert "no model configured" in caplog.text

    def test_is_available_logs_server_down(self, caplog):
        """is_available() logs why it returns False when server is unreachable."""
        import logging
        from app.provider.local import LocalLLMProvider

        provider = LocalLLMProvider()
        with patch.dict("os.environ", {"KOAN_LOCAL_LLM_MODEL": "test-model"}), \
             patch("app.ollama_client.is_server_ready", return_value=False), \
             caplog.at_level(logging.DEBUG, logger="koan.provider"):
            result = provider.is_available()
            assert result is False
            assert "not responding" in caplog.text


# ---------------------------------------------------------------------------
# PID manager integration
# ---------------------------------------------------------------------------


class TestPidManagerIntegration:
    """Tests for ollama_client integration with pid_manager.start_ollama()."""

    def test_start_ollama_verifies_http(self):
        """start_ollama should check HTTP readiness, not just process liveness."""
        from app.pid_manager import start_ollama
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "logs").mkdir()

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            with patch("shutil.which", return_value="/usr/bin/ollama"), \
                 patch("app.pid_manager.check_pidfile", return_value=None), \
                 patch("app.pid_manager._open_log_file", return_value=MagicMock()), \
                 patch("subprocess.Popen", return_value=mock_proc), \
                 patch("app.pid_manager.acquire_pid"), \
                 patch("app.pid_manager._is_process_alive", return_value=True), \
                 patch("app.ollama_client.is_server_ready", return_value=True), \
                 patch("time.monotonic", side_effect=[0, 0.1, 0.2]):
                ok, msg = start_ollama(root)
                assert ok is True
                assert "started" in msg
                assert "12345" in msg

    def test_start_ollama_warming_up(self):
        """If HTTP never responds but process is alive, report warming up."""
        from app.pid_manager import start_ollama
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "logs").mkdir()

            mock_proc = MagicMock()
            mock_proc.pid = 12345

            # Simulate: process alive but HTTP never ready (timeout after monotonic exhaustion)
            times = [0] + [i * 0.5 for i in range(20)] + [100]
            with patch("shutil.which", return_value="/usr/bin/ollama"), \
                 patch("app.pid_manager.check_pidfile", return_value=None), \
                 patch("app.pid_manager._open_log_file", return_value=MagicMock()), \
                 patch("subprocess.Popen", return_value=mock_proc), \
                 patch("app.pid_manager.acquire_pid"), \
                 patch("app.pid_manager._is_process_alive", return_value=True), \
                 patch("app.ollama_client.is_server_ready", return_value=False), \
                 patch("time.monotonic", side_effect=times), \
                 patch("time.sleep"):
                ok, msg = start_ollama(root)
                assert ok is True
                assert "warming up" in msg


# ---------------------------------------------------------------------------
# _api_post
# ---------------------------------------------------------------------------


class TestApiPost:
    """Tests for _api_post() — low-level POST wrapper."""

    def test_successful_post(self):
        from app.ollama_client import _api_post
        response_data = {"status": "success"}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _api_post("http://localhost:11434", "/api/pull", {"name": "llama3.3"})
        assert result == {"status": "success"}

    def test_http_error_raises(self):
        import urllib.error
        from app.ollama_client import _api_post
        error = urllib.error.HTTPError(
            "http://localhost:11434/api/pull", 404, "Not Found",
            {}, MagicMock(read=MagicMock(return_value=b"model not found"))
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with pytest.raises(RuntimeError, match="API error 404"):
                _api_post("http://localhost:11434", "/api/pull", {"name": "nope"})

    def test_connection_error_raises(self):
        import urllib.error
        from app.ollama_client import _api_post
        error = urllib.error.URLError("Connection refused")
        with patch("urllib.request.urlopen", side_effect=error):
            with pytest.raises(RuntimeError, match="Cannot connect"):
                _api_post("http://localhost:11434", "/api/pull", {"name": "llama3.3"})

    def test_posts_json_body(self):
        from app.ollama_client import _api_post
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            _api_post("http://localhost:11434", "/api/pull", {"name": "test", "stream": False})
            req = mock_open.call_args[0][0]
            assert req.method == "POST"
            assert req.get_header("Content-type") == "application/json"
            body = json.loads(req.data.decode())
            assert body["name"] == "test"
            assert body["stream"] is False


# ---------------------------------------------------------------------------
# pull_model
# ---------------------------------------------------------------------------


class TestPullModel:
    """Tests for pull_model() — downloading models from Ollama registry."""

    def test_successful_pull(self):
        from app.ollama_client import pull_model
        with patch("app.ollama_client.is_server_ready", return_value=True), \
             patch("app.ollama_client._api_post",
                   return_value={"status": "success"}):
            ok, detail = pull_model("llama3.3")
        assert ok is True
        assert detail == "success"

    def test_pull_empty_model_name(self):
        from app.ollama_client import pull_model
        ok, detail = pull_model("")
        assert ok is False
        assert "No model name" in detail

    def test_pull_whitespace_model_name(self):
        from app.ollama_client import pull_model
        ok, detail = pull_model("   ")
        assert ok is False
        assert "No model name" in detail

    def test_pull_server_not_ready(self):
        from app.ollama_client import pull_model
        with patch("app.ollama_client.is_server_ready", return_value=False):
            ok, detail = pull_model("llama3.3")
        assert ok is False
        assert "not responding" in detail

    def test_pull_api_error(self):
        from app.ollama_client import pull_model
        with patch("app.ollama_client.is_server_ready", return_value=True), \
             patch("app.ollama_client._api_post",
                   side_effect=RuntimeError("API error 404: model not found")):
            ok, detail = pull_model("nonexistent-model")
        assert ok is False
        assert "404" in detail

    def test_pull_non_success_status(self):
        from app.ollama_client import pull_model
        with patch("app.ollama_client.is_server_ready", return_value=True), \
             patch("app.ollama_client._api_post",
                   return_value={"status": "downloading"}):
            ok, detail = pull_model("llama3.3")
        assert ok is True
        assert detail == "downloading"

    def test_pull_empty_status(self):
        from app.ollama_client import pull_model
        with patch("app.ollama_client.is_server_ready", return_value=True), \
             patch("app.ollama_client._api_post", return_value={}):
            ok, detail = pull_model("llama3.3")
        assert ok is True
        assert detail == "completed"

    def test_pull_strips_model_name(self):
        from app.ollama_client import pull_model
        with patch("app.ollama_client.is_server_ready", return_value=True), \
             patch("app.ollama_client._api_post",
                   return_value={"status": "success"}) as mock_post:
            pull_model("  llama3.3  ")
            body = mock_post.call_args[0][2]
            assert body["name"] == "llama3.3"

    def test_pull_uses_long_timeout(self):
        from app.ollama_client import pull_model
        with patch("app.ollama_client.is_server_ready", return_value=True), \
             patch("app.ollama_client._api_post",
                   return_value={"status": "success"}) as mock_post:
            pull_model("llama3.3")
            assert mock_post.call_args[1].get("timeout", 0) == 600.0

    def test_pull_with_tag(self):
        from app.ollama_client import pull_model
        with patch("app.ollama_client.is_server_ready", return_value=True), \
             patch("app.ollama_client._api_post",
                   return_value={"status": "success"}) as mock_post:
            ok, _ = pull_model("qwen2.5-coder:14b")
            assert ok is True
            body = mock_post.call_args[0][2]
            assert body["name"] == "qwen2.5-coder:14b"
