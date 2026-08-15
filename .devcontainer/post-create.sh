#!/usr/bin/env bash
set -euo pipefail

sudo chown vscode:vscode /home/vscode/.codex

uv sync --frozen --all-packages
npm install --global --no-audit --no-fund \
  @openai/codex@0.145.0 \
  @fission-ai/openspec@1.6.0
codex --version
openspec --version
