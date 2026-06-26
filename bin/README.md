# Community CLI wrappers (`bin/`)

These are small, self-contained wrapper scripts that make Koan's **Claude
provider** drive an alternative model backend, without any Koan code changes.

## How they plug in

Each wrapper is a `claude`-compatible executable. Point Koan at one with:

```bash
# .env
KOAN_CLAUDE_CLI_PATH=/absolute/path/to/koan/bin/<wrapper>
```

Koan's `ClaudeProvider` reads `KOAN_CLAUDE_CLI_PATH` (see
`koan/app/provider/claude.py`) and invokes it exactly like the real `claude`
CLI, e.g. `-p "<prompt>" --model <name> --output-format json --verbose …`.

## The contract every wrapper must honor

1. Accept the full Claude CLI argument vector unchanged.
2. If the backend selects models differently, pull `--model` (both
   `--model X` and `--model=X`) out of the vector and re-emit it in the
   backend's form; forward all other args verbatim (the prompt may contain
   spaces/newlines — use a bash array, never re-split).
3. `exec` the backend so exit codes, stdio, and signals pass through
   (Koan relies on these for JSON parsing, quota detection, and its
   stagnation/timeout killer).
4. Fail fast with a non-zero exit and a clear stderr message if a required
   dependency is missing, so Koan classifies it as a real error.
5. Re-apply the exec bit after clone if your umask strips it:
   `chmod +x bin/<wrapper>`.

## Available wrappers

| Wrapper | Backend | Setup guide |
|---------|---------|-------------|
| `oc-claude` | OpenCode Go (via `ocgo` proxy) | [docs/providers/opencode.md](../docs/providers/opencode.md) |

## Adding a new flavor

Copy `oc-claude`, adjust the dependency check and the backend exec line, and
add a matching `docs/providers/<backend>.md` setup guide plus a row in the
table above. Planned future flavors include `ollama-claude` (local Ollama) and
an OpenAI variant.
