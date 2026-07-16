# 10 · Abnormal Pattern Engine（异动模式引擎）设计方案

> 状态：🚧 **V2 已落地 P1**（Pattern Engine + 4 模式 + CLI；Global Rank / 日报专区待接）
> 依赖阶段：1(架构) / 6(特征质量) / 7(策略评分日报) / 9(关系层，可选)
> 定位：在 `daily_feature + daily_kline` 之上，构建以 **Pattern（模式）为一等公民** 的异动检测层。每种模式独立定义门槛、打分与排名；系统输出「今日各模式 TopN」，而不是一张「综合异动 Top30」。

---

## 0. 一句话概述

异动没有唯一标准。横盘放量突破、底部启动、趋势加速、一年新高……**模式之间不可比**，把它们捏成一个 0~100 综合分会制造伪序。

本系统设计为：

```text
Pattern  →  Candidate  →  Pattern Score  →  Pattern Rank  →  (可选) Global Rank
```

- **Pattern** 是第一公民：自带硬条件、特征依赖、阈值、评分规则、reasons。
- **Pattern Score** 只用于**同模式内部排序**，不跨模式比较。
- **Parameter Scan** 用多轮由严到松的参数找到「最标准 → 略宽松」的候选，而不是靠综合分区分强弱。
- 若将来要跨模式总榜，另加轻量 **Rank Engine**（排序，不重算一套综合分）。

> **相对已废止的 V1（综合评分）核心变化**：
> 1. 删除「全市场统一六维加权 + regime 融合总分」作为系统核心。
> 2. 改为 Pattern Engine；新增模式 = 新增一个 Pattern 配置/类。
> 3. 日报主产出从「综合 Top30」改为「各模式 Top10」。
> 4. Score 降级为 Pattern 内排序工具；可选全局排序单独一层。

---

## 1. 设计目标与边界

### 1.1 为什么不用综合分做核心

| 现象 | 综合分做法的问题 | Pattern 做法 |
|---|---|---|
| 横盘突破 80 vs 趋势加速 75 | 暗示前者「更值得关注」——伪序 | 分属两榜，各自 Top |
| 牛市满屏突破 / 熊市偶见底部 | 一套权重难以同时最优 | 各 Pattern 独立门槛，市况只影响「哪类 Pattern 更值得看」 |
| 调参 | 改全局权重牵一发而动全身 | 只改该 Pattern 的 Config / Scan 档位 |
| 可解释 | 「综合 82 分」难叙述 | 「命中横盘放量突破，档位 L1，模式内第 3」 |

### 1.2 能力全景

| 能力 | 说明 | 阶段 |
|---|---|---|
| Pattern 注册与扫描 | 多 Pattern 并行跑宇宙 | **P1** |
| Parameter Scan | 由严到松多档，凑够数量或扫完 | **P1** |
| Pattern 内评分 + TopN | `pattern_score` 仅模式内可比 | **P1** |
| 分模式日报 / CLI | `今日横盘突破 TOP10` 等 | **P1** |
| 一票多 Pattern | 同一股票可命中多个模式（多行） | **P1** |
| 可选 Global Rank | 轻量跨模式排序（非综合分重算） | **P2** |
| 更多 Pattern | 缩量后放量、放量反包、放量长阳… | P2+ |
| Theme / 关系层加分 | 仅作 Rank Engine 特征 | P2 |
| ML 学 Pattern 权重 | 未来 | 明确不做于 P1 |

### 1.3 P1 范围

- 宇宙：与 selector 一致（≈主板 3200，受 pool / board 约束）
- 落地 **4 个 Pattern**（见 §5）：`RANGE_BREAKOUT` / `BOTTOM_LAUNCH` / `TREND_ACCEL` / `ATH_250`
- 每模式默认 Top **10**（可配）；Scan 最多 3 档
- 性能：全 Pattern 合计 **≤ 5s**（特征已就绪）
- **不做** Global Rank（接口预留）

### 1.4 明确不做

- 不做跨 Pattern 的「综合异动分」作为主排序键
- 不在本模块重算 MA/MACD（读 feature）
- 不替代 strategy（Pattern 是扫描层；策略仍可独立存在，P2 可消费 Pattern 命中）
- 不做盘中分钟 Pattern（日线收盘批处理）

### 1.5 与现有模块关系

```text
daily_feature / daily_kline
        │
        ▼
 Abnormal Pattern Engine
   ├── RANGE_BREAKOUT  → Top10
   ├── BOTTOM_LAUNCH   → Top10
   ├── TREND_ACCEL     → Top10
   └── ATH_250         → Top10
        │
        ├──► report「今日异动·分模式」
        ├──► CLI qs abnormal ...
        └──► (P2) Rank Engine → 跨模式阅读顺序
                    │
              stock_selector / AI（可选消费）
```

---

## 2. 核心概念（第一公民层级）

| 概念 | 定义 | 可比范围 |
|---|---|---|
| **Pattern** | 一种可命名的异动形态 + 完整 Config | — |
| **Candidate** | 通过某档 Scan 硬条件的 (date, code, pattern) | — |
| **Pattern Score** | 0~100，该模式下的相对强弱 | **仅同 Pattern** |
| **Pattern Rank** | 同日同 Pattern 内按 score 降序的名次 | **仅同 Pattern** |
| **Scan Level** | 参数档位 L1(最严)…Lk(最松) | 同 Pattern 内：L1 优于 L2（先比档位再比分） |
| **Global Rank**（可选） | 跨模式阅读顺序 | 展示用，不是「更真的异动分」 |

**排序键（Pattern 内，P1 锁定）**：

```text
1) scan_level ASC   （L1 最严，排前面）
2) pattern_score DESC
3) amount DESC      （同分平局）
```

这样「最标准的横盘突破」永远排在「放宽才进来的」前面，而不需要靠综合分硬分高下。

---

## 3. PatternConfig（每个 Pattern 的契约）

### 3.1 结构

```text
PatternConfig
  pattern_id: str              # e.g. RANGE_BREAKOUT
  display_name: str            # 横盘放量突破
  required_features: list[str] # 缺任一关键字段 → 跳过该票（或整 Pattern 告警）
  exclude:                     # 公共否决（可继承默认）
    - one_word_limit
    - st / dq_blacklist
    - min_list_days
  scan_levels: list[ScanLevel] # 由严到松，至少 1 档
  score_rules: ScoreRules      # 通过硬条件后的打分
  reason_templates: ...        # 文案
  top_n: int                   # 默认 10
  enabled: bool
```

```text
ScanLevel
  level: int                   # 1 = 最严
  filters: dict[str, Rule]     # 全部满足才进 Candidate
  # 例: amplitude_20d_max=10, volume_ratio_min=3, return_1d_min=5, amount_min=3e8
```

```text
ScoreRules
  # 模式内专用，允许各 Pattern 不同
  components: list[{name, weight, mapper}]  # mapper: 锚点表 / 布尔加分
  # 仅用于同 Pattern 排序，权重不必跨 Pattern 对齐
```

### 3.2 扩展方式

新增模式 =：

1. 新增一个 `PatternConfig`（或 `patterns/xxx.py` 中的类）  
2. 注册到 `PATTERN_REGISTRY`  
3. **不改表结构**（`pattern_id` 长表）  
4. 不改 Fusion / 全局权重（因为没有全局综合分）

### 3.3 与「策略 Strategy」的区别

| | Pattern（本模块） | Strategy（selector） |
|---|---|---|
| 目标 | 描述「今天出现了什么形态」 | 「是否符合选股逻辑并给综合选股分」 |
| 输出 | 分模式榜 | 跨策略共振后的选股 TopN |
| 一票多命中 | 鼓励（多行） | 也支持，但会融成分 |
| 参数扫描 | 一等能力 | 通常固定阈值 |

两者可并存；P2 可选「命中某 Pattern → selector 加分/入观察」。

---

## 4. 流水线

```text
1. 加载当日 feature + 必要 kline（全宇宙一次）
2. 计算共享派生量（如 amplitude_20d、market_median_return）一次
3. for pattern in enabled_patterns:
     candidates = []
     for level in scan_levels:          # L1 → L2 → L3
         batch = apply_filters(universe, level)
         # 已在更严档命中的 code 不再降档重复计入（保留最高档）
         candidates.merge(batch, keep_best_level=True)
         if len(candidates) >= pattern.target_min:  # 可选早停
             break
     for c in candidates:
         c.pattern_score = pattern.score(c)
         c.reasons = pattern.reasons(c)
     rank within pattern
     persist + expose TopN
4. (P2) optional global_rank(all pattern hits)
```

**同一股票多 Pattern**：保留多行，例如既是「横盘突破」又是「一年新高」——这是信息，不是冲突。

**Scan 早停**：某档已凑够 `target_min`（如 10）可停止放宽；也可强制跑完所有档以便回测统计「有多少是 L1 纯种」。P1 默认：**跑完所有档**，输出时按排序键截 TopN（更干净，利回测）。

---

## 5. P1 四个 Pattern（规格）

以下阈值为默认值，全部进 Config，可改。

### 5.1 `RANGE_BREAKOUT` · 横盘放量突破

**语义**：近端波动收敛后，放量突破短线前高。

| Scan | 振幅(20d) | volume_ratio | 突破 | return_1d | amount |
|---|---|---|---|---|---|
| L1 | < 10% | ≥ 3.0 | break_high_20d | ≥ 5% | ≥ 3 亿 |
| L2 | < 12% | ≥ 2.5 | break_high_20d | ≥ 4% | ≥ 2.5 亿 |
| L3 | < 15% | ≥ 2.0 | break_high_20d | ≥ 3% | ≥ 2 亿 |

公共：阳线、非一字、非 ST。

**振幅定义**（现场算或进 feature）：

\[
amplitude\_20d = \frac{\max(high_{20}) - \min(low_{20})}{\min(low_{20})} \times 100\%
\]

**模式内评分（示例）**：量比 log 锚点 40% + BreakDistance/ATR 30% + 涨幅 15% + 成交额 15%。  
（权重只在本 Pattern 内有意义。）

### 5.2 `BOTTOM_LAUNCH` · 底部启动

**语义**：低位区放量转强，偏左侧/底部攻击。

| Scan | range_pos_250 | volume_ratio | return_1d | 其它硬条件 |
|---|---|---|---|---|
| L1 | ≤ 0.25 | ≥ 2.5 | ≥ 5% | MACD 金叉 + MA5 上穿 MA10（或当日金叉/上穿） |
| L2 | ≤ 0.30 | ≥ 2.0 | ≥ 4% | MACD 金叉 **或** MA5>MA10 |
| L3 | ≤ 0.35 | ≥ 2.0 | ≥ 4% | macd_hist>0 或 ma_bull_arrange |

**评分侧重**：位置（低更好）+ 相对强度 + 量比；突破不是必须。

### 5.3 `TREND_ACCEL` · 趋势加速

**语义**：已在趋势中，继续放量加速，而非底部首次启动。

| Scan | 均线 | return_5d | volume | 突破 |
|---|---|---|---|---|
| L1 | close>MA5>MA10>MA20 | ≥ 12% | volume_ratio≥2.5 且连 2 日≥2 | break_high_60d |
| L2 | 同上 | ≥ 8% | volume_ratio≥2.0 | break_high_60d |
| L3 | ma_bull_arrange | ≥ 8% | volume_ratio≥1.8 | break_high_20d |

**评分侧重**：5 日涨幅质量、量能延续、突破距离；**位置分故意低权或反向**（趋势股常在偏高位）。

### 5.4 `ATH_250` · 突破近一年新高

**语义**：站上 250 日前高，流动性足够。

| Scan | break | volume_ratio | amount | 质量 |
|---|---|---|---|---|
| L1 | break_high_250d | ≥ 2.5 | ≥ 8 亿 | BreakDistance ≥ 0.5 ATR |
| L2 | break_high_250d | ≥ 2.0 | ≥ 5 亿 | Distance ≥ 0.2 ATR |
| L3 | break_high_250d | ≥ 1.8 | ≥ 5 亿 | Distance ≥ 0（真突破即可） |

**评分侧重**：突破质量 + 成交额 + 相对强度；不与「底部启动」比高低。

### 5.5 P2 Pattern 池（只列名，不写死阈值）

- `VOL_SHRINK_THEN_SPIKE` 缩量整理后放量  
- `BULLISH_ENGULF` 放量反包  
- `LONG_YANG` 放量长阳  
- `GAP_UP` 向上跳空  
- `LIMIT_UP_OPEN` 非一字涨停异动  

---

## 6. Pattern Score（模式内排序工具）

### 6.1 原则

1. **只回答**：在这个 Pattern 的候选人里，谁更「典型 / 更强」？  
2. **不回答**：横盘突破是否优于趋势加速？  
3. 各 Pattern 的组件与权重**允许完全不同**，无需归一到同一套全局维。  
4. 仍建议用饱和锚点（log 量比、ATR 距离），避免极端值刷分——但这是 Pattern 实现细节，不是系统哲学。

### 6.2 通用可选组件（工具箱，按需取用）

| 组件 | 适用 |
|---|---|
| volume_ratio 锚点分 | 多数 Pattern |
| BreakDistance/ATR | 突破类 |
| amount 锚点分 | 要流动性的 Pattern |
| relative_return（相对市场中位数） | 多数 Pattern 建议接入 |
| range_pos / ma250_bias | 底部类 |
| return_5d / 连续放量天数 | 趋势类 |

V1 里论证过的 relative strength、突破质量、连续放量，**作为工具箱保留**，挂到合适的 Pattern 上，而不是强制每只股票都算「全局六维再融合」。

### 6.3 与 Scan Level 的关系

Score **不替代**档位：L1 候选默认排在所有 L2 之前。  
Score 解决的是：**同一档内**谁更靠前。

---

## 7. Parameter Scan（参数扫描）

### 7.1 动机

综合分用连续分值区分「强/弱」；Pattern 体系用 **离散档位**表达：

- L1：教科书级、最典型  
- L2：标准  
- L3：可观察、略宽松  

用户看榜时先看 L1 有几只；没有再往下看——比看「综合 82 vs 76」更符合交易直觉。

### 7.2 规则

1. 档位必须 **单调放宽**（更松档的可行域 ⊇ 更严档）。  
2. 同一 code 只保留 **最严命中档**（best level）。  
3. 回测按 level 分层统计：L1 的前瞻收益是否系统性好于 L3——这是 Pattern 是否定得靠谱的核心检验。

### 7.3 与「凑数量」的关系

可配置 `target_min`：若 L1 已 ≥ TopN，仍建议落库全部 L1（回测用），展示只取 TopN。  
**不要**为了凑满 Top10 而无底放宽到 L10；最多 3 档（P1），不够就显示「今日该模式仅 N 只」。

---

## 8. 可选 Global Rank Engine（P2）

### 8.1 定位

只解决：**阅读顺序**（日报第一节先看谁），**不是**「更真实的异动分」。

输入：各 Pattern 的命中行（已有 pattern_id / scan_level / pattern_score / amount / risk_flags / regime）。

输出：`global_rank` 整数 + 简短 `rank_reason`。

### 8.2 建议算法（轻量，禁止重算综合分）

伪排序键示例：

```text
priority(pattern_id, regime)   # 表驱动：熊市抬高 BOTTOM_LAUNCH，牛市抬高 TREND_ACCEL/ATH
→ scan_level ASC
→ pattern_score DESC
→ amount DESC
→ 风险项惩罚（有 ⚠ 则后移）
```

- 不用再算一套 volume/breakout/position 加权总分。  
- `priority` 是小字典，可配，不是模型。

P1：**不实现**，表上可空着 `global_rank` 字段或根本不建。

---

## 9. 数据存储

### 9.1 表：`abnormal_signal`（长表，按 Pattern 一行）

| 字段 | 说明 |
|---|---|
| `trade_date` | PK |
| `code` | PK |
| `pattern_id` | PK，如 `RANGE_BREAKOUT` |
| `scan_level` | 命中的最严档 1..k |
| `pattern_score` | 0~100，**仅模式内可比** |
| `pattern_rank` | 同日同 pattern 内名次 |
| `global_rank` | 可空，P2 |
| `reasons` | JSON string[] |
| `risk_flags` | JSON |
| `score_components` | JSON，模式内各组件分（调参用） |
| `inputs_snapshot` | JSON，关键输入阈值快照 |
| `params_version` | Config + Scan 档指纹 |
| `feature_version` | |
| `created_at` | |

**索引**：

- PK `(trade_date, code, pattern_id)`  
- `(trade_date, pattern_id, pattern_rank)` — 拉某模式 TopN  
- `(trade_date, pattern_id, scan_level)`

**行数**：每模式过筛通常个位数~几十；4 模式 × ~30 ≈ 百级/日，远小于综合方案「全过筛写库」。

### 9.2 表：`abnormal_run`

| 字段 | 说明 |
|---|---|
| trade_date / status / duration_ms / error_msg | |
| patterns_enabled | JSON 列表 |
| params_version | |
| per_pattern_stats | JSON：`{RANGE_BREAKOUT: {L1:3,L2:5,L3:4, written:12}, ...}` |
| universe_size | |

幂等：按日 delete+insert 全部 pattern 行；或按 `pattern_id` 增量重跑。

---

## 10. 代码结构

```text
quant_system/abnormal/
  __init__.py
  context.py          # 当日共享：feature df、振幅、median return…
  registry.py         # PATTERN_REGISTRY
  engine.py           # 编排：跑所有 Pattern → 落库
  scan.py             # Parameter Scan 通用执行器
  score_utils.py      # 锚点插值、BreakDistance 等工具（无业务）
  reasons.py
  patterns/
    base.py           # Protocol: match(level) / score / reasons
    range_breakout.py
    bottom_launch.py
    trend_accel.py
    ath_250.py
  rank_engine.py      # P2 可选
  service.py
  queries.py          # top_by_pattern / show(code) 跨 pattern
  backtest.py         # 按 pattern × level 分层
```

```text
Protocol Pattern
  id: str
  config: PatternConfig
  required_features() -> list[str]
  filter(df, level) -> DataFrame     # 硬条件
  score(row, ctx) -> float
  reasons(row, ctx) -> list[str]
```

新增 Pattern：新文件 + 注册，**不改 engine**。

---

## 11. 特征依赖

### 11.1 已有可直接用

`return_1d/5d`、`ma5/10/20`、`ma_bull_arrange`、`macd_*`、`volume_ratio`、`break_high_20d`、`atr_14`、`turnover_rate`；kline 的 OHLC/amount。

### 11.2 P1 建议补进 `daily_feature`

| 字段 | 谁用 |
|---|---|
| `high_60d` / `break_high_60d` | TREND_ACCEL |
| `high_250d` / `low_250d` / `break_high_250d` | ATH / BOTTOM |
| `range_pos_250d` | BOTTOM |
| `ma250` / `ma250_bias` | BOTTOM（可选） |
| `amplitude_20d` | RANGE_BREAKOUT（也可现场算 rolling，但进 feature 更干净） |
| `ma5_cross_ma10`（可选布尔） | BOTTOM；也可用当日 ma5>ma10 且昨 ma5≤ma10 现场判 |

Feature lookback ≥ **280** 交易日。

### 11.3 仅引擎现场算

阳线、一字板、BreakDistance、连续放量天数、market_median_return、Scan 合并逻辑。

---

## 12. 性能

| 步骤 | 预估 |
|---|---|
| 一次读全池 feature + 当日 kline | <1.5s |
| 共享派生（振幅/中位数） | <100ms |
| 每 Pattern 多档布尔过滤（向量化） | 每模式 <50ms |
| 评分（仅候选） | 可忽略 |
| 写库（百级行） | <200ms |
| **合计** | **≪ 5s** |

禁止：每 Pattern 各自重新拉 250 日 K 线。

---

## 13. CLI 与日报

### 13.1 CLI

| 命令 | 含义 |
|---|---|
| `qs abnormal scan [--date --patterns --force --dry-run]` | 跑引擎 |
| `qs abnormal top --pattern RANGE_BREAKOUT [--limit]` | 单模式榜 |
| `qs abnormal top --all` | 依次打印各模式 TopN |
| `qs abnormal show <code>` | 该票命中了哪些 Pattern + level + score |
| `qs abnormal stats` | 每模式 L1/L2/L3 数量漏斗 |

### 13.2 日报结构（主产出）

```text
## 今日异动（按模式）

### 横盘放量突破 TOP10
| rank | code | level | score | reasons |

### 底部启动 TOP10
...

### 趋势加速 TOP10
...

### 突破一年新高 TOP10
...
```

不再默认给「综合异动 TOP30」。P2 若有 Global Rank，可加一节「阅读推荐顺序（非强度排名）」并加脚注防误解。

---

## 14. 回测与验收

### 14.1 核心：按 Pattern × Scan Level 分层

对每个 `(pattern_id, scan_level)`：

| 指标 | 用途 |
|---|---|
| 样本数 | 是否过稀/过滥 |
| T+1 / T+5 均收益、胜率 | 模式是否有边 |
| **L1 vs L3 收益差** | Scan 是否真的在区分「典型 ↔ 宽松」 |
| 模式内 score 分桶 | 同 Pattern 内 score 是否有区分力 |

**不再把「跨模式综合分桶」当作第一指标**——那种指标服务的是已废止的综合分哲学。

### 14.2 P1 验收

1. 四 Pattern 可独立开关；禁用某一个不影响其它。  
2. 同票可同时出现在两个 Pattern 榜。  
3. 同 Pattern 内排序：`level` 优先于 `score`。  
4. dry-run 打印每模式每档命中数；某日某模式为 0 只属正常。  
5. 单测：放宽单调性（L1 集合 ⊆ L2 集合 ⊆ L3）；best_level 保留最严。  
6. 全市场 < 5s。  
7. 回测：至少一个 Pattern 的 L1 前瞻优于 L3（方向正确）。

---

## 15. 配置

```text
QS_ABNORMAL__ENABLED_PATTERNS=RANGE_BREAKOUT,BOTTOM_LAUNCH,TREND_ACCEL,ATH_250
QS_ABNORMAL__TOP_N=10
# 各 Pattern 阈值放在 patterns/*.py 的 PatternConfig 或独立 yaml
# params_version = hash(全部启用 Pattern 的 Config)
```

业务零 magic number：阈值进 Config，不进引擎硬编码。

---

## 16. 落地顺序

| 步 | 内容 |
|---|---|
| 1 | feature 补字段 + lookback |
| 2 | `Pattern` Protocol + `scan.py` + `score_utils` + 单测（单调放宽） |
| 3 | 实现 4 个 P1 Pattern |
| 4 | ORM 长表 + run + Repository |
| 5 | CLI `scan/top/show/stats` |
| 6 | report 分模式专区 |
| 7 | 按 pattern×level 回测脚本 |
| 8 | （P2）Rank Engine |

---

## 17. 关键决策速查

| 决策点 | 结论 |
|---|---|
| 系统核心 | **Pattern**，不是综合分 |
| 分数含义 | 仅 Pattern 内排序 |
| 跨模式比较 | P1 不做；P2 轻量 Rank，不重算综合分 |
| 强弱表达 | Parameter Scan 档位 L1→L3 为主，score 为辅 |
| 扩展 | 加 Pattern ≈ 加配置/类 |
| 一票多模式 | 允许多行 |
| 存储 | `(date, code, pattern_id)` 长表 |
| 日报 | 分模式 TopN |
| V1 综合分 / regime 全局权重表 | **废止**（工具箱想法可下沉到各 Pattern） |

---

## 18. 从 V1 废止与保留

| V1 内容 | 处置 |
|---|---|
| 全局六维加权 + regime 融合总分 | **废止** |
| 综合 Top30 作为主产出 | **废止** |
| 全局 Score 分桶作第一验收 | **废止**（改为 pattern×level） |
| relative_return / BreakDistance / 连续放量 / 位置混合 | **保留为 Pattern 工具箱** |
| 硬过滤思想 | **下沉到各 Pattern 的 ScanLevel.filters** |
| 可插拔扩展 | **升级为 Pattern Registry**（比 Detector 类型更贴切） |
| abnormal_run 血缘 / 幂等 | **保留** |

---

## 附录 A · 同日输出示意

```text
【横盘放量突破】
1. 600XXX  L1  score=91  振幅8%·量比3.2·破20日高·距高0.7ATR
2. 000XXX  L1  score=85  ...
3. 002XXX  L2  score=88  ← 分虽高但档位低于 L1，排后面

【底部启动】
1. 601XXX  L1  score=87  250日位25%·金叉·放量
...

【趋势加速】
（今日 L1 仅 2 只，L2 补足展示）

【突破一年新高】
...
```

同一标的若出现在「横盘突破」和「一年新高」两榜，两处都展示——读者按关心的模式看，而不是问「到底综合第几」。
