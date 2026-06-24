# Environment-variable-only deployment

Kōan does not require a `.env` file. On platforms that inject configuration as
process environment variables — Railway, Docker, Kubernetes, systemd
`Environment=` — you can run Kōan without ever writing a `.env`.

## How it works

When `KOAN_ROOT` and the other `KOAN_*` settings are present in the process
environment, the onboarding `Initialize instance` step creates an **empty**
`.env` and proceeds (it does not fail when `env.example` is missing).
`load_dotenv()` then layers that file on top of `os.environ` using
`setdefault`, so injected environment variables always take precedence.

`env.example` is only used as a template for interactive local setup and is
optional in containerized / PaaS deploys. Likewise, `create_env_file()` writes
an empty `.env` rather than aborting when no template is shipped in the image.

## Precedence

1. Process environment variables (highest priority — always win).
2. Values in `.env` (only fill gaps via `os.environ.setdefault`).

This means you can safely set everything via environment variables and leave
`.env` empty (or absent until onboarding creates it).
