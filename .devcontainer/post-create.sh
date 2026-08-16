#!/usr/bin/env bash
set -euo pipefail

sudo chown vscode:vscode /home/vscode/.codex

uv sync --frozen --all-packages
npm --prefix frontend ci --no-audit --no-fund
npm install --global --no-audit --no-fund \
  @openai/codex
codex --version
