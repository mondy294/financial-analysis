# quant_system - 个人 A 股量化分析系统

> 每日收盘后自动拉取 A 股数据、计算技术与基本面指标、跑策略、生成推荐日报。**只做分析，不做交易。**

---

## 特性

- **数据源**：akshare（免费、无 token）
- **数据库**：SQLite（默认，零部署）/ PostgreSQL（配置切换）
- **技术指标**：pandas-ta（纯 Python，无编译）
- **策略**：突破、趋势、低估成长（可扩展）
- **评分**：技术 40 + 资金 30 + 基本面 30 三维加权
- **数据质量**：每日自动巡检，脏数据前置剔除
- **回测**：与实盘共用同一份策略代码，防止未来函数
- **日报**：Markdown + HTML 双输出（含 plotly 交互图）
- **调度**：APScheduler 定时，或手动 CLI

---

## 快速开始

### 1. 环境要求

- Python 3.11+
- macOS / Linux（Windows 未测试）

### 2. 安装

```bash
cd ~/Desktop/py
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"      # 或 make install-dev
```

### 3. 配置

```bash
cp .env.example .env
# 按需修改 .env（默认已可用）
```

嵌套配置用双下划线：`QS_DATABASE__URL=...` / `QS_STOCK_POOL__POOL=HS300`。
生产环境推荐 `QS_STOCK_POOL__POOL=ALL`，首次验证用 `HS300` 更快。

### 4. 初始化数据库

```bash
qs init-db                   # 或 make init-db
qs doctor                    # 检查 DB 健康 + 22 张表齐全性
qs pool list                 # 查看已注册的股票池
```

### 5. 首次拉数

```bash
qs update                    # 拉最近交易日
qs update --date 2026-07-15  # 指定日
qs update --full             # 从 kline_start_date 全量拉
```

### 6. 跑完整流程

```bash
qs pipeline                  # 一次跑完：更新→特征→质量→选股→日报
```

日报生成到 `reports/YYYY-MM-DD.md` 和 `reports/YYYY-MM-DD.html`。

### 7. 常驻调度器

```bash
qs schedule                  # 前台阻塞，收盘后自动跑
# 或用 nohup / systemd / launchd 后台化
```

---

## CLI 命令一览

| 命令 | 说明 |
|---|---|
| `qs init-db` | 初始化数据库 |
| `qs update [--date --full]` | 拉/更新数据 |
| `qs feature [--date --codes]` | 重新计算特征 |
| `qs quality [--date]` | 数据质量检查 |
| `qs select [--date --top-n]` | 跑策略选股 |
| `qs report [--date --format]` | 生成日报 |
| `qs pipeline [--date]` | 端到端一键跑 |
| `qs backtest --config path.toml` | 跑回测 |
| `qs benchmark [--strategy --days]` | 策略性能测试 |
| `qs doctor` | 数据完整性 + DB 健康检查 |
| `qs schedule` | 启动调度器 |
| `qs pool list` / `qs pool show HS300` | 股票池 |
| `qs signal stats --strategy ...` | 策略统计 |

---

## 项目结构

```
quant_system/
├── config/          # 全局配置（可调参数集中）
├── infra/           # 基础设施：db、logger、cache、trading_calendar、code_hash
├── database/        # ORM 模型 & migrations
├── data/            # 数据源 provider + repository + 更新编排
├── market/          # 市场域：index、sentiment、market_features
├── indicators/      # 技术指标（technical / factors）
├── feature_store/   # 特征商店（builder / reader / vector）
├── data_quality/    # 数据质量巡检 + 过滤器
├── strategy/        # 策略（纯函数）+ 评分 + selector
├── backtest/        # 回测引擎
├── report/          # 日报生成
├── scheduler/       # APScheduler 任务
├── cli.py           # 命令行入口
└── main.py          # 调度器常驻入口
```

依赖方向严格自下而上，见 [ARCHITECTURE.md](#) （待补）。

---

## 数据流

```
每日收盘 (15:30)
  │
  ├─► update    拉行情/财务/市场数据 → daily_kline / financial_snapshot / market_daily
  │
  ├─► features  算指标 → daily_feature（含 ann_date 溯源）+ market_feature_daily
  │
  ├─► quality   巡检 → data_quality_check
  │
  ├─► select    策略 → scoring → strategy_signal + strategy_signal_feature
  │             （前置：按 DQ 过滤脏股票）
  │
  └─► report    日报 → daily_report + reports/YYYY-MM-DD.{md,html}
```

---

## 配置速查

所有配置在 `quant_system/config/settings.py`。常改项：

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `QS_DB_URL` | `sqlite:///./data_cache/quant.db` | 切 PG 改这里 |
| `QS_STOCK_POOL` | `HS300` | ALL / HS300 / ZZ500 / CUSTOM |
| `QS_SIGNAL_RECORD_LEVEL` | `HIT_FILTERED` | 见下表 |
| `QS_DQ_FILTER_LEVEL` | `ERROR` | 数据质量过滤级别 |
| `QS_REPORT_TOP_N` | `20` | 日报 TopN |

**信号记录级别**：

| 值 | 含义 |
|---|---|
| `HIT_ONLY` | 只记完全命中 |
| `HIT_FILTERED` | 命中 + 被过滤（**默认**） |
| `WITH_WATCH` | 上面 + 观察名单 |
| `ALL` | 全记（含 NEAR_MISS，表膨胀 5-10 倍） |

**数据质量过滤级别**：

| 值 | 含义 |
|---|---|
| `OFF` | 不过滤 |
| `ERROR` | 只剔除 ERROR 级问题股（**默认**） |
| `WARN_AND_ABOVE` | ERROR + WARN 都剔 |

---

## 扩展点

| 需求 | 落点 | 是否动核心 |
|---|---|---|
| 实时行情 | 新增 `data/realtime_provider.py` | 否 |
| QMT 接口 | 新增 `execution/` 层 | 否 |
| ML 模型 | 新增 `models/`，输入 = daily_feature | 否 |
| 向量检索 | 补充 `feature_store/vector.py` + FAISS/Chroma | 否 |
| LLM 报告分析 | 新增 `report/llm_analyst.py` | 否 |

---

## 开发

```bash
make lint      # ruff + mypy
make format    # 一键格式化
make test      # pytest
make clean     # 清理缓存
```

---

## 免责声明

本项目仅供个人研究学习使用，**不构成任何投资建议**。基于本系统输出做出的任何交易决策，风险自负。
