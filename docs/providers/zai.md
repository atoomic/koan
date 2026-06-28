# Z.ai (GLM) via the Claude CLI

Run Koan's **default Claude provider** against a
[Z.ai](https://z.ai) subscription (GLM models) — without changing any Koan
code. Koan keeps invoking the Claude CLI; a committed wrapper, `bin/zai-claude`,
points that invocation at Z.ai's Anthropic-compatible endpoint and maps Koan's
model tiers to GLM models.

> Same mechanism as [OpenCode Go via the Claude CLI](opencode.md) and
> [Local Ollama via the Claude CLI](ollama-wrapper.md): a thin wrapper binary
> set via `KOAN_CLAUDE_CLI_PATH`. `cli_provider` stays `claude`.

Unlike those two wrappers, the backend here **is** the real `claude` binary —
there is no proxy or launcher in between. The wrapper only sets the Z.ai
endpoint/auth via env vars and translates model tiers, then `exec`s `claude`.

## Architecture

```
run.py ──spawn──> bin/zai-claude   (KOAN_CLAUDE_CLI_PATH)
                     │  loads Z.ai key, maps --model tiers -> GLM, exports env
                     ▼
                  claude <args>   (the real Claude Code CLI, on PATH)
                     │  ANTHROPIC_BASE_URL=api.z.ai  +  ANTHROPIC_AUTH_TOKEN
                     ▼
                  Z.ai ──> glm-4.5 / glm-5.2[1m] / ...
```

## Prerequisites

1. **A Z.ai account + API key** (from the Z.ai console).

2. **The Claude Code CLI installed and on PATH** — the wrapper execs the real
   `claude` binary, it does not bundle one:

   ```bash
   npm install -g @anthropic-ai/claude-code
   claude --version
   ```

## Provide the Z.ai key

The wrapper resolves the key in this order:

1. `$KOAN_ZAI_KEY` — the key value, read from `.env` (recommended).
2. `$KOAN_ROOT/.zai.key` — a file at the root of your Kōan instance containing
   just the key (whitespace/newlines are trimmed).

Put one of these in your `.env`:

```bash
KOAN_ZAI_KEY=sk-zai-...               # option A: key value
```

…or create the file:

```bash
printf 'sk-zai-...\n' > "$KOAN_ROOT/.zai.key"
chmod 600 "$KOAN_ROOT/.zai.key"
```

`.zai.key` is gitignored (see `.gitignore`) — but treat it like any other secret
and never commit it.

## Wire Koan to the wrapper

Point `KOAN_CLAUDE_CLI_PATH` at the committed wrapper in your `.env`:

```bash
KOAN_CLAUDE_CLI_PATH=/absolute/path/to/koan/bin/zai-claude
```

The wrapper is resolved by the Claude provider (see
[claude.md → Custom CLI Binary](claude.md#advanced-configuration)). No other
Koan config changes are required.

## Model selection — your config does not change

This is the key simplification: **keep using Anthropic tier names** in your Koan
config exactly as you would for a normal Claude subscription. The wrapper maps
each tier to a Z.ai GLM model:

| Koan tier (`--model`) | Z.ai model |
|-----------------------|------------|
| `haiku`               | `glm-4.5`  |
| `sonnet`              | `glm-5.2[1m]` |
| `opus`                | `glm-5.2[1m]` |

So your existing `config.yaml` works as-is:

```yaml
# config.yaml — identical to a standard Claude setup
models:
  default:
    mission: ""          # -> glm-5.2[1m]  (empty = default = sonnet tier)
    lightweight: "haiku" # -> glm-4.5      (cheap calls)
    fallback: "sonnet"   # -> glm-5.2[1m]
```

And per-project overrides in `projects.yaml` keep using tiers too:

```yaml
projects:
  heavy-repo:
    path: "/path/to/heavy-repo"
    models:
      mission: "opus"        # -> glm-5.2[1m]
      review_mode: "sonnet"  # -> glm-5.2[1m]
```

**Naming GLM models directly** also works: any `--model` value that is *not* a
tier alias (`haiku`/`sonnet`/`opus`) passes through unchanged. So this is
equally valid:

```yaml
models:
  claude:
    mission: "glm-5.2[1m]"
    lightweight: "glm-4.5"
    fallback: "glm-5.2[1m]"
```

### Overriding the tier → model mapping

Each tier is overridable via its `ANTHROPIC_DEFAULT_*_MODEL` env var (set in
`.env`). Useful when Z.ai ships a new model and you want to test it without
editing the wrapper:

```bash
ANTHROPIC_DEFAULT_SONNET_MODEL=glm-6.0
ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-4.8
```

These feed both the `--model` translation and the `ANTHROPIC_DEFAULT_*_MODEL`
exports, so Claude Code's internal tier selection stays consistent.

### Concurrency — tune the lightweight tier for headroom

Z.ai enforces per-model concurrency caps (see the rate-limits page on your
API-key dashboard). The defaults the wrapper ships with land on opposite
sides of that (values are plan-dependent — confirm on your dashboard):

| Tier | GLM model | Typical concurrency |
|------|-----------|---------------------|
| `haiku` (lightweight) | `glm-4.5` | low (~2) |
| `sonnet` / `opus` (mission) | `glm-5.2[1m]` | high (~10) |

The **lightweight tier is the bottleneck**: Claude Code reaches for it on
background / small calls, so under load it trips `429` first. A single Kōan
instance rarely exceeds a couple of concurrent lightweight calls, so the
default is fine until you run multiple instances or parallel subagents.

To raise headroom, point `haiku` at a higher-concurrency **text** model:

```bash
# .env — glm-4.5 is a text model with a high concurrency cap (~10)
ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-4.5
```

Pick a **text** model here, not a `V` variant (e.g. `glm-4.6V`) — the `V`
means vision/multimodal, and the lightweight tier (formatting, mission
picking, contemplation — all text-only) never sends images, so you'd pay for
capability and latency you don't use. Good text picks at a high concurrency
cap: `glm-4.5` (default choice), or `glm-5.1` if you'd trade cost for a
smarter lightweight model.

## Environment reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `KOAN_CLAUDE_CLI_PATH` | — | Set to the wrapper path in `.env` to activate it. |
| `KOAN_ZAI_KEY` | — | Z.ai API key value (highest priority). |
| `$KOAN_ROOT/.zai.key` | — | Fallback key file (read when `KOAN_ZAI_KEY` is unset). |
| `KOAN_ZAI_CLAUDE_BIN` | `claude` | The backend binary to `exec`. Override if your `claude` lives elsewhere. |
| `ANTHROPIC_BASE_URL` | `https://api.z.ai/api/anthropic` | Z.ai endpoint. Override only for a mirror/proxy. |
| `API_TIMEOUT_MS` | `9000000` (150 min) | Long per-request timeout for big missions. |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | `1000000` | Raised auto-compact window. |
| `ANTHROPIC_DEFAULT_HAIKU/SONNET/OPUS_MODEL` | `glm-4.5` / `glm-5.2[1m]` / `glm-5.2[1m]` | Override any tier's GLM model. |

## Caveats

- **`claude` must stay on PATH.** If the CLI is missing, every mission fails
  fast — the wrapper exits `127` with a `claude`-not-found message that Kōan
  surfaces as a real error. (The wrapper resolves the *real* `claude` binary on
  PATH; it is not named `claude` itself, so there is no recursion.)
- **Interactive shell functions are irrelevant here.** If you have a personal
  `claude-zai` / `claude-full` shell function for interactive use, it is *not*
  loaded in Kōan's non-interactive subprocess — the wrapper always finds the
  real `claude` binary.
- **Cost figures are Anthropic-priced.** Token *counts* survive, but any
  reported `cost_usd` is computed against Anthropic pricing and is approximate
  at best for GLM models. Treat cost numbers as unreliable here.
- **Re-apply exec bit after clone if needed.** Git preserves `+x`, but a
  restrictive umask may strip it: `chmod +x bin/zai-claude`.

## Verify

1. **Arg translation only (no API call, no quota spent)** — point the wrapper
   at a printer to confirm the tier mapping and env exports:

   ```bash
   cat > /tmp/zai-probe.sh <<'EOF'
   #!/usr/bin/env bash
   echo "ARGS: $*"
   echo "AUTH: ${ANTHROPIC_AUTH_TOKEN:+set}"
   echo "URL: $ANTHROPIC_BASE_URL"
   echo "HAIKU: $ANTHROPIC_DEFAULT_HAIKU_MODEL  SONNET: $ANTHROPIC_DEFAULT_SONNET_MODEL"
   EOF
   chmod +x /tmp/zai-probe.sh

   KOAN_ZAI_KEY=test KOAN_ZAI_CLAUDE_BIN=/tmp/zai-probe.sh \
     ./bin/zai-claude --model haiku --fallback-model sonnet -p "hi"
   # expect: ARGS: --model glm-4.5 --fallback-model glm-5.2[1m] -p hi
   ```

   `--model glm-5.2[1m]` (a real model id) should pass through unchanged.

2. **End-to-end in Kōan** — with `KOAN_CLAUDE_CLI_PATH` set and a valid key,
   queue a trivial mission and watch `make logs` confirm it reaches **Done**.
   `/status` shows the provider as `claude (zai-claude)`.
