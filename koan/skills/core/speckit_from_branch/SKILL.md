---
name: speckit_from_branch
scope: core
group: code
emoji: 🌿
description: "Resume spec-kit from a human-validated spec on a branch (skip specify, run plan -> tasks -> implement -> review -> CI -> PR)"
version: 0.1.0
audience: hybrid
model_key: mission
github_enabled: true
github_context_aware: true
commands:
  - name: speckit_from_branch
    description: "Run spec-kit plan onward from a human-authored spec already pushed to a branch"
    usage: "/speckit_from_branch <repo-id> <branch-name>"
---

> **Scaffold (Phase 1).** This skill is under construction. The bridge handler
> (`handler.py`), agent-loop runner (`speckit_from_branch_runner.py`), and
> orchestration prompt (`prompts/speckit.md`) are added in the Foundational +
> US5 phases per `specs/001-speckit-native-support/tasks.md`. Until then
> `/speckit_from_branch` is a placeholder.
