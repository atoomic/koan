---
name: ollama
scope: core
description: Ollama server status, model listing, and model pulling
version: 1.1.0
audience: bridge
worker: true
commands:
  - name: ollama
    description: Show Ollama server status and models. Use /ollama pull <model> to download.
    aliases: [llama]
handler: handler.py
---
