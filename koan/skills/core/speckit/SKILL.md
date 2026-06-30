---
name: speckit
scope: core
group: code
emoji: 📋
description: "Run a spec-kit pipeline (specify -> plan -> tasks -> implement) for a goal or tracker issue, then best-effort review/CI and a draft PR"
version: 0.1.0
audience: hybrid
model_key: mission
github_enabled: true
github_context_aware: true
commands:
  - name: speckit
    description: "Run the spec-kit SDD pipeline for a project goal or tracker issue"
    usage: "/speckit <project> <goal> | /speckit <issue-url> [repo:.. branch:..]"
---

> **Scaffold (Phase 1).** This skill is under construction. The bridge handler
> (`handler.py`), agent-loop runner (`speckit_runner.py`), and orchestration
> prompt (`prompts/speckit.md`) are added in the Foundational + US1 phases per
> `specs/001-speckit-native-support/tasks.md`. Until then `/speckit` is a
> placeholder.
