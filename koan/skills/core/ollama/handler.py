"""Kōan ollama skill — server status, model listing, model pulling."""


def _format_size(size_bytes):
    """Format bytes to human-readable size."""
    if not size_bytes:
        return ""
    gb = size_bytes / (1024 ** 3)
    if gb >= 1.0:
        return f"{gb:.1f}GB"
    mb = size_bytes / (1024 ** 2)
    return f"{mb:.0f}MB"


def handle(ctx):
    """Handle /ollama command — dispatch to subcommands."""
    args = (ctx.args or "").strip()

    if args.startswith("pull "):
        return _handle_pull(ctx, args[5:].strip())
    if args == "pull":
        return "Usage: /ollama pull <model>\nExample: /ollama pull llama3.3"

    return _handle_status(ctx)


def _handle_pull(ctx, model_name):
    """Pull a model from the Ollama registry."""
    from app.ollama_client import is_model_available, is_server_ready, pull_model
    from app.provider import get_provider_name

    provider = get_provider_name()
    if provider not in ("local", "ollama", "ollama-claude"):
        return f"Ollama not active (provider: {provider})"

    if not model_name:
        return "Usage: /ollama pull <model>\nExample: /ollama pull llama3.3"

    if not is_server_ready():
        return "Ollama server not responding. Start with: ollama serve"

    # Check if already available
    if is_model_available(model_name):
        return f"Model '{model_name}' is already available locally."

    ok, detail = pull_model(model_name)
    if ok:
        return f"Model '{model_name}' pulled successfully."
    return f"Failed to pull '{model_name}': {detail}"


def _handle_status(ctx):
    """Show server status and models."""
    from app.ollama_client import (
        get_version,
        is_server_ready,
        list_models,
        list_running_models,
    )
    from app.provider import get_provider_name

    provider = get_provider_name()
    if provider not in ("local", "ollama", "ollama-claude"):
        return f"Ollama not active (provider: {provider})"

    lines = []

    # Server health
    ready = is_server_ready()
    if not ready:
        lines.append("Ollama server: not responding")
        lines.append("  Start with: ollama serve")
        return "\n".join(lines)

    version = get_version() or "unknown"
    lines.append(f"Ollama server: running (v{version})")

    # Available models
    models = list_models()
    if not models:
        lines.append("\nNo models pulled. Run: /ollama pull <model>")
        return "\n".join(lines)

    lines.append(f"\nModels ({len(models)}):")
    for m in models:
        name = m.get("name", m.get("model", "unknown"))
        size = _format_size(m.get("size", 0))
        details = m.get("details", {})
        param_size = details.get("parameter_size", "")
        quant = details.get("quantization_level", "")

        parts = [f"  {name}"]
        if param_size:
            parts.append(f"({param_size})")
        if quant:
            parts.append(f"[{quant}]")
        if size:
            parts.append(size)
        lines.append(" ".join(parts))

    # Running models
    running = list_running_models()
    if running:
        names = [r.get("name", r.get("model", "?")) for r in running]
        lines.append(f"\nLoaded: {', '.join(names)}")

    # Show configured model
    try:
        configured = None
        if provider == "ollama-claude":
            from app.provider.ollama_claude import OllamaClaudeProvider
            p = OllamaClaudeProvider()
            configured = p._get_model()
        else:
            from app.provider.local import LocalLLMProvider
            p = LocalLLMProvider()
            configured = p._get_default_model()
        if configured:
            from app.ollama_client import is_model_available
            available = is_model_available(configured)
            status = "ready" if available else "not pulled"
            lines.append(f"\nConfigured model: {configured} ({status})")
            if not available:
                lines.append(f"  Run: /ollama pull {configured}")
    except Exception:
        pass

    return "\n".join(lines)
