#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEMO_DB="$ROOT/data/ai_trader_demo.db"
PYTHON="$ROOT/backend/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "缺少后端虚拟环境，请先按 README 完成首次安装。"
  exit 1
fi

echo "正在重置独立演示工作区（${DEMO_DB}）..."
"$ROOT/scripts/stop.sh" >/dev/null 2>&1 || true
DATABASE_URL="sqlite:///${DEMO_DB}" "$PYTHON" "$ROOT/scripts/seed_demo.py"
"$ROOT/scripts/start.sh"
