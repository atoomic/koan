# Installation

## Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- Python 3.8+ with `requests` (`pip install requests`)
- A Telegram account

## Setup

### 1. Clone and create your instance

```bash
git clone https://github.com/sukria/koan.git
cd koan
cp -r instance.example instance
```

The `instance/` directory is your private data — it's gitignored and never pushed to the Kōan repo. You can version it in a separate private repo if you want persistence.

### 2. Edit your instance

```bash
$EDITOR instance/config.yaml    # Set your project path
$EDITOR instance/soul.md        # Write your agent's personality
```

### 3. Create a Telegram bot

1. Open Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow the prompts
3. Copy the bot token
4. Send any message to your new bot
5. Get your chat ID: `curl https://api.telegram.org/bot<TOKEN>/getUpdates`

### 4. Set environment variables

```bash
export KOAN_TELEGRAM_TOKEN="your-bot-token"
export KOAN_TELEGRAM_CHAT_ID="your-chat-id"
export KOAN_PROJECT_PATH="/path/to/your/project"
```

### 5. Run

```bash
# Terminal 1: Telegram bridge
python3 bridge.py

# Terminal 2: Agent loop
./run.sh
```

## Optional environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KOAN_MAX_RUNS` | 20 | Maximum runs per session |
| `KOAN_INTERVAL` | 300 | Seconds between runs |
| `KOAN_BRIDGE_INTERVAL` | 10 | Telegram poll interval (seconds) |
