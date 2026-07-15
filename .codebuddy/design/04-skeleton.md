# 04 · 项目骨架 + 依赖 + 配置

## 目录结构

```
~/Desktop/py/                         工程根
├── quant_system/                     Python 包
│   ├── config/       settings.py（pydantic-settings 分组配置）+ logging.yaml
│   ├── infra/        db / logger / cache / trading_calendar / code_hash / board
│   ├── database/     models.py（22 张表）+ migrations.py
│   ├── data/         stock_provider / financial_provider / repository / data_update / provider_factory
│   ├── market/       index_provider / sentiment
│   ├── indicators/   technical.py（手写指标）
│   ├── feature_store/  builder.py
│   ├── data_quality/   checker.py
│   ├── strategy/     待做
│   ├── backtest/     待做
│   ├── report/       待做
│   ├── scheduler/    待做
│   ├── cli.py        Typer 入口
│   └── main.py       调度器常驻入口
├── data_cache/       akshare 磁盘缓存 + SQLite 库
├── logs/             运行日志
├── reports/          日报输出
├── scripts/          一次性脚本（init_db / seed_mock_kline / smoke_test）
├── pyproject.toml
├── requirements.txt / requirements-dev.txt
├── Makefile
├── .env.example
└── README.md
```

## 依赖选型

| 场景 | 库 | 备注 |
|---|---|---|
| 数据源 | akshare | 免费、无 token，社区活跃 |
| 数据处理 | pandas 2.2 / numpy <2.1 | numpy 2.x 生态还不稳 |
| 技术指标 | **手写** | pandas-ta 要求 py 3.12；不升 py 版本 |
| 数据库 | SQLAlchemy 2.0 + SQLite（默认）/ Alembic | 未来切 PG |
| 调度 | APScheduler | |
| 配置 | pydantic-settings | 从 .env 加载，带类型校验 |
| 日志 | loguru | 比标准 logging 上手快 |
| CLI | Typer + Rich | 类型注解自动生成命令 + 终端表格 |
| 可视化 | plotly + matplotlib | HTML 交互 + Markdown 内嵌 |
| 工具 | tenacity（重试）+ diskcache（磁盘缓存）| |

## 配置分组（config/settings.py）

分组的 pydantic BaseModel，嵌套用双下划线加载：

```
QS_DATABASE__URL=sqlite:///./data_cache/quant.db
QS_STOCK_POOL__POOL=HS300
QS_BOARD_FILTER=MAIN
QS_SIGNAL__RECORD_LEVEL=HIT_FILTERED
QS_DATA_QUALITY__FILTER_LEVEL=ERROR
```

| 分组 | 关键项 |
|---|---|
| DatabaseConfig | url / echo_sql / SQLite PRAGMA |
| DataConfig | cache_dir / kline_start_date=2015-01-01 / akshare 重试 / 限流 |
| StockPoolConfig | pool（ALL/HS300/ZZ500/CUSTOM）/ custom_codes / exclude_st/new_listed/suspended |
| FeatureConfig | version / MA/MACD/RSI/KDJ/ATR/BOLL 各指标参数 |
| StrategyConfig | breakout / momentum / value_growth 各自参数 dict |
| ScoringConfig | 技术 40 / 资金 30 / 基本面 30 权重 + 多命中加成 |
| SignalConfig | record_level / near_miss_tolerance |
| DataQualityConfig | filter_level / abnormal_pct_threshold / feature_null_rate_warn |
| ReportConfig | output_dir / top_n / formats=['md','html'] |
| BacktestConfig | 初始资金 / 佣金 / 滑点 / 最大持仓 |

顶层加了 `board_filter: str = "MAIN"` 平级字段。

## CLI 命令一览

```
qs init-db              初始化数据库
qs update stock-basic   拉股票基础
qs update stock-pool    拉池成分
qs update kline         拉日线（增量）
qs update financial     拉财务
qs update market        拉指数+情绪（--backfill 回填历史情绪）
qs update all           全跑
qs feature [--date]     算特征
qs quality [--date]     数据质量巡检
qs select [--date]      跑策略（待做）
qs report [--date]      日报（待做）
qs pipeline [--date]    端到端（待做）
qs backtest --config    回测（待做）
qs benchmark            性能测试（待做）
qs doctor               健康检查
qs schedule             启动调度器（待做）
qs pool list|show
qs signal stats         策略统计（待做）
qs cache stats|clear|rebuild
```

**统一约定**：所有子命令都接受 `--date`，方便回补历史或调试。

## 依赖注入契约

```python
# 业务只依赖 Protocol
def run_daily_update(
    stock_provider: StockProvider,
    financial_provider: FinancialProvider,
    repos: Repositories,
) -> UpdateStats: ...

# CLI 是 composition root，唯一注入点
with session_scope() as session:
    run_daily_update(
        stock_provider=get_stock_provider(),        # 工厂决定用哪个实现
        financial_provider=get_financial_provider(),
        repos=build_repositories(session),
    )
```

未来接 QMT：在 `provider_factory.py` 加一个 `if name == "qmt": return QmtStockProvider()` 就完成，业务代码零改动。

## .env.example 关键项

```bash
QS_DATABASE__URL=sqlite:///./data_cache/quant.db
QS_STOCK_POOL__POOL=HS300
QS_BOARD_FILTER=MAIN
QS_DATA__KLINE_START_DATE=2015-01-01
QS_SIGNAL__RECORD_LEVEL=HIT_FILTERED
QS_DATA_QUALITY__FILTER_LEVEL=ERROR
QS_STOCK_PROVIDER=akshare
```
