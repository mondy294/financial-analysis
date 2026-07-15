# 03 · 数据库设计 v2（最终版）

## 相对 v1 的变更

| 变更 | 涉及表 |
|---|---|
| A. 基本面字段带血缘 | `daily_feature` 加 `financial_snapshot_date` / `financial_ann_date` |
| B. hit → signal_type 四态 | `strategy_signal` 加 `signal_type` / `filter_reason` / `near_miss_gap` |
| C. 向量预留 | `daily_feature` 加 `vector_version` / `embedding_id` |
| D. 回测任务/结果 | 新增 `backtest_task` / `backtest_result` |
| E. 数据质量表 | 新增 `data_quality_check` |
| F. ORM 数据库中立 | sqlite_with_rowid 走 dialect 判断；不用 JSON1 语法 |

**共 22 张表**（v1 18 张 + 新增 4 张）。

## signal_type 四态语义

| 值 | 含义 | 何时写 | 用途 |
|---|---|---|---|
| `HIT` | 完全命中，进候选池 | 全部条件通过 | 日报推荐 |
| `WATCH` | 主要条件满足但差一个次要 | 例：MA 多头+MACD 金叉，但量能没放大 | 观察名单 |
| `NEAR_MISS` | 差一点触发（可量化差距） | 例：距 20 日新高还差 0.3% | 复盘敏感度 |
| `FILTERED` | 命中但被前置规则拒（ST/停牌/新股/流动性） | 命中条件被过滤 | 分析假信号 |

**记录级别配置** `QS_SIGNAL__RECORD_LEVEL`：
- `HIT_ONLY` 只记 HIT
- `HIT_FILTERED` HIT + FILTERED（**默认**）
- `WITH_WATCH` 上面 + WATCH
- `ALL` 全记

`hit` 字段保留（`hit = (signal_type == 'HIT')`），boolean 索引比字符串快 3-5 倍。

## data_quality_check 关键设计

| check_type | 触发时机 | 默认 severity |
|---|---|---|
| MISSING_KLINE | 池成员某天无 K 线 | WARN |
| SUSPENDED | 成交量 = 0 | WARN |
| ABNORMAL_PRICE | \|pct_change\| > 22% | ERROR |
| ZERO_VOLUME | volume=0 但 pct_change≠0 | ERROR |
| FINANCIAL_LATE | 报告期后 >60 天未公告 | WARN |
| FEATURE_NULL_RATE_HIGH | 某日特征空值率 >5% | WARN |
| SYNC_STALE | 同步游标落后 >3 天 | INFO |

**过滤级别配置** `QS_DATA_QUALITY__FILTER_LEVEL`：
- `OFF` 不过滤
- `ERROR` 只剔除 ERROR 级 STOCK（**默认**）
- `WARN_AND_ABOVE` ERROR + WARN 都剔

**硬约束**：selector 接收的是**已过滤的特征**，过滤在 selector 前完成，策略层零感知数据脏问题。

## backtest_task / backtest_result 分工

- `backtest_task`：输入配置（策略/参数/时间/池/资金/费率），含 `strategy_code_hash`（策略目录整体 SHA256，保证复现）
- `backtest_result`：输出指标（收益/回撤/夏普/胜率/交易统计）
- 1:1 拆表原因：批量看参数扫描结果只扫 result（更小），不用带上大 params_snapshot JSON

## 与 strategy_performance 的分工

| 表 | 含义 | 数据来源 |
|---|---|---|
| `strategy_performance` | 策略在真实时间轴上的**滚动表现** | 生产调度器基于 strategy_signal + kline 自动算 |
| `backtest_task/result` | **一次显式实验**的完整回测 | backtester 模块运行时写入 |

## SQLite 特化项

只在 `event.listens_for(Engine, "connect")` 里根据 `dialect.name == 'sqlite'` 分支执行，PG 切换时跳过：

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -262144;    -- 256 MB
PRAGMA mmap_size = 268435456;   -- 256 MB
PRAGMA temp_store = MEMORY;
PRAGMA foreign_keys = ON;
```

`sqlite_with_rowid=False` 用 `__table_args__` 传递，其他方言忽略。

## 关键 fix（v2 实施时踩的坑）

**问题**：SQLAlchemy 主键用 `BigInteger` + `autoincrement=True`，SQLite 只把 `INTEGER PRIMARY KEY` 视为 rowid 别名，`BigInteger` 编译成 `BIGINT` 不会自动填充。

**修复**：
```python
id: Mapped[int] = mapped_column(
    BigInteger().with_variant(Integer(), "sqlite"),
    primary_key=True, autoincrement=True,
)
```
PG/MySQL 继续用 BIGINT，SQLite 用 INTEGER（rowid 别名）。
