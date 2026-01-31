# Kōan

An autonomous background agent that uses idle Claude Max quota to work on your projects.

Kōan runs as a loop on your local machine: it pulls missions from a shared repo, executes them via Claude Code CLI, writes reports, and communicates with you via Telegram.

**The agent proposes. The human decides.** No unsupervised code modifications.

## How It Works

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Telegram    │◄───►│  bridge.py   │◄───►│ instance/        │
│  (Human)     │     │              │     │   missions.md    │
└─────────────┘     └──────────────┘     │   outbox.md      │
                                         └────────┬─────────┘
                                                  │
                                         ┌────────▼─────────┐
                                         │   run.sh         │
                                         │  (Claude CLI     │
                                         │    loop)         │
                                         └────────┬─────────┘
                                                  │
                                         ┌────────▼─────────┐
                                         │  Your Code       │
                                         │  (read-only)     │
                                         └──────────────────┘
```

## Repo Structure

```
koan/
  run.sh                    # App — main loop launcher
  bridge.py                 # App — Telegram bridge
  README.md
  INSTALL.md
  LICENSE
  instance.example/         # Template — copy to instance/ to start
    soul.md                 #   Agent personality
    config.yaml             #   Budget, paths, Telegram config
    missions.md             #   Task queue
    usage.md                #   Pasted /usage data
    outbox.md               #   Bot → Telegram queue
    mission-report.md       #   Report template
    memory/                 #   Persistent context
    journal/                #   Daily logs
  instance/                 # Your data (gitignored)
```

**Design principle:** App code (`run.sh`, `bridge.py`) is generic and open source. Instance data (`instance/`) is private to each user. Fork the repo, write your own soul.

See [INSTALL.md](INSTALL.md) for setup instructions.

## License

AGPL-3.0 — See [LICENSE](LICENSE).
