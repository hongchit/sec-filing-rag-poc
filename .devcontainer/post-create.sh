#!/usr/bin/env bash
set -euo pipefail

readonly workspace_dir="${1:?workspace directory is required}"

sudo chown vscode:vscode /home/vscode/.codex

# Fix: "fatal: detected dubious ownership in repository" error when running git commands in the devcontainer
if ! git config --global --get-all safe.directory |
  grep -Fqx -- "${workspace_dir}"; then
  git config --global --add safe.directory "${workspace_dir}"
fi

# Enable the tracked staged-secret scan for this checkout.
git -C "${workspace_dir}" config --local core.hooksPath .githooks

uv sync --frozen --all-packages
cargo install httpgenerator --version 1.1.0 --locked
npm --prefix frontend ci --no-audit --no-fund
npm install --global --no-audit --no-fund \
  @openai/codex
codex --version
