# 10 · Pattern Template Matching Framework（形态模板匹配框架）

> 状态：🚧 设计稿 v2 已部分落地（GenericMatcher + RANGE_BREAKOUT 可变窗口）
> 依赖阶段：1(架构) / 5(数据层) / 6(特征质量)
> 定位：通用 Matcher + PatternDefinition(Timeline) + 统一 FeatureCatalog + 独立 Evaluator。  
> 新增形态时，原则上只新增 Definition，不改 Matcher 主流程。

---

## 0. 一句话概述

稳定下来的核心链路只有这一条：

```text
KLine
  → FeatureExtractor
  → FeatureValue
  → Evaluator
  → FeatureSimilarity
  → StageSimilarity
  → PatternSimilarity
  → matched
```

其中：

| 角色 | 职责 |
|---|---|
| `PatternDefinition` | 描述理想模板（Timeline / Stage / Target / Window） |
| `GenericPatternMatcher` | 组织匹配流程：搜窗口 → 抽特征 → 评价 → 聚合 |
| `FeatureExtractor` | 从 K 线切片计算统一 `FeatureValue` |
| `Evaluator` | 用 `FeatureValue` 与 `TargetValue` 算相似度 |
| `Similarity` | 唯一核心语言；`matched` 只是最终阈值派生值 |

新增 Pattern 的理想路径：

```text
新增 PatternDefinition
        ↓
复用同一个 Matcher / Extractor / Evaluator
        ↓
输出分层 similarity
```

---

## 1. 相对上一版的关键修正（已采纳）

| 点 | 上一版 | 本版定稿 |
|---|---|---|
| Stage 窗口 | 固定 `length=20` | **`min_length` / `max_length`，V1 必做** |
| 跨 Stage | 特殊 `RelationTarget` | **升级为 `RelationFeature`，进 FeatureCatalog** |
| Target 方向 | 建议做 mode | **V1 必做 `TargetValue.mode`** |
| 单位 | 建议统一小数 | **强制全部用小数比例** |
| 首个 Pattern | 写死 20+2 | **`RangeBreakout`：platform 15~30，breakout 1~5** |
| 评价层 | Feature 直接出 Similarity | **拆出独立 `Evaluator`** |

上一版把可变窗口留给 Matcher「以后再补」是错的：  
若 Definition 只写死 20 天，Matcher 迟早会偷偷搜 18/19/21……，窗口策略就泄漏进实现细节。  
**允许的窗口范围必须属于 PatternDefinition；Matcher 只负责在该范围内搜最优。**

---

## 2. 核心抽象总览

```text
PatternDefinition
├─ timeline: [Stage, ...]
│    └─ window: WindowConstraint(min_length, max_length)
│    └─ targets: { feature_name: TargetValue }
├─ threshold
├─ stage_weights
└─ constraints (hard filters)

FeatureCatalog
├─ PriceFeature / VolumeFeature / VolatilityFeature / ...
└─ RelationFeature          # 跨 Stage / 跨区间关系，一等公民

GenericPatternMatcher
├─ 枚举合法 Timeline 窗口组合
├─ 对每个候选窗口：
│    FeatureExtractor → FeatureValue
│    Evaluator → FeatureSimilarity
│    聚合 → Stage / Pattern Similarity
└─ 取 overall_similarity 最高者作为最终结果
```

---

## 3. PatternDefinition：模板，不是参数表

### 3.1 结构

```text
PatternDefinition
├─ id: "RANGE_BREAKOUT"
├─ version: "tl-v2"
├─ display_name: "横盘突破"
├─ threshold: 80.0
├─ stage_weights: {platform: 0.55, breakout: 0.45}
├─ constraints: HardConstraints(...)
└─ timeline: [Stage, ...]
```

### 3.2 Stage + WindowConstraint

```text
Stage
├─ name: "platform"
├─ window: WindowConstraint(min_length=15, max_length=30)
└─ targets: dict[str, TargetValue]
```

```text
WindowConstraint
├─ min_length: int          # 含，交易日
└─ max_length: int          # 含，交易日
```

约定：

1. `min_length <= max_length`
2. `min_length == max_length` 时退化为固定窗口（仍合法）
3. Stage 按时间正序书写：`[更早, ..., 更晚]`
4. 切片相对 `trade_date` **末端对齐**，Stage 相邻不重叠
5. 总窗口上界 = `sum(stage.max_length)`；历史不足则该样本不可匹配

### 3.3 TargetValue（含 mode）

```text
TargetValue
├─ ideal: float
├─ tolerance: float          # > 0
├─ weight: float
└─ mode:
      - two_sided            # 离 ideal 越近越好（如换手率最佳 2%）
      - one_sided_high       # 达到 ideal 后，更高不重罚或轻罚（如放量、突破距离）
      - one_sided_low        # 达到 ideal 后，更低不重罚或轻罚（如振幅、回撤）
```

`mode` 属于 Target，不属于 Matcher 分支逻辑。  
Matcher / Evaluator 不得出现 `if feature_name == "amplitude"`。

### 3.4 首个 Pattern：RangeBreakout（范围窗口）

```text
RANGE_BREAKOUT
├─ Stage platform
│    window: 15~30
│    targets: amplitude↓, slope≈0, volume_shrink, volatility↓, ...
└─ Stage breakout
     window: 1~5
     targets: total_return↑, volume_expand↑, bull_ratio, ...
     + RelationFeature: breakout_distance vs platform.high_max
```

这样第一版就验证完整框架，而不是先写死 `20+2` 再立刻返工。

---

## 4. 可变窗口搜索（V1 必做）

### 4.1 语义

Pattern 定义的是：

> 「允许的平台长度范围 / 突破长度范围」

不是：

> 「唯一的平台长度」

Matcher 必须：

1. 枚举所有合法窗口组合
2. 对每个组合算 overall similarity
3. **取 similarity 最高的组合**作为最终匹配结果
4. 在 `metrics` 中回传最优窗口：`chosen_lengths = {platform: 23, breakout: 2}`

同一形态下：

- A：18 天横盘后突破
- B：23 天横盘后突破

可以命中同一个 `RANGE_BREAKOUT` Definition。

### 4.2 搜索空间

对 Timeline `[S1, S2, ..., Sk]`：

```text
候选数 = Π (max_i - min_i + 1)
```

例如 platform 15~30（16 档）× breakout 1~5（5 档）= **80** 个候选。  
3200 股 × 80 × 少量 Feature，对日频扫描可接受。

### 4.3 性能护栏（V1 就要有，但不把复杂度推回固定窗口）

1. **只算 Definition 引用到的 Feature**（懒计算）
2. 同股票同日多 Pattern 共享 OHLCV series
3. 可对单 Stage 做前缀统计缓存（high/low/sum/vol），避免每个窗口从头扫
4. 若未来 Pattern 段数变多，再加 beam / 粗筛，不回退到固定 length

### 4.4 结果确定性

同相似度时的 tie-break（写死，避免抖动）：

1. overall_similarity 更高者优先
2. 相同则优先 **更短总窗口**（更紧凑）
3. 再相同则优先更靠近各 Stage 窗口中位长度的组合

---

## 5. FeatureCatalog：统一特征全集

### 5.1 分类

```text
Feature
├── PriceFeature
├── VolumeFeature
├── VolatilityFeature
├── TrendFeature
├── CandleFeature
└── RelationFeature          # 跨 Stage / 跨区间，一等公民
```

### 5.2 Feature vs RelationFeature

**普通 Feature**：只依赖**单个 Stage 切片**。

```text
amplitude(stage_bars)
total_return(stage_bars)
body_ratio(stage_bars)
```

**RelationFeature**：依赖**多个 Stage 的原子量或切片**。

```text
breakout_distance =
  (breakout.close_last - platform.high_max) / platform.high_max

volume_vs_platform =
  breakout.avg_volume / platform.avg_volume

dist_to_ma20 =
  (close_last - ma20) / ma20          # 也可视为相对参考序列的 Relation
```

这些不是 Matcher 私货，必须进 Catalog，带：

- 明确输入声明（需要哪些 stage 的哪些原子量）
- 单位、公式、边界情况（除零 / 缺数据）

### 5.3 FeatureSpec

```text
FeatureSpec
├─ name
├─ category                 # price / volume / ... / relation
├─ unit                     # 强制 ratio（小数）
├─ inputs                   # stage-local 或 multi-stage
├─ extract(...) -> FeatureValue
├─ description
└─ version
```

### 5.4 单位铁律

全系统比例 **只允许小数**：

| 含义 | 写法 | 禁止 |
|---|---|---|
| 8% | `0.08` | `8` / `"8%"` |
| 量比 2.5 倍 | `2.5` | — |
| 实体占比 65% | `0.65` | `65` |

FeatureCatalog / Definition / Evaluator / 落库 metrics **同一口径**。  
违反即视为框架 bug。

### 5.5 FeatureValue

```text
FeatureValue
├─ name: str
├─ value: float | None      # None = 无法计算
├─ unit: "ratio"
└─ meta: dict               # 可选：参与计算的中间量
```

Extractor 只产出 `FeatureValue`，**不算分**。

---

## 6. Evaluator：评价与抽取彻底分离

### 6.1 为什么必须拆

| 步骤 | 职责 | 变化原因 |
|---|---|---|
| Extract | K 线 → 数值 | 新指标、新公式 |
| Evaluate | 数值 vs Target → 相似度 | 新核函数、新惩罚曲线 |

混在一起会导致：换 Gaussian 相似度时改到 Feature 代码；或改振幅公式时碰到打分分支。

### 6.2 接口

```text
Evaluator.evaluate(
    feature_value: FeatureValue,
    target: TargetValue,
) -> FeatureSimilarity   # 0~100 + distance + debug
```

V1 默认实现：`LinearToleranceEvaluator`

```text
distance = abs(actual - ideal) / tolerance
# 按 mode 修正 one_sided_high / one_sided_low
similarity = max(0, 1 - distance) * 100
```

预留可替换实现（Definition 可不改）：

- `GaussianEvaluator`
- `SigmoidEvaluator`
- `PiecewiseEvaluator`

PatternDefinition 只声明 Target；**不声明用哪种 Evaluator 公式细节**（可由全局默认或 Definition 级可选 `evaluator: "linear"`）。

### 6.3 聚合仍分层

```text
FeatureSimilarity   （Evaluator 输出）
      ↓ weight
StageSimilarity
      ↓ stage_weights（含 RelationFeature 贡献归属规则，见下）
PatternSimilarity
      ↓ threshold
matched
```

RelationFeature 的相似度：

- 默认计入**最晚相关 Stage**（如 breakout）
- 或在 Definition 中显式 `attach_to_stage="breakout"`

禁止把 Relation 分数偷偷加在 Matcher 外挂逻辑里。

---

## 7. GenericPatternMatcher：唯一流程编排器

### 7.1 输入输出

```text
输入：
  series: 足够长的 OHLCV（到 trade_date）
  definition: PatternDefinition
  context: 可选市场上下文

输出：
  PatternMatchResult
    pattern_id / code / trade_date
    matched
    similarity                      # overall
    stage_similarity
    feature_similarity
    chosen_windows                  # 最优窗口长度
    metrics                         # 实际 FeatureValue
    reasons
```

Matcher **不**负责：扫全市场、落库、排名、买卖决策。

### 7.2 标准流程

```text
1. Hard constraints（ST / 金额 / 上市天数等）—— 不进 similarity
2. 校验历史长度 >= sum(min_length)；否则直接失败
3. 枚举所有合法窗口组合（各 Stage length ∈ [min, max]）
4. 对每个候选：
     a. 末端对齐切片，得到各 Stage bars
     b. FeatureExtractor 计算 Stage 内 Feature + RelationFeature
     c. Evaluator 逐特征打 FeatureSimilarity
     d. 聚合 StageSimilarity / PatternSimilarity
5. 选 overall 最高候选（含 tie-break）
6. matched = overall >= threshold
7. 生成 reasons（按贡献排序，带上 chosen_windows）
```

### 7.3 Matcher 内禁止出现的东西

- `if pattern_id == "RANGE_BREAKOUT"`
- `if feature_name == "amplitude": ...`
- 私有临时指标公式
- 固定写死 20+2 之类的窗口假设

---

## 8. 分层职责一览（最终版）

```text
PatternDefinition     理想模板（含窗口范围 + Target + mode）
        ↓
GenericPatternMatcher 搜窗口 + 编排
        ↓
FeatureExtractor      KLine/切片 → FeatureValue（含 RelationFeature）
        ↓
Evaluator             FeatureValue + TargetValue → FeatureSimilarity
        ↓
Aggregator            Feature → Stage → Pattern
        ↓
PatternMatchResult
```

外围：

- `PatternRegistry`：注册 Definition
- `PatternRunner`：扫宇宙
- `PatternService`：落库 / CLI / 幂等
- `Strategy`：消费 similarity，决定交易

边界金句：

> Pattern 回答「像不像」；Strategy 回答「做不做」。  
> Extractor 回答「是多少」；Evaluator 回答「有多像」。

---

## 9. 坑点（更新后仍要警惕）

### 9.1 搜索组合爆炸

两段 16×5=80 可接受；三段若各自 20 档会到 8000。  
V1 约束：建议 Timeline **不超过 3 段**；单段跨度建议 ≤ 30。  
超限在 Definition 校验期直接拒绝或告警。

### 9.2 最优窗口过拟合短噪

可能总是搜到「最短、波动碰巧最小」的子段。  
对策：

- Stage target 本身要约束结构（不只 amplitude）
- tie-break 偏短窗口，但不要过度奖励极端短窗
- 后续可用 `prior`（靠近中位长度加轻微 bonus），**V1 不做复杂 prior，只留扩展点**

### 9.3 RelationFeature 输入声明不清

若 Relation 偷偷读「全历史」而不是声明的 Stage，口径必乱。  
强制：RelationFeature 的 `inputs` 必须显式列出依赖。

### 9.4 单位与 mode 回潮

任何「图省事写 8 表示 8%」或「在 Matcher 里特判振幅」都会破坏框架。  
Code review 门禁：Definition / Catalog / Evaluator 三处检查。

### 9.5 相关 Feature 重复计分

`amplitude` / `volatility` / `std` 同组不要堆太多。  
这是 Definition 作者问题，框架可提示，不自动黑盒降维。

---

## 10. 落地顺序（确认设计后才写代码）

### P0：抽象落地

- `WindowConstraint` / `Stage` / `TargetValue(mode)` / `PatternDefinition`
- `FeatureCatalog`（含 `RelationFeature`）
- `FeatureExtractor` / `Evaluator` / `Aggregator`
- `GenericPatternMatcher`（含窗口搜索）

### P1：第一个 Definition

`RANGE_BREAKOUT`：

- platform: 15~30
- breakout: 1~5
- 含 `breakout_distance` RelationFeature
- 跑通 CLI dry-run / 落库 / 分层解释

### P2：更多 Definition

底部启动、趋势加速等，全部只加 Definition。

### P3：增强

GaussianEvaluator、窗口 prior、三段以上 Timeline 的搜索优化。

---

## 11. 对当前代码的态度

`quant_system/patterns/` 下现有专用 `RangeBreakoutMatcher` 视为过渡实现。  
设计确认后重构目标：

1. 删除一 Pattern 一 Matcher
2. 引入 Definition + 可变窗口搜索
3. 引入 FeatureExtractor / Evaluator 分离
4. RelationFeature 进 Catalog
5. 用范围版 `RANGE_BREAKOUT` 替换现示例

当前代码已按本设计完成第一版落地：`GenericPatternMatcher` + `RANGE_BREAKOUT`（15~30 / 1~5）。

---

## 12. 已确认决策（本轮锁定）

| # | 决策 | 状态 |
|---|---|---|
| 1 | Stage 使用 `min_length` / `max_length`（WindowConstraint），V1 必做 | ✅ |
| 2 | RelationFeature 作为 FeatureCatalog 一等公民 | ✅ |
| 3 | `TargetValue.mode` 进入 V1 | ✅ |
| 4 | 比例单位强制小数 | ✅ |
| 5 | 首个 Pattern 为范围版 `RANGE_BREAKOUT`（15~30 + 1~5） | ✅ |
| 6 | 增加 Evaluator 层：Extract 与 Evaluate 分离 | ✅ |

---

## 13. 最终判断

这套抽象可以稳定下来：

```text
KLine
→ FeatureExtractor → FeatureValue
→ Evaluator → FeatureSimilarity
→ StageSimilarity → PatternSimilarity
→ matched
```

Matcher 只编排；Definition 只描述模板；Extractor 只算值；Evaluator 只打分。  
这样「新增 Pattern ≈ 新增 Definition」才真正成立，而不是口号。
