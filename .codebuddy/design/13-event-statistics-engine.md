# 13 · Event Statistics Engine（事件统计引擎）

> 状态：✅ **V1 冻结**（2026-07-18）  
> 规范名：Event Statistics Engine（历史名 Pattern Event Backtest 仅作别名）  
> 依赖：10 Pattern Matching / 12 Definition Editor / 11 Web / 05 数据层 / 14 Feature Catalog  
> 非目标：组合资金回测（仓位 / 换仓 / 手续费）——阶段 17 / `backtest_task`  
> 旧稿：`13-pattern-outcome-backtest.md` → 已废弃，以本文为准  

---

## 0. 模块到底负责什么？

### 0.1 一句话

> **Event Backtest = Event Statistics Engine，不是 Strategy Rating Engine。**

它只回答两句事实：

1. **历史上哪些时刻触发了入场形态？**（Discovery）  
2. **触发之后，价格上发生了什么？**（Evaluation + Aggregation）

它**不**回答：策略好不好、该不该用、综合多少分。  
那些属于**分析 / 产品解释层**，必须能基于落库事件随时重算，**禁止**写进引擎核心产出。

### 0.2 核心原则（冻结）

| # | 原则 |
|---|------|
| P1 | **回测负责生成数据，不负责解释数据。** |
| P2 | **回测负责统计事实，不负责评价策略。** |
| P3 | **任何可由后处理得到的「评分 / 综合指标 / 评价结论」，都不要在回测过程中固化。** |
| P4 | **尽可能保存完整 Event 原始结果**，使未来新增任意统计分析时，**不需要重新跑 Discovery / Matcher**。 |
| P5 | **Entry 回答「像不像」** → 保留 `entry_similarity` + `match_explain`。 |
| P6 | **Outcome 默认回答「后来发生了什么」** → 输出 Metrics（事实），不是 Outcome Similarity。 |

### 0.3 四职责 / 明确不做

```text
① Event Discovery   → 发现事件（含 Match Explain）
② Event Evaluation  → 度量事实（每个事件）
③ Aggregation       → 跨事件描述统计
④ Storage           → 事件级原始结果落库 + Run 级统计快照
```

| 不做 | 原因 |
|------|------|
| `strategy_effect_score` / `S_*` / 权重 profile | 替用户做价值判断 |
| 默认产出「策略 85 分」 | 解释权在分析层 |
| 默认 Outcome Similarity「后来有多好」 | 默认语义是观测事实 |
| 资金曲线 / 仓位 / 手续费 | 阶段 17 |

### 0.4 与相邻模块的边界

| 模块 | 问的问题 | 本引擎关系 |
|------|----------|------------|
| Pattern Matching（10） | asof 日「像不像」 | Discovery **复用** Entry Matcher |
| Definition Editor（12） | 如何编辑 Entry（及可选 Mode B） | 配置来源 |
| **本引擎（13）** | 历史上触发后发生了什么 | 事实生产 |
| 分析层 / Web / notebook | 怎样解读这些事实 | **只读事件表** |
| 组合回测（17） | 按规则买卖后资金怎样 | 表与 Job 分离 |

---

## 1. 概念模型

```text
EntryDefinition (published, version-locked)
        │
        ▼
┌───────────────────┐
│ Event Discovery   │──► Event[]
│                   │    code, signal_date, entry_similarity,
│                   │    match_explain, tags, …
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Event Evaluation  │
│  Mode A（默认）   │──► 宽列标准指标 + extra_metrics_json
│  Mode B（P1+）    │──► + outcome_json（可选）
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Aggregation       │──► summary_json（缓存，带 aggregation_version）
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Storage           │──► pattern_event_run / pattern_event
└───────────────────┘
        │
        ▼
  Statistics Report / 任意后处理视图（引擎外）
```

### 1.1 Event（最小单元）

| 字段 | 含义 | 性质 |
|------|------|------|
| `code` / `signal_date` | 标识 | |
| `entry_similarity` | 入场总分 | **分类分，必须保留** |
| `match_explain` | 命中解释（§6.4） | 免重跑 Matcher |
| `tags` | 事件标签（§5.3） | 后过滤 |
| 标准 Observation 宽列 | `return_*` / `mfe` / … | **核心产出** |
| `extra_metrics_json` | 扩展 / 自定义指标 | 演进槽 |
| `outcome_json` | Mode B 明细 | P1+ |
| `forward_status` | 质量 | |

### 1.2 时间锚点（V1 冻结）

| 项 | 规则 |
|----|------|
| Signal bar | 当日收盘后可知 |
| 远期第 1 根可用 K | **下一交易日（T+1）** 起算 |
| 禁止 | 用信号日收盘假装「未来第 0 日收益」 |
| 复权 | **前复权（qfq）**；Run meta 记 `price_adj=qfq` |
| 日历 | Run meta 记 `calendar`（§5.2）；V1 = `ChinaTradingCalendar` |
| `anchor_mode` | V1 固定 `t1_close` |

### 1.3 Entry vs Outcome

| | Entry | Outcome（默认） |
|---|------|----------------|
| 问题 | **像不像？** | **后来发生了什么？** |
| 机制 | Matcher + Target + Similarity | 固定窗口事实指标 |
| 必有 | `entry_similarity` + `match_explain` | 标准宽列 Metrics |
| Stage/Weight | 要 | **不要** |

---

## 2. Outcome：两种模式

### 2.1 Mode A — Observation（默认 · **P0 唯一实现**）

```yaml
outcome:
  mode: observation
  horizon_bars: 20                 # V1 默认
  return_horizons: [1, 3, 5, 10, 20, 60]
```

系统计算 §3 标准事实指标。  
**没有**：Stage / Timeline / Target / Weight / Threshold / Similarity / Matcher。

未来 bar 不足：`forward_status = truncated | insufficient`，缺指标为 `null`，**事件仍保留**。

### 2.2 Mode B — Pattern Outcome（**P1+，P0 不做**）

仅当用户要描述「未来路径像不像某种形态」时启用。

```yaml
outcome:
  mode: pattern
  horizon_bars: 20
  definition: { timeline: [...], threshold: 60, ... }
  also_observe: true
```

V1 窗口策略预留：**Fixed** Stage 长度。  
**禁止**把 `outcome_similarity` 揉成引擎级效果总分。  
P0：接口/枚举可预留 `outcome_mode`，但 Runner **只跑** `observation`。

### 2.3 配置挂载（P0）

| 配置 | 说明 |
|------|------|
| Entry | `pattern_definition` + revision（必选） |
| Observation | `horizon_bars=20` + 标准 `return_horizons` |

正式 Run 锁定（P0）：

`entry_id@version` + `outcome_mode=observation` + 宇宙 + 区间 + `horizon` / `return_horizons` + `dedup_policy` + `calendar` + `anchor_mode` + `price_adj` + `engine_version` + `code_hash` + `engine_config_hash` + `aggregation_version`。

---

## 3. Event Evaluation — 事实指标目录

> Evaluation 输出「发生了什么」，不是「有多好」。

### 3.1 存储策略（V1 冻结 · 重要）

**标准 Observation 指标 → 宽列**；**扩展指标 → `extra_metrics_json`**。

原因：查询 / 排序 / 筛选 / 索引友好；扩展性仍由 JSON 槽位保留。

```text
pattern_event
├── return_1 … return_60, return_horizon     # 宽列
├── mfe, mae, max_drawdown, volatility, …
├── forward_status, forward_bars_available
└── extra_metrics_json                      # 未来 / 自定义
```

P0 **不写** `benchmark_return_*` 宽列（Benchmark 整体后置）。

### 3.2 标准宽列（冻结集合）

| 列名 | 含义 |
|------|------|
| `return_1` / `return_3` / `return_5` / `return_10` / `return_20` / `return_60` | 信号收盘 → 第 h 日收盘收益 |
| `return_horizon` | 主观测窗末日收益（=`return_{horizon_bars}`） |
| `mfe` | Maximum Favorable Excursion |
| `mae` | Maximum Adverse Excursion |
| `max_drawdown` | 窗内最大回撤（正数） |
| `volatility` | 窗内日收益样本标准差 |
| `bull_ratio` | 阳线占比（close > open） |
| `up_days` | 上涨天数（close > prev_close） |
| `continuous_up_days` | 最长连续上涨天数 |
| `highest_day` / `lowest_day` | 最高 / 最低价相对日序（1…H） |
| `time_to_mfe` / `time_to_mae` | MFE / MAE 日序 |
| `forward_bars_available` | 实际可用未来 bar 数 |
| `forward_status` | `ok` / `truncated` / `insufficient` |

### 3.3 V1 口径（写进 Run meta，禁止 silently 改）

- 收益类、MFE、MAE：相对 **信号日收盘**  
- MFE / MAE：窗内 `[T+1 … T+H]` 的 high / low  
- `max_drawdown`：窗内 running peak → low，存**正数**  
- `time_to_*` / `highest_day` / `lowest_day`：统一用**日序**  
- `mae` 口径：`1 - min(low)/anchor`（不利幅度为正；实现锁定）

### 3.4 `extra_metrics_json`

未来新增、自定义、插件产出的指标放入此列，例如：

```json
{ "atr_14": 0.02, "rsi_14": 58.3, "alpha_101_001": 0.11 }
```

聚合层对宽列做一等公民统计；对 `extra_metrics_json` 的聚合为 P1+（按需）。

### 3.5 Mode B 字段（P1+）

写入 `outcome_json`，与宽列分离：

| 字段 | 含义 |
|------|------|
| `outcome_similarity` / `outcome_matched` | 远期形态 |
| `outcome_stage_similarity` / feature 明细 | 可解释 |

---

## 4. Metrics Hook（扩展接口 · P0 留口、P0 不实现插件）

`observe.py` 内置标准指标，并通过协议预留扩展：

```python
class MetricProvider(Protocol):
    """对单个 Event 的远期窗口计算额外事实指标。"""

    name: str
    version: str

    def compute(
        self,
        *,
        code: str,
        signal_date: date,
        forward_bars: Any,       # qfq OHLCV window
        anchor_close: float,
        ctx: ObserveContext,
    ) -> dict[str, Any]:
        """返回写入 extra_metrics_json 的 key→value；不得改写标准宽列语义。"""
        ...
```

| 阶段 | 行为 |
|------|------|
| **P0** | 仅内置 `StandardObservationProvider` → 写宽列；**不注册**外部 Provider |
| **P1+** | 可注册 ATR / RSI / MACD / Alpha101 / 行业特征等；结果进 `extra_metrics_json` |

约束：

- Provider **只产事实**，不产评分。  
- Provider 版本纳入 `engine_config_hash`（启用时）。  
- Engine 核心循环不因新指标改代码，只注册 Provider。

---

## 5. Storage

### 5.1 目标

> **一次回测，多次分析。**  
> 新视图 = 新查询 / 新聚合，不是新一次全历史 Matcher。

```sql
SELECT AVG(return_10), AVG(mae)
FROM pattern_event
WHERE run_id = ? AND forward_status = 'ok';

SELECT *
FROM pattern_event
WHERE run_id = ? AND return_5 > 0
ORDER BY mfe DESC
LIMIT 50;
```

### 5.2 `pattern_event_run`

| 字段 | 说明 |
|------|------|
| `run_id` | PK |
| `entry_pattern_id` / `entry_version` | 锁定 |
| `outcome_mode` | P0 固定 `observation` |
| `outcome_version` | Mode B 时必填（P1+） |
| `universe_spec` / `start_date` / `end_date` | 宇宙见下；时间为信号扫描区间 |
| | **universe_spec V1**：`{kind:all}` / `{kind:codes, codes:[…]}`（**最小 1 只**）/ `{kind:pool, pool}` |
| `horizon_bars` / `return_horizons_json` | |
| `calendar` | 交易日历标识，V1=`ChinaTradingCalendar`；预留 `SSE`/`SZSE`/港美等 |
| `anchor_mode` | V1=`t1_close` |
| `price_adj` | V1=`qfq` |
| `dedup_policy` | 见 §6 |
| `engine_version` | 引擎语义版本 |
| `code_hash` | 实现代码指纹 |
| `engine_config_hash` | **配置指纹**（见 §5.4） |
| `aggregation_version` | **聚合逻辑版本**；`summary_json` 与此绑定 |
| `status` / `created_at` / `duration_ms` | |
| `summary_json` | §7 聚合缓存；可被事件表按 `aggregation_version` 重算覆盖 |

### 5.3 `pattern_event`

| 字段 | 说明 |
|------|------|
| `run_id` + `event_id` | |
| `code` / `signal_date` | |
| `entry_similarity` | 分类分 |
| `match_explain_json` | §6.4 命中解释 |
| `entry_snapshot_json` | windows / 原始 match 快照（可选，与 explain 互补） |
| `tags_json` | `string[]`，如 `["半导体","创业板"]` |
| **标准宽列** | §3.2 全部 |
| `extra_metrics_json` | 扩展指标 |
| `outcome_json` | Mode B；P0 空 |
| `forward_status` | 冗余宽列，便于过滤 |

**推荐索引（P0）：**

- `(run_id, code, signal_date)` UNIQUE  
- `(run_id, signal_date)`  
- `(run_id, entry_similarity)`  
- `(run_id, return_5)` / `(run_id, return_10)` / `(run_id, mfe)` / `(run_id, mae)`  
- `(run_id, forward_status)`  

`tags`：SQLite 可用 `tags_json` + 应用层过滤；PG 日后可迁数组/GIN（schema 字段名保持 `tags_json`）。

### 5.4 `engine_config_hash`（复现）

`code_hash` 不够。真正影响结果的还包括配置面。哈希输入至少包含（规范化后 canonical JSON）：

| 纳入 | 说明 |
|------|------|
| Entry definition 正文 / version | Target、Weight、Threshold、Timeline… |
| Feature Catalog 版本或相关 feature 集合指纹 | |
| Normalization / Evaluator 相关配置 | |
| Observation：`horizon_bars`、`return_horizons`、口径常量 | |
| `calendar` / `anchor_mode` / `price_adj` / `dedup_policy` | |
| 已启用 MetricProvider 的 `name@version` 列表 | P0 仅标准 Provider |
| `aggregation_version` **不**纳入（聚合可独立重算） | |

同一 `engine_config_hash` + 同一数据 → 事件宽列应可复现。

### 5.5 `aggregation_version`

- `summary_json` 是**缓存**，不是真相源。  
- 聚合算法变更时 bump `aggregation_version`，可只重跑 Aggregation，不必重跑 Discovery/Observation。  
- 报告展示：若缓存版本 ≠ 当前代码的 aggregation_version → 提示重算或自动重算。

### 5.6 tags（事件标签）

Discovery（或紧随其后的 enrichment）为每个 Event 写入 `tags_json`，例如：

```json
["半导体", "创业板", "高换手"]
```

来源（P0 最小集，实现可裁剪）：

- 板块 / 行业名  
- 市场板块（主板 / 创业板 / 科创板 等，由 code 规则推导）  

P0 不要求完整标签体系；**字段必须有**， enrichment 可先写少量稳定标签。  
后处理可按 tag 过滤统计，**无需重新 Discovery**。

---

## 6. Event Discovery

```text
for date in trading_days(start, end, calendar):
  for code in universe(date):
    result = EntryMatcher.match(code, date, …)   # 仅用 ≤ signal_date
    if result.matched:
      emit Event(
        code, date,
        entry_similarity,
        match_explain = build_explain(result),
        tags = enrich_tags(code, date),
        …
      )
```

默认只收录 `matched == true`。

### 6.1 去重（Dedup）

| policy | 行为 |
|--------|------|
| `none` | 全留 |
| `cooldown_h` | 命中后 H 个交易日内同票忽略 |

**V1 默认**：`cooldown_h` 且 `H = horizon_bars`。  
去重在 Discovery 后、Evaluation 前；被丢事件 P0 可不落库。

### 6.2 无未来函数

| 阶段 | 可用数据 |
|------|----------|
| Entry | `≤ signal_date` |
| Evaluation | `> signal_date`（从 T+1 起） |

单测：信号日 K 线不得进入 `return_*` / MFE / MAE。

### 6.3 Observation 计算（示意）

```text
bars = qfq_ohlc(code)[after signal_date]
H = horizon_bars
window = bars[:H]
anchor = close(signal_date)

write wide columns: return_*, mfe, mae, …
extra = {}
for provider in enabled_providers:          # P0: 仅标准，且标准直接写宽列
  extra |= provider.compute(...)
write extra_metrics_json = extra            # P0 可为 {}
```

### 6.4 `match_explain`（命中解释 · P0 要落库）

除 `entry_similarity` 外，持久化解释结构，供日后 AI / UI 回答「为什么命中」而**不必重跑 Matcher**：

```json
{
  "entry_similarity": 78.5,
  "threshold": 60,
  "top_feature_contribution": [
    {"key": "platform.slope", "similarity": 92.0, "weight": 1.2, "value": 0.004},
    {"key": "breakout.total_return", "similarity": 85.0, "weight": 1.0, "value": 0.06}
  ],
  "stage_explain": {
    "platform": {"similarity": 80.1, "weight": 1.0},
    "breakout": {"similarity": 76.2, "weight": 1.0}
  },
  "feature_explain": {
    "platform.slope": {"similarity": 92.0, "value": 0.004, "ideal": 0.0, "hard_failed": false},
    "…": {}
  },
  "hard_failed": [],
  "chosen_windows": {"platform": 18, "breakout": 3},
  "chosen_window_ranges": { "…": {} }
}
```

实现：从 `PatternMatchResult` 抽取；字段可随 Matcher 演进，但 **P0 必须有** `stage_explain` + `feature_explain`（或等价明细）+ `top_feature_contribution`（可按 weight×(100−sim) 或 sim 排序取 TopK）。

---

## 7. Aggregation — 只做描述统计

对有效样本（通常 `forward_status='ok'`，或按字段非空）聚合。  
`summary_json` **全部是统计量**，绑定 `aggregation_version`。

### 7.1 覆盖

- 事件数、股票数、区间  
- 事件覆盖率（定义写入 summary meta）  
- truncated / insufficient 计数  

### 7.2 各 horizon 收益（宽列）

对 `return_1`…`return_60` / `return_horizon`：

mean / median / P10 / P90 / win_rate / `n_valid`

### 7.3 路径与时间结构

对 `mfe` / `mae` / `max_drawdown` / `volatility` / `bull_ratio` / `up_days` / `continuous_up_days` / `highest_day` / `lowest_day` / …：

mean / median（及必要分位） / `n_valid`

### 7.4 明确不输出

```text
❌ strategy_effect_score / S_* / profile 权重
❌ 「综合 85 分」作为引擎一等公民
```

---

## 8. Statistics Report

```text
# 覆盖
事件数 / 股票数 / 覆盖率 / 区间
Entry@version / horizon / calendar / dedup
engine_config_hash / aggregation_version

# 收益（按 horizon）
return_1 / 3 / 5 / 10 / 20 / 60
  mean | median | P10 | P90 | win_rate | n

# 路径
MFE | MAE | max_drawdown | volatility | bull_ratio
  …

# 时间结构
highest_day | lowest_day | up_days | continuous_up_days

# 下钻
事件表：按宽列排序过滤；可看 match_explain / tags
```

**禁止作为报告主角**：综合分、效果四维雷达（分析层实验除外）。

---

## 9. 系统落点

```text
quant_system/eventstats/
  discovery.py          # Entry 扫描 → Event + match_explain + tags
  observe.py            # Mode A：标准宽列；MetricProvider 协议
  providers/
    standard.py         # P0 唯一 Provider（写宽列）
  aggregate.py          # 描述统计；暴露 AGGREGATION_VERSION
  store.py              # Run / Event 读写
  report.py             # summary → 报告 DTO
  runner.py             # Job 编排
  # pattern_outcome.py  # P1+ 再加
```

- 包名 **V1 冻结**：`quant_system/eventstats`  
- 包内不得出现 `strategy_effect_score` / `S_return` 等命名  

---

## 10. API / CLI / Web（P0）

### 10.1 Job

`pattern.event_stats`

参数：`pattern_id`、`entry_version`、区间、宇宙、`horizon_bars`、`return_horizons`、`dedup_policy`、`calendar`（可选，默认中国交易日历）。

P0 **不接受** `outcome_mode=pattern`（或接受但直接拒绝）。

### 10.2 读接口

- `GET /api/event-stats/runs`  
- `GET /api/event-stats/runs/{run_id}` → summary  
- `GET /api/event-stats/runs/{run_id}/events` → 分页 / 筛选 / 排序（**宽列**）  

### 10.3 CLI

```bash
qs event-stats run --pattern RANGE_BREAKOUT --start … --end … --horizon 20
qs event-stats report --run-id …
qs event-stats reaggregate --run-id …   # 可选：仅重算 summary
```

### 10.4 Web

策略页 Tab（P0）：

1. 入场形态  
2. **事件统计**（跑 Job + 统计报告 + 事件表 + explain / tags 展示）  

Mode B 编辑器：**不做**。

---

## 11. 落地节奏（收敛后）

| 阶段 | 内容 |
|------|------|
| **P0** | Discovery（含 match_explain + 基础 tags）+ Observation 宽列 + Storage + Aggregation + Statistics Report（API/页/CLI） |
| **P0′** | `reaggregate`；tags enrichment 加厚；更多索引 |
| **P1** | MetricProvider 插件注册；`extra_metrics_json` 聚合；Mode B Pattern Outcome；Benchmark 可选列 |
| **P2** | 增量重算 Evaluation；分析层自定义评分（**引擎外**） |

### P0 明确不做

```text
❌ Benchmark
❌ Pattern Outcome（Mode B）
❌ 外部 Plugin Metrics（协议可留，不注册第三方）
❌ 任何评分体系 / 综合分 / S_* profile
```

### P0 验收

1. 同一 `engine_config_hash` + 数据可复现宽列指标。  
2. `SELECT AVG(return_10), AVG(mae) FROM pattern_event WHERE run_id=?` 可直接跑。  
3. 事件可按 `return_5` / `mfe` 等宽列排序过滤。  
4. `match_explain_json` 足够回答「为何命中」而无需重跑 Matcher。  
5. `summary_json` 带 `aggregation_version`；报告无综合分。  
6. 无未来函数单测通过。  
7. 包内 grep 不到评分体系命名。

---

## 12. 决策速查（V1 冻结）

| # | 决策 |
|---|------|
| 1 | 定位 = **Event Statistics Engine** |
| 2 | 四职责：Discovery / Evaluation / Aggregation / Storage |
| 3 | **无**引擎级综合评分 |
| 4 | Outcome 默认 Observation；Mode B = P1+ |
| 5 | Entry：`entry_similarity` + **`match_explain`** |
| 6 | 标准指标 **宽列**；扩展进 **`extra_metrics_json`** |
| 7 | Run：`calendar` / `engine_config_hash` / `aggregation_version` |
| 8 | Event：`tags_json` |
| 9 | Observation：`MetricProvider` 协议预留，P0 仅标准实现 |
| 10 | 报告 = 统计报告 |
| 11 | 锚点 T+1；复权 qfq；日历 `ChinaTradingCalendar` |
| 12 | 包名 `eventstats`；默认 `horizon_bars=20`；默认 dedup=`cooldown=horizon` |
| 13 | 与组合回测分离 |

---

## 13. 与旧设计的关系

| 旧概念 | 处置 |
|--------|------|
| `strategy_effect_score` / `S_*` / profile | **作废** |
| 全部指标进 `metrics_json` | **改为宽列 + extra_metrics_json** |
| Outcome 默认复制 Entry Matcher | **改为默认 Observation** |
| 评分卡报告 | **改为统计报告** |
| `13-pattern-outcome-backtest.md` | **废弃**，以本文为准 |

---

## 附录 A · 分析层（引擎外）

允许 Web / notebook / 独立 Job：

- 自带版本号；  
- 读宽列 / `extra_metrics_json` / `tags_json` / `match_explain_json`；  
- **不得**回写为引擎 Run 唯一总分。

```text
my_score = 0.5 * mean(return_10) - 0.3 * mean(mae) + 0.2 * win_rate(return_5)
```

不同用户可以有完全不同的公式——这正是引擎不内置综合分的原因。
