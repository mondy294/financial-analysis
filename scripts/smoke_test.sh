#!/usr/bin/env bash
# 第 4 步能力冒烟脚本
# 用法：bash scripts/smoke_test.sh
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate
export PYTHONPATH=.

echo "==> 1. 初始化数据库"
python -m quant_system.cli init-db

echo "==> 2. 系统体检"
python -m quant_system.cli doctor

echo "==> 3. 股票池"
python -m quant_system.cli pool list

echo "==> 4. HS300 成分（当前为空）"
python -m quant_system.cli pool show HS300

echo "==> 5. 数据库表清单"
sqlite3 data_cache/quant.db ".tables"

echo "==> 6. 种子数据核对"
sqlite3 data_cache/quant.db "SELECT code, name FROM strategy;"

echo ""
echo "✓ 第 4 步冒烟通过。下一步（第 5 步）会接 akshare，你就能真拉 A 股数据了。"
