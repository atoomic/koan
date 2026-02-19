"""Ollama REST API client for Kōan.

Wraps the native Ollama HTTP API (not the OpenAI-compatible /v1 endpoint)
for server management: health checks, model listing, version detection.

The Ollama API runs at http://localhost:11434 by default.
Endpoints used:
  GET  /api/tags     — list available models
  GET  /api/ps       — list running/loaded models
  GET  /api/version  — server version info
  HEAD /              — lightweight health probe

Reference: https://github.com/ollama/ollama/blob/main/docs/api.md
"""

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def _get_ollama_host(base_url: str = "") -> str:
    """Derive the Ollama host from a base_url or environment.

    The base_url may be an OpenAI-compat URL like http://localhost:11434/v1.
    We strip the /v1 suffix to get the native Ollama API root.

    Falls back to OLLAMA_HOST env var, then DEFAULT_OLLAMA_HOST.
    """
    import os

    if base_url:
        host = base_url.rstrip("/")
        # Strip OpenAI-compat suffix
        for suffix in ("/v1", "/v1/"):
            if host.endswith(suffix.rstrip("/")):
                host = host[: -len(suffix.rstrip("/"))]
                break
        return host

    return os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)


def _api_get(host: str, path: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Perform a GET request to the Ollama API.

    Returns the parsed JSON response.
    Raises RuntimeError on connection or HTTP errors.
    """
    url = f"{host.rstrip('/')}{path}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"Ollama API error {e.code} on {path}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot connect to Ollama at {host}: {e.reason}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Ollama API request failed: {e}") from e


def is_server_ready(base_url: str = "", timeout: float = 3.0) -> bool:
    """Check if the Ollama server is responding.

    Uses a lightweight HEAD request to the root endpoint.
    Returns True if the server responds (any HTTP status), False otherwise.
    """
    host = _get_ollama_host(base_url)
    url = f"{host.rstrip('/')}/"
    req = urllib.request.Request(url, method="HEAD")

    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        # Even a 4xx/5xx means the server is running
        return True
    except Exception:
        return False


def get_version(base_url: str = "", timeout: float = 5.0) -> Optional[str]:
    """Get the Ollama server version string.

    Returns the version (e.g. "0.16.0") or None if unreachable.
    """
    host = _get_ollama_host(base_url)
    try:
        data = _api_get(host, "/api/version", timeout=timeout)
        return data.get("version", None)
    except RuntimeError:
        return None


def list_models(base_url: str = "", timeout: float = 5.0) -> List[Dict[str, Any]]:
    """List all locally available models.

    Returns a list of model dicts with keys like:
        name, model, modified_at, size, digest, details
    Returns empty list if server is unreachable.
    """
    host = _get_ollama_host(base_url)
    try:
        data = _api_get(host, "/api/tags", timeout=timeout)
        return data.get("models", [])
    except RuntimeError:
        return []


def list_running_models(base_url: str = "", timeout: float = 5.0) -> List[Dict[str, Any]]:
    """List currently loaded/running models.

    Returns a list of model dicts with runtime info (size_vram, etc.).
    Returns empty list if server is unreachable.
    """
    host = _get_ollama_host(base_url)
    try:
        data = _api_get(host, "/api/ps", timeout=timeout)
        return data.get("models", [])
    except RuntimeError:
        return []


def is_model_available(model_name: str, base_url: str = "", timeout: float = 5.0) -> bool:
    """Check if a specific model is pulled and available locally.

    Performs a fuzzy match: "qwen2.5-coder:14b" matches "qwen2.5-coder:14b"
    and "qwen2.5-coder" matches "qwen2.5-coder:latest".

    Args:
        model_name: Model name to check (e.g. "qwen2.5-coder:14b").
        base_url: Ollama server URL.
        timeout: Request timeout.

    Returns True if the model is available.
    """
    models = list_models(base_url=base_url, timeout=timeout)
    return _model_matches_any(model_name, models)


def _model_matches_any(model_name: str, models: List[Dict[str, Any]]) -> bool:
    """Check if model_name matches any model in the list.

    Handles Ollama naming conventions:
    - Exact match on 'name' or 'model' field
    - "foo" matches "foo:latest"
    - "foo:tag" matches "foo:tag"
    """
    if not model_name:
        return False

    # Normalize: add :latest if no tag specified
    query = model_name.strip()
    query_with_tag = query if ":" in query else f"{query}:latest"

    for m in models:
        for key in ("name", "model"):
            val = m.get(key, "")
            if not val:
                continue
            # Exact match
            if val == query or val == query_with_tag:
                return True
            # Model field without tag matches query without tag
            base = val.split(":")[0]
            if base == query.split(":")[0] and ":" not in query:
                return True
    return False


def get_model_info(model_name: str, base_url: str = "", timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    """Get info about a specific model from the local model list.

    Returns the model dict if found, None otherwise.
    """
    models = list_models(base_url=base_url, timeout=timeout)
    if not model_name:
        return None

    query = model_name.strip()
    query_with_tag = query if ":" in query else f"{query}:latest"

    for m in models:
        for key in ("name", "model"):
            val = m.get(key, "")
            if val == query or val == query_with_tag:
                return m
            base = val.split(":")[0]
            if base == query.split(":")[0] and ":" not in query:
                return m
    return None


def check_server_and_model(
    model_name: str, base_url: str = "", timeout: float = 5.0
) -> Tuple[bool, str]:
    """Combined check: server reachable + model available.

    Returns (ok, detail) where:
        ok=True, detail="" — ready to use
        ok=False, detail="..." — human-readable error message
    """
    host = _get_ollama_host(base_url)

    if not is_server_ready(base_url=base_url, timeout=timeout):
        return False, f"Ollama server not responding at {host}"

    if not model_name:
        return False, "No model configured (set KOAN_LOCAL_LLM_MODEL or local_llm.model in config.yaml)"

    if not is_model_available(model_name, base_url=base_url, timeout=timeout):
        return False, f"Model '{model_name}' not found locally. Run: ollama pull {model_name}"

    return True, ""


def format_model_list(base_url: str = "", timeout: float = 5.0) -> str:
    """Format a human-readable list of available models.

    Returns a multi-line string suitable for Telegram/console display.
    """
    models = list_models(base_url=base_url, timeout=timeout)
    if not models:
        return "No models available (is Ollama running?)"

    lines = []
    for m in models:
        name = m.get("name", m.get("model", "unknown"))
        size_bytes = m.get("size", 0)
        size_gb = size_bytes / (1024 ** 3) if size_bytes else 0
        details = m.get("details", {})
        param_size = details.get("parameter_size", "")
        quant = details.get("quantization_level", "")

        parts = [name]
        if param_size:
            parts.append(f"({param_size})")
        if quant:
            parts.append(f"[{quant}]")
        if size_gb >= 0.1:
            parts.append(f"{size_gb:.1f}GB")
        lines.append(" ".join(parts))

    return "\n".join(lines)
