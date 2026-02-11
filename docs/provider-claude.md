# Claude Code CLI Provider

The Claude Code CLI is Koan's default and most capable provider. It gives
the agent full access to Claude's reasoning, tool use, and multi-turn
conversation capabilities.

## Quick Setup

### 1. Install Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
```

Verify the installation:

```bash
claude --version
```

### 2. Authenticate

```bash
claude
```

Follow the interactive login flow. Once authenticated, your credentials
are stored in `~/.claude/` and persist across sessions.

### 3. Configure Koan

Claude is the default provider — no extra configuration is needed.
If you've previously changed the provider, set it back:

In `config.yaml`:

```yaml
cli_provider: "claude"
```

Or via environment variable (in `.env`):

```bash
KOAN_CLI_PROVIDER=claude
```

### 4. Verify

```bash
claude -p "Hello, what model are you?"
```

If this returns a response, you're ready to run Koan.

## Model Configuration

Koan uses different models for different tasks. Configure them in
`config.yaml`:

```yaml
models:
  mission: ""              # Main mission execution (empty = subscription default)
  chat: ""                 # Telegram/dashboard chat responses
  lightweight: "haiku"     # Low-cost calls: formatting, classification
  fallback: "sonnet"       # Fallback when primary model is overloaded
  review_mode: ""          # Override model for REVIEW mode
```

Empty strings use your subscription's default model. Common overrides:

| Use Case | Recommended Model | Why |
|----------|------------------|-----|
| Complex missions | `opus` | Best reasoning for architectural work |
| Cost-efficient missions | `sonnet` | Good balance for routine tasks |
| Chat responses | `haiku` | Fast, cheap for quick answers |
| Code review | `sonnet` | Sufficient for review, saves quota |

### Per-Project Model Overrides

Different projects can use different models. In `projects.yaml`:

```yaml
projects:
  critical-backend:
    path: "/path/to/backend"
    models:
      mission: "opus"         # Use Opus for complex backend work
      review_mode: "sonnet"   # Sonnet for reviews

  small-library:
    path: "/path/to/lib"
    models:
      mission: "sonnet"       # Sonnet is sufficient here
```

## Tool Configuration

Control which tools the agent can use:

```yaml
tools:
  chat: ["Read", "Glob", "Grep"]                          # Read-only for Telegram
  mission: ["Read", "Glob", "Grep", "Edit", "Write", "Bash"]  # Full access for missions
```

Available tools: `Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`.

### Per-Project Tool Restrictions

Restrict tools for sensitive repos in `projects.yaml`:

```yaml
projects:
  vendor-lib:
    path: "/path/to/vendor"
    tools:
      mission: ["Read", "Glob", "Grep"]  # Read-only — no modifications
```

## Advanced Configuration

### MCP (Model Context Protocol) Servers

Claude Code supports MCP servers for extended capabilities (browser,
databases, APIs):

```yaml
mcp:
  - "/path/to/mcp-config.json"
```

### Max Turns

The `max_turns` setting controls how many tool-use rounds Claude gets
per invocation. Koan sets sensible defaults per context (missions get
more turns than chat). You generally don't need to change this.

### Output Format

Claude Code supports JSON output (`--output-format json`) which Koan
uses internally for structured mission results. This is handled
automatically.

### Fallback Model

When the primary model is rate-limited or unavailable, Koan falls back
to the configured fallback model:

```yaml
models:
  fallback: "sonnet"  # Used when primary model is overloaded
```

This is a Claude-specific feature — other providers don't support it.

## Troubleshooting

### "claude: command not found"

The CLI is not installed or not in your PATH.

```bash
npm install -g @anthropic-ai/claude-code
```

If installed via a version manager (nvm, fnm), make sure the right
Node.js version is active.

### Authentication expired

Re-authenticate:

```bash
claude
```

Or check your credentials:

```bash
ls ~/.claude/
```

### Rate limiting / quota exhaustion

Koan monitors quota and pauses automatically when limits are approached.
Check your usage:

```bash
# Via Telegram
/quota

# Or check Claude's stats
claude usage
```

### "Reached max turns" errors

If you see this in logs, the agent ran out of allowed tool-use rounds.
This is normal for complex tasks — Koan handles it gracefully and
reports partial results.
