---
type: doc
title: "CI runners (webpros-sandbox self-hosted)"
description: "Why every GitHub Actions job in this fork pins runs-on to the self-hosted `webpros-sandbox` runner group instead of a GitHub-hosted label, the exact YAML form to use, the exemptions, and the runner-image gotchas to watch for."
tags: [operations, ci]
created: 2026-07-28
updated: 2026-07-28
---

# CI runners (webpros-sandbox self-hosted)

This fork of Kōan is hosted at `webpros-sandbox/koan-bot`, an internal repository
in the `webpros-sandbox` GitHub organization. That org supplies its own
self-hosted runner fleet, and **GitHub-hosted runners are not the default there** —
org policy is that CI runs on the org's own capacity.

## The rule

**Every job must run on the self-hosted `webpros-sandbox` runner group.** Never a
GitHub-hosted label (`ubuntu-latest`, `windows-latest`, `macos-latest`, …).

```yaml
jobs:
  my-job:
    runs-on:
      group: webpros-sandbox
    steps: ...
```

Use the **runner-group** mapping form (`runs-on: { group: webpros-sandbox }`), not
the bare-label form (`runs-on: webpros-sandbox`) and not the AWS CodeBuild
ephemeral-label form (`codebuild-runner-webpros-sandbox-default-${{ github.run_id }}-…`).
All three appear across the org, but the group form is the one documented as the
org-wide hard requirement and the one with a consistently green run history — so
it is the single form used here.

## Exemptions

Two job shapes legitimately have no `runs-on`:

- **Reusable-workflow calls** — a job that uses `uses:` instead of `steps:`
  inherits the callee's runner. `publish-container.yml::publish` and
  `release.yml::publish-image` both call `docker-publish.yml`, whose own
  `publish` job carries the pin.
- **Composite actions** (`.github/actions/*`, `runs: { using: composite }`) have
  no jobs at all. This repo currently ships none.

## Where the pin lives

All nine runner-bearing jobs across the eight workflows:

| Workflow | Job(s) |
| --- | --- |
| `tests.yml` | `test`, `check-coverage` |
| `openapi.yml` | `drift` |
| `spec-change-guard.yml` | `spec-change-guard` |
| `wiki-sync.yml` | `wiki-sync` |
| `request-review.yml` | `assign` |
| `release.yml` | `release` |
| `publish-container.yml` | `validate` |
| `docker-publish.yml` | `publish` |

## Runner-image gotchas

The `webpros-sandbox` image is Debian/Ubuntu-based with `sudo`, but it is **leaner
than a GitHub-hosted image**. Things that are free on `ubuntu-latest` may need an
explicit setup step:

- **No preinstalled Node.** Any job that shells out to `node` in a `run:` step must
  add `actions/setup-node` first. Note this does *not* affect JavaScript actions
  themselves (`actions/checkout`, `actions/setup-python`, `actions/github-script`) —
  the Actions runner ships its own bundled Node to execute them, so they work
  unchanged. Kōan's workflows contain no `run: node …` steps.
- **Python comes from `actions/setup-python`, not the image.** The action downloads
  the requested interpreter into the runner tool cache on first use, including the
  prerelease 3.14 build that `tests.yml` and `openapi.yml` pin. Expect a slower
  first run per interpreter version while the cache warms.
- **`pnpm` needs `libatomic1`** installed before it runs (`sudo apt-get install -y
  libatomic1`). Not currently relevant — Kōan is a Python project — but it is the
  most common trip-up in the org and worth knowing if a Node toolchain is ever added.
- **Docker/Buildx availability is not guaranteed.** `docker-publish.yml` needs a
  working Docker daemon plus `docker/setup-buildx-action`, and its
  `cache-from/cache-to: type=gha` relies on the Actions cache service. Both
  container workflows are `workflow_dispatch` / `workflow_call` only, so this is
  not exercised on ordinary pushes and PRs — verify it deliberately the first time
  an image is published from this fork.

## Changing this

If a job ever genuinely needs a GitHub-hosted runner, that is a deliberate
exception, not a drive-by edit: say so in the PR body and explain why the
self-hosted fleet cannot serve it. Keep every other job on the group pin, so
"which runner does CI use" stays a single answer.
