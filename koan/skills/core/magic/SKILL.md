---
name: magic
scope: core
description: Instant creative exploration of a random project
version: 1.0.0
commands:
  - name: magic
    description: Instantly explore a random project and suggest ideas
    usage: |
      /magic

      Picks a random project, runs a quick single-turn Claude call,
      and returns creative improvement ideas directly in the chat.
      Unlike /ai (deep, mission-queued), /magic is instant and lightweight.
worker: true
handler: handler.py
---
