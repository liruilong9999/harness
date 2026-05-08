#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "正在启动 DeepSeek 本地代理，监听 127.0.0.1:50010"
python3 deepseek_proxy.py --host 127.0.0.1 --port 50010
