# 14 · Earnings Event Analytics（业绩事件分析）

> 状态：📝 **设计稿 v3**（2026-07-18）— 报告类型分层 + 可选分簇  
> 原名：Earnings Mispricing Engine（已废弃作模块名；Mispricing 仅为 Score Layer 的一种输出）  
> 依赖：05 数据层 / 13 Event Statistics / **cluster（相似度簇）** / disclosures + forecast_return_factors / valuation / kline  
> 非目标（V1）：组合回测、盘中分钟级反应、簇×特征全交互高阶项  
> 关联窄域原型：`analysis/forecast_return_factors.py`（中报预告短窗探索，保留）

---

## 0. Design Principles（冻结）

| # | 原则 |
|---|------|
| **P1** | 本模块的核心职责是构建 **Earnings Event Dataset（Event Panel）**，不是绑定某一种定价理论。 |
| **P2** | **模型是 Dataset 的消费者，不是核心。** 换 OLS / Ridge / Tree / LLM 都不应倒逼改表结构。 |
| **P3** | 任何模型都必须能消费**同一份** Event Panel（宽表：Raw / Derived / Targets）。 |
| **P4** | **Panel 一次构建，可重复拟合。** Fit / Predict / Explain 不得要求重爬事件。 |
| **P5** | Event Builder、Feature Builder、Target Builder、Regression Backend、Fair Value Estimator、Prediction Layer、Score Layer、Explain Engine **全部解耦**，仅通过稳定接口通信。 |
| **P6** | V1 默认实现可以很朴素（OLS + Median EY + contrib 解释），但**架构层禁止写死算法名**。 |

---

## 1. 模块定位与命名

### 1.1 为什么不叫 Mispricing Engine

整条链路实际是：

```text
Earnings Event
  → Feature Engineering
  → Return Model（Regression Backend）
  → Fair Value Estimator
  → Prediction Layer
  → Score Layer（其中一种输出才是 Mispricing Score）
  → Explain Engine
```

真正叫「Mispricing」的只有 **Score Layer 的一类产物**。  
模块正式名：**Earnings Event Analytics**（简称 EEA）。

未来可在同一模块下挂载、且**不改管道**：

- Earnings Surprise Analysis  
- Earnings Quality Analysis  
- Earnings Reaction Analysis  
- （乃至非业绩事件：回购 / 定增 / 减持 — 只换 Event Builder）

### 1.2 V1 产品要回答的问题

> 拿到某只股票当前（或刚披露）的业绩信息后，快速得到：  
> 1）相对历史同类场景，偏高估还是偏低估、大约多少（`premium_pct` / `mispricing_score`）；  
> 2）历史上这类特征组合对应的 **未来 5 / 10 / 20 交易日** 预期收益。  
> 3）拟合宇宙可选：**综合（全类型） / 仅中报 / 仅年报**。  
> 4）预测时可选：**是否纳入该股所在相似度簇** 对业绩反应的差异。

教科书：`Implied MCap ≈ PE × 年化归母`。现实用可观测特征 + 事后收益校准，不做「绝对真值」。

### 1.3 与相邻模块边界

| 模块 | 问的问题 | 与 EEA |
|------|----------|--------|
| 13 Event Statistics | Pattern 触发后价格发生了什么 | Target Builder **复用**其前瞻收益算法 |
| **cluster** | 股票相似度分区（Louvain 等） | Panel 挂 `cluster_id`；可选分簇模型 / 簇固定效应 |
| 中报预告因子分析页 | 短窗、单批 OLS 探索 | **保留**；EEA 是多年可复现生产路径 |
| 未来 Surprise / Quality | 另一类分析产物 | **共用** Event Panel + 管道，换 Feature / Score |

---

## 2. 最终架构（冻结）

```text
Earnings Events（原始披露 / 预告 / 快报 …）
        │
        ▼
   Event Builder          ← 唯一与「什么是事件」绑定的层
        │
        ▼
  Feature Builder         ← Raw → Derived
        │
        ▼
  Target Builder          ← ret_5d / 10d / 20d …
        │
        ▼
    Event Panel           ← 一次构建，多消费者
        │
        ├──────────────────┐
        ▼                  ▼
 Regression Backend   Fair Value Estimator
 (default: OLS)       (default: Median EY)
        │                  │
        └────────┬─────────┘
                 ▼
          Prediction Layer
          · expected_return_{5,10,20}d
          · fair_value / implied_fair_mcap
          · premium_pct
                 │
                 ▼
            Score Layer
          · mispricing_score
          · confidence
          · percentile
                 │
                 ▼
           Explain Engine
          · feature contribution
          · ranking
          · natural language（二期）
                 │
                 ▼
          API / Web / CLI
```

解耦要点：

| 解耦 | 含义 |
|------|------|
| Event ↔ Model | 换回归算法不改事件表 |
| Model ↔ Score | 预期收益 ≠ 错定价分数；Score 可换公式 |
| Fair Value ↔ Regression | 公允估计不依赖回归后端 |
| 一切模型 ↔ 同一 Panel | P3 |

---

## 3. Pipeline 分层详述

### 3.1 Event Builder

**输入**：数据源（EM 披露日历、预告、快报、正式财报公告等）  
**输出**：规范化 `EarningsEvent` 行（只含「事件本身」的原始事实）

职责：

- 解析 `event_kind` / `event_date` / `report_period` / `parent_np` / `parent_np_yoy` …
- 去重策略（V1：同 code+period+kind 保留**首次**公告日）
- **禁止**在此层算 PE、年化、收益

扩展：研究回购/定增/减持/并购时，**只替换 Event Builder**（或新增 Builder 写入统一事件接口），下游可复用。

#### 3.1.1 `event_kind`（V1）

| kind | 说明 | 后续年化（在 Feature Builder） |
|------|------|-------------------------------|
| `annual` | 正式年报 | ×1 |
| `interim` | 正式中报 | ×2 |
| `q1` / `q3` | 一季报 / 三季报 | ×4 / ×4/3 |
| `forecast` | 业绩预告 | 按报告期进度 |
| `express` | 业绩快报 | 同正式报告进度 |

事件入库：全 kind（含季报）。  
**拟合宇宙**由 Model Scope 决定（§3.10），不是 Event Builder 过滤掉数据。

#### 3.1.2 `event_date`

必须用真实公告日；**禁止** `report_period+45d` 作主路径（THS 合成 `ann_date` 仅 fallback）。

### 3.2 Feature Builder

**输入**：EarningsEvent + 行情/估值/日特征（as_of）  
**输出**：Derived Features（宽列）

#### 年化规则（V1 冻结，属 Feature 而非 Event）

| 进度 | `annualized_parent_np` |
|------|------------------------|
| 年报 / 年度预告·快报 | `parent_np` |
| 中报 / 中报预告·快报 | `parent_np × 2` |
| 一季报 | `parent_np × 4` |
| 三季报 | `parent_np × 4/3` |

`annualized ≤ 0`：不进主回归特征集；Score 可返回 `unavailable_reason=loss_making`。

#### 估值与位置（as_of）

- 估值：`daily_valuation` 在 `event_date`（≤）最近条 → `pe_ttm`, `mcap`, …  
- 价格位置特征用 **T-1** 交易日（降泄漏）；收益锚点见 Target Builder。

| Derived（示例） | 定义 |
|-----------------|------|
| `ln_mcap` | `ln(mcap)` |
| `ey_event` | `annualized_parent_np / (mcap×1e8)` |
| `ey_event_pct` | `ey_event × 100` |
| `pe_event` | `(mcap×1e8) / annualized_parent_np` |
| `pe_rel` | `pe_ttm / pe_event - 1`（与 ey 高相关则 V1 可丢掉） |
| `yoy_pct` | `parent_np_yoy × 100` |
| `range_pos_250d` / `range_pos_750d` | 高/低位 |
| `dist_to_high_250d` | `close/high_250 - 1` |

V1 回归用特征集（可配置，写入 model 元数据）：

`pe_ttm`, `ln_mcap`, `yoy_pct`, `ey_event_pct`, `range_pos_250d`  
（综合模型可加 kind 哑变量；分簇见 §3.10 / §3.11）

Feature Builder 另写入（供分簇，**不作强制回归自变量**）：

| 字段 | 含义 |
|------|------|
| `cluster_run_id` | 事件日可用的簇分区 run（见 §3.11） |
| `cluster_id` | 该股在该 run 下的簇编号；无归属则空 |

### 3.3 Target Builder

**输入**：event_date + kline  
**输出**：Targets

```text
anchor = event_date 当日收盘；非交易日 → 其后首个交易日
ret_h  = close[anchor + h] / close[anchor] - 1
h ∈ {5, 10, 20}   # V1；可扩展 1/3/60
```

不足 h 根 K：该 target 置空，该行不进对应 horizon 的拟合。  
实现上**复用** eventstats / `forward_returns` 的前复权逻辑，本层只做 glue。

### 3.4 Event Panel（存储契约）

**禁止**把主特征塞进单一 `features_json` 当主存储。  
表建议：`earnings_event_panel`，字段分三类宽列 + 可选扩展 JSON。

```text
-- Identity
panel_id / event_id
code
event_date
report_period
event_kind
source

-- Raw Features（事件原始事实）
parent_np
parent_np_yoy
predict_type
title                  -- 可选
raw_extra_json         -- 扩展，非主查询路径

-- Derived Features（Feature Builder 产出）
annualized_parent_np
pe_ttm
mcap
ln_mcap
ey_event
ey_event_pct
pe_event
pe_rel
yoy_pct
range_pos_250d
range_pos_750d
dist_to_high_250d
cluster_run_id         -- 可选；分簇用
cluster_id             -- 可选；分簇用
valuation_date
feature_asof_date      -- 通常 T-1
derived_extra_json     -- 扩展

-- Targets
ret_5d
ret_10d
ret_20d
target_extra_json      -- 如未来加 mfe/mae

-- Meta
built_at
panel_tag
```

原则：SQL / Notebook / Web **直接扫列**；JSON 仅扩展。

上游事件事实表可另存 `earnings_disclosure_event`（Event Builder 落库）；Panel 是 join 后的分析表。

### 3.5 Regression Backend（接口，不绑 OLS）

```text
protocol RegressionBackend:
  id: str                          # "ols" | "ridge" | …
  fit(panel, feature_cols, target_col, params) -> FittedModel
  predict(fitted, X) -> y_hat
  # FittedModel 至少含：coef / intercept / means / stds / metrics(r2,…)
```

| 实现 | 阶段 |
|------|------|
| **OLS**（`numpy.linalg.lstsq`） | V1 默认 |
| Ridge / Lasso / ElasticNet / Huber | 二期可插拔 |
| 树模型等 | 只要能 `predict` + 可选贡献，即可挂 Score/Explain |

每个 horizon **独立** `fit`（V1）。  
Winsorize 1%/99% 作为 Backend 前的可选 `PanelTransform`，不写进 OLS 内部。

最低样本：`n ≥ max(80, 10 × k)`。

### 3.6 Fair Value Estimator（接口，不绑 median）

```text
protocol FairValueEstimator:
  id: str                          # "median_ey" | "industry_median_ey" | …
  fit(panel, context) -> FairValueModel
  estimate(model, row_or_features) -> FairValueResult
    # fair_ey / fair_pe / implied_fair_mcap / method_meta
```

| 实现 | 阶段 |
|------|------|
| **Median EY**（按 `event_kind` 分组中位数） | V1 默认 |
| Industry Median / Rolling Median / Weighted Median | 二期 |
| Regression Fair EY / Bayesian Fair EY | 三期 |

`premium_pct` 的计算放在 **Prediction Layer**（消费 Estimator 结果），不写死在 Estimator 内也可以；V1 约定：

```text
implied_fair_mcap_yi = (annualized_parent_np / 1e8) / fair_ey
premium_pct = mcap / implied_fair_mcap_yi - 1
# >0 相对公允偏贵（高估），<0 偏低估
```

UI 标明所用 estimator id（如 `median_ey`）。

### 3.7 Prediction Layer

**只负责预测与公允结果，不负责「分数语义」。**

输入：Fitted Regression Model(s) + FairValueModel + 当前特征行  

输出（稳定 schema）：

```text
expected_return_5d
expected_return_10d
expected_return_20d
fair_ey / fair_pe          # 视 estimator
implied_fair_mcap
premium_pct
prediction_meta            # model_id, backend_id, estimator_id, …
# 二期可加：prediction_interval_*, residual_vol, …
```

**禁止**在本层直接产出 `mispricing_score`。

### 3.8 Score Layer

消费 Prediction Layer（+ 可选 Panel 分位信息），产出面向决策/展示的分数：

```text
mispricing_score           # V1 建议：综合 premium 与 -z(E[ret]) 的可配置映射
confidence                 # V1 可先用简单代理：特征完整度 / 历史密度
percentile                 # 如 ey_event 或 premium 在同类 panel 中的分位
score_meta
```

以后增加 Uncertainty、多分数体系，**只改 Score Layer**。

V1 默认映射（可配置，写入 model 元数据）：

```text
mispricing_score ≈ normalize(premium_pct)     # 主：贵贱
# 可选辅：-z(expected_return_20d) 作为「预期偏弱」维度，勿与 premium 混成一个黑箱
```

### 3.9 Explain Engine

独立层，消费：Prediction + Score + FittedModel + 当前特征。

V1 输出：

```text
feature_contributions[]    # {key, value, coef, contrib, rank}
contribution_ranking[]
```

二期：

```text
natural_language           # 模板或 LLM，只读 Explain 结构，不重算模型
```

`contrib_i = bi * (xi - mean_i)`（或 `bi*xi`，在 meta 标明）。  
AI / Web **只消费 Explain Engine**，不解析 raw coef。

### 3.10 Model Scope：综合 / 仅中报 / 仅年报（V1 必做）

**同一份 Event Panel**，多次 `fit`，产出多套 `earnings_analytics_model`。  
预测时由用户（或 Web）选择 `model_scope`。

| `model_scope` | 拟合用的 panel 子集 | 典型用途 |
|---------------|---------------------|----------|
| `all` | 主池：`forecast + express + annual + interim`（季报默认不含） | 综合判断 |
| `interim` | 中报正式 + 中报预告/快报（`event_kind`∈{interim, forecast/express 且报告期为 6-30}） | 「只信中报季节」 |
| `annual` | 年报正式 + 年度预告/快报（报告期 12-31） | 「只信年报」 |

约定：

- Scope 过滤在 **fit 读 Panel 时**完成，不删 Panel 行。  
- 每个 scope 独立存一套三 horizon 系数 + 独立 Fair Value（Median EY 也按该子集估）。  
- `/predict` 必传或默认 `model_scope`（默认 `all`）。  
- Web：打分器上三个 Tab / 下拉：**综合 | 中报 | 年报**。

`interim` / `annual` 的精确 kind 规则写入 `model.meta.filter_sql` 或 `filter_spec`，避免口口径漂移。

### 3.11 分簇：能否做、怎么做（V1 纳入可选路径）

#### 结论

**可以分析不同簇对业绩披露的反应差异**，且现有 `StockClusterRun` / `StockCluster` / `StockClusterMember` 已足够挂载。  
约束：小簇样本不足时不能硬拟合，必须有 fallback。

#### Panel 如何挂簇

构建 Panel 时（Feature Builder）：

```text
cluster_run_id = 选定的「分析用」簇 run
  推荐 V1：固定使用「当前最新成功 run」（meta 写死 run_id）
  二期：event_date 之前最近成功 run（时变分区）
cluster_id = membership[code]  or null
```

无簇归属的事件：`cluster_id = null`，分簇模式下走 **global fallback**。

#### 簇差异的两种拟合模式（协议层）

| `cluster_mode` | 做法 | 何时用 |
|----------------|------|--------|
| `none` | 忽略簇（默认） | 综合/中报/年报主路径 |
| `fixed_effect` | 全局回归 + 簇哑变量（截距不同，斜率共用） | 样本中等；回答「哪簇整体偏强/偏弱」 |
| `per_cluster` | 每个 `cluster_id` 单独 OLS（斜率可不同） | 大簇且 `n_c ≥ max(40, 8×k)`；回答「簇内定价结构不同」 |

V1 **两者都实现接口**；默认对外：

- 总览页：`fixed_effect` 下各簇截距 / 平均残差表 → 「簇间业绩反应差异」  
- 单票打分：`use_cluster=false` → `cluster_mode=none` 的模型；`use_cluster=true` → 优先 `per_cluster`（该簇够样本），否则 `fixed_effect` 调整，再否则 fallback `none` 并在 `prediction_meta` 标明。

#### 与 model_scope 组合

```text
model_key ≈ (model_scope, cluster_mode[, cluster_id])
例：
  (all, none)
  (interim, none)
  (annual, none)
  (all, fixed_effect)
  (all, per_cluster, cid=3)
  (interim, per_cluster, cid=3)
```

不必一次 fit 笛卡尔积爆炸：  
`fit` 支持 `scopes=[all,interim,annual]` × `cluster_modes=[none, fixed_effect]`，  
`per_cluster` 按「样本达标的簇」增量生成子模型。

#### Predict 开关

```text
POST /predict
{
  ...
  "model_scope": "interim",   # all | interim | annual
  "use_cluster": true,        # 是否考虑所在簇
  "cluster_run_id": null      # 可选；默认用模型训练时的 run
}
```

行为：

1. 解析股票在指定 run 下的 `cluster_id`  
2. `use_cluster=false` → 用 `(scope, none)`  
3. `use_cluster=true` → 选 `(scope, per_cluster, cid)` 或 `(scope, fixed_effect)` + 该簇效应  
4. Explain 中增加一行：`cluster_effect`（若有）

#### 产品上「簇差异」怎么看

Web 增加一小节（不阻塞单票打分）：

- 各簇：事件数、上涨占比、`ret_5/10/20` 均值、相对全局的超额  
- `fixed_effect` 下簇截距排序（谁对业绩更「钝」/更「敏」）  
- 点击簇 → 可钻取 panel 子集

这回答的是：**不同相似度簇，在业绩披露后的平均反应是否系统不同**；不是因果。

---

## 4. 代码包与接口草图（实现指引）

建议包路径（可调）：

```text
quant_system/earnings_analytics/
  events/          # Event Builder + earnings_disclosure_event IO
  features/        # Feature Builder + annualize rules
  targets/         # Target Builder
  panel/           # build / load Event Panel
  regression/      # protocol + ols.py (+ 未来 ridge…)
  fair_value/      # protocol + median_ey.py
  prediction/      # Prediction Layer
  score/           # Score Layer
  explain/         # Explain Engine
  api_schemas.py
```

CLI 与 API 共用同一服务函数，避免两套逻辑。

---

## 5. API 拆层

前缀建议：`/api/analysis/earnings-events`（或 `/api/eea`）

| 方法 | 路径 | 层 | 作用 |
|------|------|-----|------|
| POST | `/build-panel` | Panel | 按区间/tag 构建或增量更新 Panel（含 cluster 挂载） |
| POST | `/fit` | Regression + FairValue | `scopes` × `cluster_modes`；写多套 model |
| POST | `/predict` | Prediction | 单票/批量；`model_scope` + `use_cluster` |
| POST | `/explain` | Explain | 对某次 predict 做贡献分解（可含 cluster_effect） |
| GET | `/models` | — | 模型列表（含 scope / cluster_mode） |
| GET | `/models/{id}` | — | 公式、backend、estimator、指标 |
| GET | `/panel/summary` | — | 描述统计 / 分位 |
| GET | `/panel/by-cluster` | — | 簇间业绩反应差异摘要（V1） |

便利端点（可选，非架构核心）：

```text
POST /score   = predict + score_layer + explain   # Web 一键；内部仍调三层
```

请求示例（predict）：

```text
POST /predict
{
  "code": "600000",
  "as_of": "2026-07-15",
  "event_kind": "interim",
  "parent_np": 1.2e9,
  "parent_np_yoy": 0.15,
  "model_scope": "all",       # all | interim | annual
  "use_cluster": false,       # true 时纳入所在簇效应
  "model_id": "latest"        # 可选；与 scope/cluster 解析冲突时以显式 id 为准
}
```

现有 `GET /disclosures/factor-analysis` **保留**为短窗探索，不塞进 EEA 核心路径。

---

## 6. 落库产物命名

| 表 / 对象 | 用途 |
|-----------|------|
| `earnings_disclosure_event` | Event Builder 产出（原始事件） |
| `earnings_event_panel` | Raw + Derived + Targets 宽表 |
| `earnings_analytics_model` | fit 结果：backend_id、estimator_id、feature_cols、各 horizon 参数、metrics |

旧名 `earnings_mispricing_model` **不要用**；避免模块名泄漏进表名。

`daily_valuation`：取消 10 日截断（或 KEEP_YEARS≥5）+ 历史 backfill — **Phase 0 阻塞项**。

---

## 7. 数据地基（Phase 0，功能与 v1 稿相同）

| 需要 | 现状 | 动作 |
|------|------|------|
| 真实披露日 | 现拉未多年落库 | Event Builder 回填 |
| 归母 NP | DB 多为非归母/合成日 | 事件上持久化 parent_np |
| 公告日 PE/市值 | valuation 约留 10 日 | 长期保留 + backfill |
| 5/10/20 收益 | 算法可复用 | Target Builder glue |
| 股价分位 | 部分在 DailyFeature | Feature Builder 对齐 |

验收：随机 20 事件人工核公告日、归母、PE、T+20。

---

## 8. 分阶段交付（V1 功能不变，接口按新架构）

### Phase 0 — Dataset

1. valuation 长期保留 + backfill  
2. Event Builder → `earnings_disclosure_event`  
3. Feature + Target → `earnings_event_panel`（宽列三类 + `cluster_id`/`cluster_run_id`）

### Phase 1 — 默认可插拔实现 + 打通（含 scope + 可选簇）

1. Regression Backend = **OLS**；Fair Value = **Median EY**  
2. **Fit 三套 scope**：`all` / `interim` / `annual`（`cluster_mode=none`）  
3. **Fit 簇模式**：`fixed_effect`（按 scope=all 至少一套）+ 样本达标簇的 `per_cluster`  
4. Prediction + Score + Explain；`predict` 支持 `model_scope` + `use_cluster`  
5. API：`build-panel` / `fit` / `predict` / `explain` / `panel/by-cluster`  
6. Web：打分器可选综合/中报/年报；开关「考虑所在簇」；簇差异摘要表

### Phase 2 — 硬化

1. 亏损规则、滚动样本外、系数稳定性（含跨簇稳定性）  
2. 时变 `cluster_run`（按 event_date 选 run）  
3. 披露日历批量 predict  
4. Fair EY 按 `range_pos` 分桶（可选）

### Phase 3 — 扩展（架构已留位）

- 新 Regression：Ridge / Huber …  
- 新 Fair Value：Industry / Rolling / Regression Fair EY  
- 簇×关键特征交互（不仅截距）  
- Surprise / Quality / Reaction 分析（新 Feature + Score，同 Panel）  
- 非业绩 Event Builder  
- Explain 自然语言  
- Prediction Interval / 更认真的 confidence  

---

## 9. 方法论免责（UI）

1. 机械年化忽略季节性 → kind 分层缓解。  
2. 前瞻收益含市场 β；二期可加对冲残差作 Y。  
3. 预告样本有选择偏差；标明宇宙。  
4. 系数是相关非因果。  
5. 输出是条件期望与相对分位，非投资建议。

---

## 10. 开放细节（Phase 0 前冻结）

1. 收益锚点 **T 日**收盘；特征 **T-1**（与泄漏控制一致）。  
2. `all` scope 是否含季报（建议：入库；主拟合先不含）。  
3. Median EY 是否按 `range_pos` 分桶（建议 Phase 1 不分桶，Phase 2 可选）。  
4. V1 簇 run：固定最新成功 run vs 时变（建议 Phase 1 **固定 run**，Phase 2 时变）。  
5. `interim` scope 是否含「中报预告/快报」（建议：**含**，与正式中报同属中报季节）。

---

## 11. 一页纸（给实现用）

```text
# Build panel
events = EventBuilder.run(date_range)
for e in events:
  raw = e.raw_fields
  derived = FeatureBuilder.transform(e, valuation, kline, cluster_run)
  targets = TargetBuilder.compute(e, kline, horizons=[5,10,20])
  Panel.upsert(raw, derived, targets)

# Fit scopes × cluster modes
for scope in (all, interim, annual):
  sub = Panel.filter(scope)
  save Model(scope, none, OLS.fit(sub), MedianEY.fit(sub))
  save Model(scope, fixed_effect, OLS.fit(sub + cluster_dummies), …)
  for cid in large_enough_clusters(sub):
    save Model(scope, per_cluster, cid, OLS.fit(sub|cid), …)

# Predict (online)
row = FeatureBuilder.transform_online(code, kind, parent_np, as_of, use_cluster)
model = resolve(model_scope, use_cluster, row.cluster_id)
pred = PredictionLayer.run(row, model)
score = ScoreLayer.run(pred, panel_context)
expl  = ExplainEngine.run(row, pred, score, model)  # may include cluster_effect
return pred + score + expl
```

---

## 12. 修订对照

| 建议 | 落点 |
|------|------|
| 模块勿叫 Mispricing Engine | §1 Earnings Event Analytics |
| Fair Value 不绑 median | §3.6 Fair Value Estimator |
| 回归不绑 OLS | §3.5 Regression Backend |
| Score 与 Prediction 解耦 | §3.7 / §3.8 |
| Panel 三类宽列 | §3.4 |
| Explain 独立 | §3.9 |
| API 拆 build/fit/predict/explain | §5 |
| Event Builder 独立、管道可复用 | §2 / §3.1 |
| Design Principles | §0 P1–P6 |
| **综合 / 仅中报 / 仅年报** | §3.10，Phase 1 必做 |
| **可选分簇差异** | §3.11，`use_cluster` + `panel/by-cluster` |
