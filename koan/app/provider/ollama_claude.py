"""Ollama-Claude provider: Claude CLI routed through a local Ollama backend.

Uses the real Claude Code CLI with ANTHROPIC_BASE_URL pointed at an
Anthropic-compatible proxy (LiteLLM, ollama-cloud-proxy, etc.) that
translates requests to the local Ollama server.

This gives full Claude CLI feature parity (MCP, extended thinking,
tool sophistication) while running inference locally.

Configuration (config.yaml):
    cli_provider: "ollama-claude"
    ollama_claude:
        base_url: "http://localhost:11434"   # Proxy endpoint
        api_key: "ollama"                     # Dummy key
        model: "llama3.3"                     # Required
"""

import os
from typing import Dict, List, Tuple

from app.provider.claude import ClaudeProvider


class OllamaClaudeProvider(ClaudeProvider):
    """Claude CLI provider routed through a local Ollama backend.

    Extends ClaudeProvider — inherits all flag building (--model,
    --allowedTools, --mcp-config, etc.). The only difference is
    environment variables injected into subprocess invocations.
    """

    name = "ollama-claude"

    def _get_config(self) -> dict:
        """Get ollama_claude config section from config.yaml."""
        try:
            from app.utils import load_config
            config = load_config()
            return config.get("ollama_claude", {})
        except Exception:
            return {}

    def _get_setting(self, env_key: str, config_key: str, default: str = "") -> str:
        """Resolve a setting: env var > config.yaml > default."""
        env_val = os.environ.get(env_key, "")
        if env_val:
            return env_val
        return self._get_config().get(config_key, default)

    def _get_base_url(self) -> str:
        return self._get_setting(
            "KOAN_OLLAMA_CLAUDE_BASE_URL", "base_url"
        )

    def _get_model(self) -> str:
        return self._get_setting(
            "KOAN_OLLAMA_CLAUDE_MODEL", "model"
        )

    def _get_api_key(self) -> str:
        return self._get_setting(
            "KOAN_OLLAMA_CLAUDE_API_KEY", "api_key", "ollama"
        )

    def _get_auth_token(self) -> str:
        return self._get_setting(
            "KOAN_OLLAMA_CLAUDE_AUTH_TOKEN", "auth_token"
        )

    def _validate(self) -> None:
        """Validate required configuration, raising ValueError if missing."""
        base_url = self._get_base_url()
        if not base_url:
            raise ValueError(
                "ollama-claude provider requires 'base_url' — "
                "set KOAN_OLLAMA_CLAUDE_BASE_URL or "
                "ollama_claude.base_url in config.yaml"
            )
        model = self._get_model()
        if not model:
            raise ValueError(
                "ollama-claude provider requires 'model' — "
                "set KOAN_OLLAMA_CLAUDE_MODEL or "
                "ollama_claude.model in config.yaml"
            )

    def is_available(self) -> bool:
        """Check if Claude CLI is installed and config is valid."""
        if not super().is_available():
            return False
        try:
            self._validate()
            return True
        except ValueError:
            return False

    def get_env(self) -> Dict[str, str]:
        """Return Anthropic env vars to route Claude CLI through Ollama.

        These are merged into the subprocess environment by cli_exec.py.
        """
        self._validate()

        env: Dict[str, str] = {
            "ANTHROPIC_BASE_URL": self._get_base_url(),
            "ANTHROPIC_API_KEY": self._get_api_key(),
            "ANTHROPIC_MODEL": self._get_model(),
        }

        auth_token = self._get_auth_token()
        if auth_token:
            env["ANTHROPIC_AUTH_TOKEN"] = auth_token

        # Optional model overrides for Haiku/Sonnet routing
        config = self._get_config()
        sonnet_model = config.get("sonnet_model", "")
        if sonnet_model:
            env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = sonnet_model
        haiku_model = config.get("haiku_model", "")
        if haiku_model:
            env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = haiku_model

        return env

    def check_quota_available(self, project_path: str, timeout: int = 15) -> Tuple[bool, str]:
        """No quota concept with local models — always available."""
        return True, ""

    def build_model_args(self, model: str = "", fallback: str = "") -> List[str]:
        """Build model args, using configured Ollama model as default.

        When no explicit model is passed, uses the ollama-claude model
        config. This ensures the Claude CLI sends the right model name
        to the proxy.
        """
        effective_model = model or self._get_model()
        flags: List[str] = []
        if effective_model:
            flags.extend(["--model", effective_model])
        # Fallback model not meaningful with local inference
        return flags
