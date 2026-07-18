# 13 · Pattern Event Statistics Engine（事件统计引擎）

> 状态：📝 **设计稿 v2（推倒重写）**  
> 依赖：10 Pattern Matching / 12 Pattern Definition Editor / 11 Web Console / 05 数据层  
> 定位：**发现事件 → 度量事实 → 聚合统计 → 落库复用**  
> 非定位：策略打分、综合效果分、替用户做「好不好」的价值判断  
> 非目标：传统资金曲线组合回测（仓位/换仓/手续费）——见后续阶段 / 现有 `backtest_task` 预留  

**v1 → v2**：删除 `strategy_effect_score` / `S_*` 权重体系；Outcome 默认改为 Observation（事实指标），Pattern Outcome（Matcher）降为高级模式；报告改为统计报告。

---

## 0. 核心原则（冻结）

1. **回测负责生成数据，不负责解释数据。**  
2. **回测负责统计事实，不负责评价策略。**  
3. **任何可由后处理统计得到的数据，都不要在回测过程中固化为「评分」或「综合指标」。**  
   回测应尽量保存**原始事件数据**与**基础聚合统计**，使未来可在**不重新回测**的情况下衍生新的分析视图。  
4. **Entry 回答「像不像」** → 保留 Similarity。  
   **Outcome 默认回答「后来发生了什么」** → 输出 Metrics（事实），不是 Outcome Similarity。

一句话：

> **Event Backtest = Event Statistics Engine，不是 Strategy Rating Engine。**

---

## 1. 职责边界

### 1.1 引擎只做四件事

| # | 职责 | 产出 |
|---|------|------|
| ① | **Event Discovery** | 历史扫描 → `Event(code, signal_date, entry_*)` |
| ② | **Event Evaluation** | 对每个事件度量「之后发生了什么」→ 事实指标 |
| ③ | **Aggregation** | 跨事件聚合 → 均值/中位/分位/胜率等**统计量** |
| ④ | **Event Storage** | 事件级原始结果落库，支持日后 `SELECT AVG(return_10)` 而不重跑 |

### 1.2 明确不做

| 不做 | 原因 |
|------|------|
| `strategy_effect_score` / `S_return` / `S_risk` / `S_outcome` / `S_sample` / 权重 profile | 产品层评价逻辑，因人而异 |
| 默认给 Outcome 打 Similarity「后来有多好」 | 默认语义是事实观测，不是形态验收 |
| 替用户裁定「策略 85 分」 | 解释权在分析层 / 用户 |
| 资金曲线、仓位、手续费 | 另一条回测链路 |

### 1.3 与组合回测的区别

| 维度 | 本模块（事件统计） | 组合回测（后续） |
|------|-------------------|------------------|
| 对象 | `(code, signal_date)` 事件 | 资金/持仓序列 |
| 输出 | 事实指标 + 统计表 | 年化、回撤、Sharpe… |
| 仓位 | 不模拟 | 需要 |
| 表 | `pattern_event_*`（新建） | `backtest_task/result` |

### 1.4 产品分析层（本引擎之外）

下列能力**允许**存在于 Web/报表/notebook，但**禁止**写进回测引擎核心、禁止固化进 Run 的「唯一总分」：

- 自定义加权综合分、balanced / risk-first 等 profile  
- 「好策略」标签、评级星级  
- 任意由事件表二次聚合出的新视图  

原则：引擎存事实；产品读事实再解释。

---

## 2. 概念模型

```text
EntryDefinition (published)
        │
        ▼
 Event Discovery  ──►  Event[]   (code, signal_date, entry_similarity, …)
        │
        ▼
 Event Evaluation
        ├─ Mode A: Observation   →  forward metrics（事实，默认）
        └─ Mode B: Pattern Outcome → 可选；未来路径 Matcher（高级）
        │
        ▼
 Aggregation（描述统计，非评分）
        │
        ▼
 Storage（事件明细 + Run 级汇总快照）
        │
        ▼
 Statistics Report / 任意后处理视图
```

### 2.1 Event

最小事件：

| 字段 | 含义 |
|------|------|
| `code` | 股票 |
| `signal_date` | 入场命中日（asof） |
| `entry_similarity` | 入场总分（**分类分，保留**） |
| `entry_version` | Entry 定义版本 |
| `entry_windows` / `entry_stage_similarity` / … | 入场可解释快照 |
| `forward_*` | 观测/路径事实（见 §4） |

锚点（V1 冻结）：

- Signal bar = 当日收盘后可知。  
- 远期第 1 根可用 K：**下一交易日（T+1）** 起算，禁止用信号日收盘假装未来。  
- V1.1 可增 `anchor_mode`；V1 固定 T+1 close-to-close 为主收益口径。

### 2.2 Entry：必须 Similarity

Entry 解决的是：

> 在 asof=T，历史窗口**像不像**该形态？

这是分类问题 → `GenericPatternMatcher` + `entry_similarity` + threshold。  
Discovery **只收录** `matched == true`（或配置允许保留近阈值样本——默认不）。

### 2.3 Outcome：默认 Metrics，不是 Similarity

Outcome 默认解决的是：

> 信号之后，价格路径上**发生了什么？**

输出的是可复算的事实字段（收益、回撤、MFE/MAE…），**不是**「后来有多好」的综合分。

---

## 3. Outcome 两种模式

### 3.1 Mode A — Observation（默认，绝大多数用户）

用户只声明：

```yaml
outcome:
  mode: observation
  horizon_bars: 20          # 主观测窗（交易日）
  # 可选：额外收益地平线（仍落在同一事件行）
  return_horizons: [1, 3, 5, 10, 20, 60]
```

系统**自动**在 `[T+1, T+horizon]`（及各 horizon）上计算标准事实指标（§4）。  

**没有**：Stage / Target / Weight / Threshold / Similarity / Matcher。

不够交易日的事件：标记 `forward_status = truncated | insufficient`，指标为 NULL，**不剔除**（聚合时按有效样本计）。

### 3.2 Mode B — Pattern Outcome（高级，可选）

仅当用户要描述「未来路径像不像某种形态」时启用，例如：上涨 → 横盘 → 再上涨。

```yaml
outcome:
  mode: pattern
  horizon_bars: 20          # 仍建议有观测窗上限
  definition:               # 与 Entry 同构的 Forward Definition（Fixed 窗口）
    timeline: [...]
    threshold: 60
    ...
  # 同时仍可计算 Observation 指标（推荐默认一并落库）
  also_observe: true
```

此时才引入：

- Forward Timeline / Stage / Target / Similarity  
- Outcome 命中率、Stage/Feature 级统计  

V1 窗口策略：**Fixed**（每 Stage `min_length == max_length`），避免远期「挑最好窗口」乐观偏差。

### 3.3 配置挂载

| 配置 | 说明 |
|------|------|
| Entry | 现有 `pattern_definition` + revision（必选） |
| Outcome Observation | 可极简：默认 `horizon_bars=20` + 标准 `return_horizons`，甚至零配置 |
| Outcome Pattern | 可选表 `pattern_outcome_definition(+revision)`，仅 Mode B |

正式 Run 锁定：`entry_id@version` + `outcome_mode` +（若有）`outcome_version` + 宇宙 + 区间 + 引擎版本。

---

## 4. 事实指标目录（Event Evaluation 产出）

下列全部是**事实**，写入事件行（JSON 列或宽表，实现自定；语义冻结）。

### 4.1 收益类（相对信号日收盘，T+1 起）

| 字段 | 含义 |
|------|------|
| `return_{h}` | 信号收盘 → 第 h 个交易日收盘的收益，h ∈ return_horizons |
| `return_horizon` | 主观测窗末日收益（= `return_{horizon_bars}`） |

### 4.2 路径极值 / 风险（主观测窗内，相对信号收盘或窗内自比——口径见下）

**拍板 V1 口径**（写进 meta，禁止 silently 改）：

- 收益类：相对 **信号日收盘**。  
- MFE / MAE：相对 **信号日收盘**，在 `[T+1 … T+H]` 的 high/low 上算。  
- `max_drawdown`：窗内从 running peak 到 low 的最大回撤（正数）。  

| 字段 | 含义 |
|------|------|
| `mfe` | Maximum Favorable Excursion |
| `mae` | Maximum Adverse Excursion |
| `max_drawdown` | 窗内最大回撤 |
| `volatility` | 窗内日收益波动（样本标准差） |
| `bull_ratio` | 阳线占比 |
| `up_days` | 上涨天数（close>prev_close） |
| `max_up_streak` | 最长连续上涨天数 |
| `highest_day` | 最高价出现的相对日序（1…H） |
| `lowest_day` | 最低价出现的相对日序 |
| `time_to_mfe` / `time_to_mae` | MFE/MAE 出现位置 ∈ (0,1] 或日序（实现锁定一种并写入 meta） |

### 4.3 覆盖 / 质量

| 字段 | 含义 |
|------|------|
| `forward_bars_available` | 实际可用未来 bar 数 |
| `forward_status` | `ok` / `truncated` / `insufficient` |
| `benchmark_return_{h}` | 可选：相对基准（如 HS300）的同期收益 |

### 4.4 Mode B 附加（仅 Pattern Outcome）

| 字段 | 含义 |
|------|------|
| `outcome_similarity` | 远期形态总分（**可选字段**，不是 Run 综合分） |
| `outcome_matched` | 是否 ≥ outcome threshold |
| `outcome_stage_similarity` | 各 Stage |
| `outcome_feature_similarity` / values | 可解释明细 |

**禁止**把 `outcome_similarity` 再与收益揉成引擎级「效果总分」。

---

## 5. Aggregation（只做描述统计）

对有效样本（`forward_status=ok`，或按字段非空）聚合，**全部为统计量**：

### 5.1 覆盖

- 事件数、股票数、交易日跨度  
- 事件覆盖率（有事件的股票占比 / 日均事件数等，定义写入报告 meta）  
- truncated / insufficient 计数  

### 5.2 各 horizon 收益

对每个 `return_{h}`：

- mean / median  
- P10 / P90（可加 P25/P75）  
- win_rate（>0 占比）  
- 样本数 `n_valid`  

### 5.3 路径统计

对 `mfe` / `mae` / `max_drawdown` / `volatility` / `bull_ratio` / …：

- mean / median（及必要分位）  

### 5.4 时间结构

- `highest_day` / `lowest_day` 的分布（均值或直方图桶）  
- `up_days` / `max_up_streak` 均值  

### 5.5 Mode B 附加

- Outcome 命中率（`outcome_matched`）  
- Outcome similarity 分布（mean/median/分位）——仍是**对该分数字段的统计**，不是新综合分  
- Stage / Feature 级均值表  

### 5.6 明确不输出

- 任何 `strategy_effect_score`  
- 任何「风险调整综合分」「稳定性分」作为引擎一等公民  

若产品以后要算，从事件表 SQL/二次任务生成，并单独版本化。

---

## 6. Storage（为后处理而存）

### 6.1 设计目标

> 一次回测，多次分析。  
> 新视图 = 新查询 / 新聚合 Job，不是新一次全历史 Matcher。

### 6.2 表（逻辑名）

**`pattern_event_run`**

| 字段 | 说明 |
|------|------|
| `run_id` | PK |
| `entry_pattern_id` / `entry_version` | 锁定 |
| `outcome_mode` | `observation` / `pattern` |
| `outcome_version` | Mode B 时必填 |
| `universe_spec` / `start` / `end` | |
| `horizon_bars` / `return_horizons_json` | |
| `anchor_mode` | V1=`t1_close` |
| `engine_version` / `code_hash` | 复现 |
| `dedup_policy` | 见 §7 |
| `status` / `created_at` / `duration_ms` | |
| `summary_json` | **聚合统计快照**（§5 全部可放这里，便于报告秒开） |

**`pattern_event`**

| 字段 | 说明 |
|------|------|
| `run_id` + `event_id` | |
| `code` / `signal_date` | |
| `entry_similarity` + entry 快照 JSON | |
| `metrics_json` | §4 全部事实（宽列也可，但 JSON 利于演进） |
| `outcome_json` | Mode B 明细；Mode A 可空 |
| `forward_status` | |

索引：`(run_id, code, signal_date)`、`(run_id, signal_date)`。

### 6.3 与「不固化评分」的关系

- `summary_json` 只存**描述统计**，可随时用事件表重算覆盖。  
- 允许缓存统计以加速报告；**不允许**把产品综合分写进引擎必出字段。  
- 指标目录新增字段：旧 Run 的 `metrics_json` 缺 key → 分析层当 NULL，或提供「只重算 Evaluation」的增量 Job（P1）。

---

## 7. Event Discovery 算法要点

```text
for date in trading_days(start, end):
  for code in universe(date):
    result = EntryMatcher.match(code, date, …)
    if result.matched:
      emit Event(code, date, entry_*)
```

### 7.1 去重（Dedup）

同一股票短期多次命中时，V1 提供策略（写入 Run meta）：

| policy | 行为 |
|--------|------|
| `none` | 全留 |
| `cooldown_h` | 命中后 H 个交易日内同票忽略（默认建议 `horizon_bars` 或可配） |

去重在 Discovery 后、Evaluation 前；被丢事件可不落库或落库标记 `deduped=true`（V1 可不落以省空间）。

### 7.2 无未来函数

- Entry：仅用 `≤ signal_date` 数据。  
- Evaluation：仅用 `> signal_date`（从 T+1 起）数据。

### 7.3 复权

与 Pattern 扫描一致：**前复权（qfq）** OHLC 计算远期事实（对齐 10/图表口径）。  
Run meta 记录 `price_adj=qfq`。

---

## 8. Statistics Report（报告长什么样）

报告是**统计报告**，不是评分卡。建议结构：

```text
# 覆盖
事件数 / 股票数 / 区间 / Entry@version / Outcome mode / horizon

# 收益（按 horizon 分表）
return_1 / 3 / 5 / 10 / 20 / 60
  mean | median | P10 | P90 | win_rate | n

# 路径
MFE | MAE | max_drawdown | volatility
  mean | median | …

# 时间结构
highest_day / lowest_day / up_days / max_up_streak
  …

# （仅 Mode B）
Outcome 命中率
Outcome similarity 分布
Stage / Feature 统计表

# 下钻
事件表（按 return_h / mae / … 排序过滤）
```

**禁止**作为报告主角：综合分 85 / 92 / 73、雷达图「效果四维」等（可放分析层实验）。

---

## 9. 系统落点（模块）

```text
quant_system/eventstats/          # 或 patterns/event_backtest/
  discovery.py                    # Entry 扫描 → Event
  observe.py                      # Mode A：事实指标
  pattern_outcome.py              # Mode B：Forward Matcher（可后置）
  aggregate.py                    # 描述统计
  store.py                        # Run / Event 读写
  report.py                       # summary_json → 报告 DTO
  runner.py                       # Job 编排
```

- **禁止**在 `aggregate.py` 引入「效果分」权重表。  
- Mode B 复用 FeatureCatalog + Target/Evaluator；Forward 窗口切割新建，不复用向左 Matcher 主循环。

---

## 10. API / CLI / Web（V1 切片）

### 10.1 Job

`pattern.event_stats`（名称可 bikeshed）：

参数：`pattern_id`、`entry_version`、区间、宇宙、`horizon_bars`、`return_horizons`、`outcome_mode`、`dedup_policy`、（Mode B）`outcome_version`。

### 10.2 读接口

- `GET /api/event-stats/runs`  
- `GET /api/event-stats/runs/{run_id}` → summary  
- `GET /api/event-stats/runs/{run_id}/events` → 分页/筛选/排序（按任意 metrics 字段）  

### 10.3 CLI

```bash
qs event-stats run --pattern RANGE_BREAKOUT --start … --end … --horizon 20
qs event-stats report --run-id …
```

### 10.4 Web

策略页 Tab建议：

1. 入场形态  
2. 事件统计（跑 Job + 统计报告 + 事件表）  
3. （可选）远期路径模板 —— 仅 Mode B 编辑器  

验收形态编辑器**不再**作为默认主路径；Observation 用表单数字即可。

---

## 11. 落地节奏

| 阶段 | 内容 |
|------|------|
| **P0** | Discovery + Observation 指标 + 落库 + 聚合 summary + 统计报告 API/页 + 事件下钻 |
| **P0′** | CLI；dedup cooldown；benchmark 可选 |
| **P1** | Mode B Pattern Outcome + 命中率/Stage 统计 |
| **P2** | 增量重算 Evaluation；分析层自定义评分插件（引擎外） |

**P0 验收**：

1. 同一配置可复现（code_hash + 版本锁定）。  
2. 事件表可直接查出 `AVG(return_10)`、`AVG(mae)`。  
3. 报告无综合分字段。  
4. 无未来函数（单测：信号日不进 MFE/收益）。  
5. 引擎包内 grep 不到 `strategy_effect_score` / `S_return` 类命名。

---

## 12. 决策速查

| # | 决策 |
|---|------|
| 1 | 模块定位 = **Event Statistics Engine** |
| 2 | 四职责：Discovery / Evaluation / Aggregation / Storage |
| 3 | **删除**引擎级综合评分体系 |
| 4 | Outcome 默认 **Observation**；Pattern Outcome 高级可选 |
| 5 | Entry 保留 Similarity；Outcome 默认只出 Metrics |
| 6 | 报告 = 统计报告，不是评分卡 |
| 7 | 原始事件落库，后处理可衍生新视图而不重跑 Matcher |
| 8 | 锚点 V1 = T+1；复权 = qfq |
| 9 | 与组合回测表分离 |

---

## 13. 待评审（少数）

1. 包名：`eventstats` vs `patterns/event_backtest`？  
2. Observation 默认 `horizon_bars`：20？  
3. Dedup 默认：`none` 还是 `cooldown = horizon`？  
4. Mode B 是否 P0 完全不做、接口只留 `outcome_mode` 枚举？  
5. `metrics_json` vs 强类型宽表（P0 偏 JSON 利于演进）？  

---

## 14. 与 v1 文档关系

v1 中 Entry×Outcome 同构打分、`strategy_effect_score`、balanced/risk-first profile 等**整段作废**。  
若需「远期像不像某形态」，归入本版 **Mode B**，且仍不产生策略综合分。  
