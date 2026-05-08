#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/.codex"

mkdir -p "$TARGET_DIR"

if [[ -f "$TARGET_DIR/config.toml" ]]; then
  cp "$TARGET_DIR/config.toml" "$TARGET_DIR/config.toml.bak"
fi

if [[ -f "$TARGET_DIR/auth.json" ]]; then
  cp "$TARGET_DIR/auth.json" "$TARGET_DIR/auth.json.bak"
fi

cp "$SCRIPT_DIR/config.toml" "$TARGET_DIR/config.toml"
cp "$SCRIPT_DIR/auth.json" "$TARGET_DIR/auth.json"

echo "已复制配置到 $TARGET_DIR"
