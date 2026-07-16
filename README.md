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
qs doctor                    # 检查 DB 健康 + 所有表齐全性
qs pool list                 # 查看已注册的股票池
```

### 5. 首次拉数

```bash
qs update all                    # 按依赖顺序全量更新（推荐）
qs update all --date 2026-07-15  # 指定交易日
qs update all --full             # 从 kline_start_date 全量拉
qs update kline --full           # 也可只更新单类数据
```

### 6. 跑完整流程

```bash
qs pipeline                  # 一次跑完：更新→特征→质量→选股→日报
```

日报生成到 `reports/YYYY-MM-DD.md` 和 `reports/YYYY-MM-DD.html`。

### 7. 常驻调度器（规划中）

```bash
qs schedule                  # 前台阻塞，收盘后自动跑（当前为占位，未实现）
# 或用 nohup / systemd / launchd 后台化
```

在调度器落地前，可用系统 cron / launchd 定时执行 `qs pipeline`。

---

## CLI 命令一览

> 入口统一为 `qs`（等价 `python -m quant_system.cli`）。所有 `--date` 默认取最近交易日。

### 核心流程

| 命令 | 说明 |
|---|---|
| `qs init-db` | 初始化数据库：建表 + 写入种子数据（股票池等） |
| `qs doctor` | 数据完整性 + 数据库健康检查（校验所有 ORM 表齐全） |
| `qs feature [--date --codes --pool]` | 重算特征（技术+基本面指标）→ `daily_feature` / `market_feature_daily` |
| `qs quality [--date]` | 数据质量巡检 → `data_quality_check` |
| `qs select [--date --top-n N]` | 跑策略 → 综合评分 → 写 `strategy_signal` |
| `qs report [--date --format md/html/both]` | 生成日报 → `reports/YYYY-MM-DD.{md,html}` |
| `qs pipeline [--date --skip-update]` | 端到端一键跑：update→feature→quality→select→report |

### 数据更新 `qs update <子命令>`

| 命令 | 说明 |
|---|---|
| `qs update all [--date --full]` | 按依赖顺序全跑：basic→pool→kline→financial→market |
| `qs update stock-basic [--full]` | 更新股票基础信息 `stock_basic` |
| `qs update stock-pool [--pool --full]` | 更新股票池成分股 |
| `qs update kline [--pool --codes --dry-run --full]` | 更新日 K 线 `daily_kline`（增量） |
| `qs update financial [--pool --codes --full]` | 更新财务快照 `financial_snapshot` |
| `qs update valuation [--pool --codes --full]` | 更新日频估值 `daily_valuation`（PE/PB/市值） |
| `qs update market [--backfill --full]` | 更新指数日线 + 市场情绪（`--backfill` 回填历史） |

### 股票关系层 `qs relationship <子命令>`

| 命令 | 说明 |
|---|---|
| `qs relationship build [--type --windows 60,250 --threshold --min-sample --max-neighbors --pool --board --dry-run --force]` | 计算并落库关系（默认 Pearson，W60+W250）。首次建议先 `--dry-run` 调阈值 |
| `qs relationship top <代码> [--window --limit --neg]` | 查某只票的 TopN 相关邻居（`--neg` 只看负相关） |
| `qs relationship pair <A> <B> [--window]` | 查两只股票之间的关系值 |
| `qs relationship strong [--window --sign ±1 --min-abs --limit]` | 全局强相关榜（`--sign -1` 看强负相关） |
| `qs relationship changed [--short --long --min-delta --limit]` | 联动增强榜：短窗−长窗 相关度变化 |
| `qs relationship leadlag [--window --candidate-min --max-lag --threshold --min-gain --force]` | 计算领先-滞后关系（候选取自同期 PEARSON 快照） |
| `qs relationship leads <代码> [--window --role leads/follows/all --limit]` | 查某只票领先/跟随了谁（lag>0=领先，lag<0=跟随） |
| `qs relationship stats [--type]` | 各窗口关系快照概览（行数/快照日/平均样本/正负分布） |

### 异动 Pattern Engine `qs abnormal <子命令>`

| 命令 | 说明 |
|---|---|
| `qs abnormal scan [--date --patterns --dry-run --force]` | 分模式扫描（横盘突破/底部启动/趋势加速/一年新高），模式内排名后落库 |
| `qs abnormal top --pattern RANGE_BREAKOUT [--limit]` | 单模式 TopN |
| `qs abnormal top --all [--limit]` | 依次打印全部模式榜 |
| `qs abnormal show <代码>` | 该票命中了哪些 Pattern |
| `qs abnormal stats [--date]` | 各 Pattern × Scan 档位命中数 |

### 股票池 `qs pool <子命令>`

| 命令 | 说明 |
|---|---|
| `qs pool list` | 列出已注册的股票池 |
| `qs pool show <代码>` | 查看某个池（如 `HS300`）的成分股 |

### 缓存 `qs cache <子命令>`

| 命令 | 说明 |
|---|---|
| `qs cache stats` | 查看缓存条数和体积 |
| `qs cache clear [--namespace akshare]` | 清空缓存（不指定则清全部） |
| `qs cache rebuild` | 清空缓存并重建交易日历 |

### 尚未实现（占位命令）

| 命令 | 说明 |
|---|---|
| `qs backtest --config path.toml` | 回测（规划中） |
| `qs benchmark [--strategy --days]` | 策略性能测试（规划中） |
| `qs schedule` | 常驻调度器（规划中） |
| `qs signal stats [--strategy --days]` | 策略信号统计（规划中） |

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
