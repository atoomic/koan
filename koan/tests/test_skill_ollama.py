"""Tests for the /ollama skill handler."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# Ensure the koan package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skills.core.ollama.handler import handle, _format_size


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def instance_dir(tmp_path):
    inst = tmp_path / "instance"
    inst.mkdir()
    return inst


@pytest.fixture
def koan_root(tmp_path, instance_dir):
    return tmp_path


def _make_ctx(koan_root, instance_dir, command_name="ollama", args=""):
    return SimpleNamespace(
        koan_root=koan_root,
        instance_dir=instance_dir,
        command_name=command_name,
        args=args,
        send_message=None,
        handle_chat=None,
    )


def _patch_ollama(provider="local", ready=True, version="0.16.0",
                  models=None, running=None):
    """Return a stack of patches for ollama-related calls."""
    if models is None:
        models = []
    if running is None:
        running = []
    return (
        patch("app.provider.get_provider_name", return_value=provider),
        patch("app.ollama_client.is_server_ready", return_value=ready),
        patch("app.ollama_client.get_version", return_value=version),
        patch("app.ollama_client.list_models", return_value=models),
        patch("app.ollama_client.list_running_models", return_value=running),
    )


# ---------------------------------------------------------------------------
# _format_size
# ---------------------------------------------------------------------------

class TestFormatSize:
    def test_zero_returns_empty(self):
        assert _format_size(0) == ""

    def test_none_returns_empty(self):
        assert _format_size(None) == ""

    def test_gb_size(self):
        assert _format_size(5 * 1024 ** 3) == "5.0GB"

    def test_mb_size(self):
        assert _format_size(500 * 1024 ** 2) == "500MB"

    def test_small_gb(self):
        result = _format_size(int(1.5 * 1024 ** 3))
        assert "1.5GB" in result

    def test_exactly_1gb(self):
        assert _format_size(1024 ** 3) == "1.0GB"

    def test_sub_gb_shows_mb(self):
        result = _format_size(100 * 1024 ** 2)
        assert result == "100MB"


# ---------------------------------------------------------------------------
# handle — provider check
# ---------------------------------------------------------------------------

class TestHandleProviderCheck:
    def test_not_active_for_claude(self, koan_root, instance_dir):
        ctx = _make_ctx(koan_root, instance_dir)
        with patch("app.provider.get_provider_name", return_value="claude"):
            result = handle(ctx)
        assert "not active" in result
        assert "claude" in result

    def test_not_active_for_copilot(self, koan_root, instance_dir):
        ctx = _make_ctx(koan_root, instance_dir)
        with patch("app.provider.get_provider_name", return_value="copilot"):
            result = handle(ctx)
        assert "not active" in result


# ---------------------------------------------------------------------------
# handle — server not responding
# ---------------------------------------------------------------------------

class TestHandleServerDown:
    def test_server_not_responding(self, koan_root, instance_dir):
        ctx = _make_ctx(koan_root, instance_dir)
        patches = _patch_ollama(ready=False)
        with patches[0], patches[1]:
            result = handle(ctx)
        assert "not responding" in result
        assert "ollama serve" in result


# ---------------------------------------------------------------------------
# handle — server running
# ---------------------------------------------------------------------------

class TestHandleServerRunning:
    def test_no_models(self, koan_root, instance_dir):
        ctx = _make_ctx(koan_root, instance_dir)
        patches = _patch_ollama(models=[])
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = handle(ctx)
        assert "v0.16.0" in result
        assert "No models pulled" in result
        assert "ollama pull" in result

    def test_models_listed(self, koan_root, instance_dir):
        models = [
            {"name": "qwen2.5-coder:14b", "size": 9 * 1024 ** 3,
             "details": {"parameter_size": "14B", "quantization_level": "Q4_K_M"}},
            {"name": "llama3.2:latest", "size": 2 * 1024 ** 3,
             "details": {"parameter_size": "3B", "quantization_level": "Q8_0"}},
        ]
        ctx = _make_ctx(koan_root, instance_dir)
        patches = _patch_ollama(models=models)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = handle(ctx)
        assert "Models (2)" in result
        assert "qwen2.5-coder:14b" in result
        assert "14B" in result
        assert "Q4_K_M" in result
        assert "llama3.2:latest" in result

    def test_shows_running_models(self, koan_root, instance_dir):
        models = [{"name": "qwen2.5-coder:14b", "size": 9 * 1024 ** 3, "details": {}}]
        running = [{"name": "qwen2.5-coder:14b"}]
        ctx = _make_ctx(koan_root, instance_dir)
        patches = _patch_ollama(models=models, running=running)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = handle(ctx)
        assert "Loaded: qwen2.5-coder:14b" in result

    def test_unknown_version(self, koan_root, instance_dir):
        models = [{"name": "test:latest", "size": 1024 ** 3, "details": {}}]
        ctx = _make_ctx(koan_root, instance_dir)
        patches = _patch_ollama(version=None, models=models)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = handle(ctx)
        assert "unknown" in result

    def test_works_with_ollama_claude_provider(self, koan_root, instance_dir):
        models = [{"name": "test:latest", "size": 1024 ** 3, "details": {}}]
        ctx = _make_ctx(koan_root, instance_dir)
        patches = _patch_ollama(provider="ollama-claude", models=models)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = handle(ctx)
        assert "v0.16.0" in result
        assert "Models (1)" in result

    def test_works_with_ollama_provider(self, koan_root, instance_dir):
        models = [{"name": "test:latest", "size": 1024 ** 3, "details": {}}]
        ctx = _make_ctx(koan_root, instance_dir)
        patches = _patch_ollama(provider="ollama", models=models)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = handle(ctx)
        assert "running" in result


# ---------------------------------------------------------------------------
# handle — configured model check
# ---------------------------------------------------------------------------

class TestHandleConfiguredModel:
    def test_configured_model_ready(self, koan_root, instance_dir):
        models = [{"name": "qwen2.5-coder:14b", "size": 9 * 1024 ** 3, "details": {}}]
        ctx = _make_ctx(koan_root, instance_dir)
        patches = _patch_ollama(models=models)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patch("app.ollama_client.is_model_available", return_value=True), \
             patch("app.provider.local.LocalLLMProvider._get_default_model", return_value="qwen2.5-coder:14b"):
            result = handle(ctx)
        assert "Configured model: qwen2.5-coder:14b" in result
        assert "ready" in result

    def test_configured_model_not_pulled(self, koan_root, instance_dir):
        models = [{"name": "llama3.2:latest", "size": 2 * 1024 ** 3, "details": {}}]
        ctx = _make_ctx(koan_root, instance_dir)
        patches = _patch_ollama(models=models)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patch("app.ollama_client.is_model_available", return_value=False), \
             patch("app.provider.local.LocalLLMProvider._get_default_model", return_value="qwen2.5-coder:14b"):
            result = handle(ctx)
        assert "not pulled" in result
        assert "ollama pull qwen2.5-coder:14b" in result

    def test_no_configured_model(self, koan_root, instance_dir):
        models = [{"name": "test:latest", "size": 1024 ** 3, "details": {}}]
        ctx = _make_ctx(koan_root, instance_dir)
        patches = _patch_ollama(models=models)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patch("app.provider.local.LocalLLMProvider._get_default_model", return_value=""):
            result = handle(ctx)
        assert "Configured model" not in result
