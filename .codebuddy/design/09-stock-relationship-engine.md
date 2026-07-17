# 09 · Similarity Framework（股票相似度框架）

> 状态：📝 **框架定稿 v3**（协议一次设计完整；实现可先只落 Pearson Calculator）  
> 原名：Stock Relationship Engine（表名 `stock_relationship*` 保留兼容）  
> 成对交付：[15 Cluster Framework](./15-stock-clustering.md)  
> 上位框架：[16 Market Representation](./16-market-representation.md)（Pipeline 中台、Representation、Relationship Fusion）  
> 本文职责：Relationship Engine——Calculator 协议、边存储、Fusion→Graph 实现、查询；表名可仍叫 `stock_relationship*`。  
> 定位：多源关系计算与融合；Cluster / 策略 / AI **只消费 Unified Graph（或声明的 Relationship 形态）**，不绑定单一算法。

---

## 0. 一句话与终局拓扑

**中心是 Unified Relationship（常为 Graph），不是 Pearson。**  
任意 Calculator 产出关系对象（边 / 图 / 未来矩阵）；**Relationship Fusion** 多源合并；Cluster **永远不读 Calculator 类型分支**。  
序列与向量表示来自 16 中台，Calculator **禁止**私有减指数 / 私有标准化。

```text
Raw Market Data
        ↓
16 Series Pipeline + Common Structure Extraction
        ├── Series / RepresentationBundle
        ↓
Relationship Calculators（本文：Pearson / Pattern / Feature / Exposure / …）
        ↓
Relationship Fusion（WEIGHTED / MAX / … → Unified Graph）
        ↓
Cluster / Similar Stocks / 传播 / AI / Strategy
```

**扩展铁律**：新增关系算法 = **只新增 Calculator**；新增预处理 / 抽取 = **只改 16**；新增融合策略 = Fusion 插件。  
**禁止**为新算法修改：Cluster、对外 API 骨架、Web 路由结构。

---

## 1. 设计原则（相对旧稿的翻转）

| 旧思路 | 本版 |
|--------|------|
| Similarity ≈ Pearson，其它以后挂插件 | **Graph 为中心**；Pearson 只是第一个 Calculator |
| `breakdown` / `confidence` 以后再加 | **协议一次完整**；Pearson 也必须产出标准字段 |
| `load_graph(type=PEARSON)` | `SimilarityGraphRequest` 支持多类型 + merge |
| 模块名 `relationship/` | 代码目录目标 **`similarity/`**；DB 历史名保留 |
| V1/V2 慢慢演进接口 | **接口冻结**；实现按 Calculator 逐个加 |

「实现完整」≠「一次写完所有 Calculator」。  
「框架完整」= 协议、存储、Graph、Merge、查询、与 Cluster 边界 **一次定死**。

---

## 2. 核心协议（冻结）

### 2.1 SimilarityType

稳定枚举（可增不可改语义）：

| Type | 含义 | 首期实现 |
|------|------|----------|
| `PEARSON` | 收益率线性相关 | **必做** |
| `SPEARMAN` | 秩相关 | 骨架/可后做 |
| `LEAD_LAG` | 领先滞后 | 骨架/可后做 |
| `PATTERN` | 形态/Definition 相似 | 接口就绪，实现跟 Pattern 成熟度 |
| `FEATURE` | 多维特征相似 | 接口就绪 |
| `EMBEDDING` | 向量相似 | 接口就绪 |
| `EVENT` | 事件共现 | 预留 |
| `COMPOSITE` | **融合图落库快照**（可选物化） | GraphBuilder 产出时可写 |

> DB 列名可继续叫 `relation_type`，语义一律 SimilarityType。

### 2.2 SimilarityResult（Calculator 标准输出，**全部必填语义**）

```python
@dataclass(frozen=True)
class SimilarityResult:
    score: float
    """主相似度 ∈ 各算法约定域；构图前由 Adapter 归一到 [0,1] 或保留有符号（见 §2.5）。"""

    confidence: float
    """可信度 ∈ [0,1]。样本少/窗口短/缺失多 → 低。与 score 独立。"""

    sample_size: int | None
    """序列类方法必填；无样本概念可为 None。"""

    direction: int = 0
    """对称=0；LEAD_LAG 等 = ±lag（或约定编码）。"""

    breakdown: dict[str, float]
    """标准必填。至少 1 个分量。禁止省略（Pearson 也要写）。"""

    meta: dict[str, Any] = field(default_factory=dict)
    """算法私有：窗口实际天数、pattern_id、model_version…"""
```

**字段分工**：

| 字段 | 回答的问题 |
|------|------------|
| `score` | 像不像？ |
| `confidence` | 这个「像」有多可信？ |
| `breakdown` | **为什么**像？（Explain / AI / Web） |
| `meta` | 复现与调试 |

**示例**

```json
// Pearson
{
  "score": 0.87,
  "confidence": 0.93,
  "sample_size": 60,
  "direction": 0,
  "breakdown": { "price": 0.87 },
  "meta": { "window": "W60", "method": "pearson" }
}

// Pattern（未来）
{
  "score": 0.91,
  "confidence": 0.42,
  "sample_size": 15,
  "direction": 0,
  "breakdown": {
    "platform": 0.92,
    "breakout": 0.87,
    "volume": 0.81
  },
  "meta": { "pattern_id": "RANGE_BREAKOUT", "asof": "2026-07-16" }
}

// Feature（未来）
{
  "score": 0.84,
  "confidence": 0.88,
  "sample_size": null,
  "direction": 0,
  "breakdown": { "roe": 0.88, "pe": 0.71, "growth": 0.94 },
  "meta": { "feature_set": "fund_v1" }
}
```

**Pearson 的 confidence 约定（锁定）**：由 `sample_size` 与窗口长度映射，例如  
`confidence = clip(sample_size / window_days, 0, 1)`（具体公式实现时写死单测）。  
**禁止** `breakdown=null`；Pearson 最少 `{"price": score}`（有符号相关时 price 与 score 同号同值）。

### 2.3 SimilarityEdge（图与仓储统一边）

```python
@dataclass(frozen=True)
class SimilarityEdge:
    code_a: str                   # 规范化 code_a < code_b（对称类型）
    code_b: str
    similarity_type: str
    window: str
    calc_date: date
    score: float
    confidence: float
    sample_size: int | None
    direction: int
    breakdown: dict[str, float]
    meta: dict[str, Any]
    # 可选冗余
    is_same_industry: bool | None = None
```

Cluster **只看见**融合后的图边（通常只需 `weight` + 端点）；Explain 才读 `breakdown`。

### 2.4 SimilarityCalculator（唯一扩展点）

```python
class SimilarityCalculator(Protocol):
    similarity_type: str

    def pair(self, a: str, b: str, *, ctx: SimilarityContext) -> SimilarityResult | None: ...

    def batch(
        self, codes: Sequence[str], *, ctx: SimilarityContext
    ) -> Iterable[tuple[str, str, SimilarityResult]]:
        """批算快路径；必须仍产出完整 SimilarityResult。"""
        ...
```

注册表：`CALCULATORS[type] = impl`。  
未实现的类型：**可注册 Stub 抛 `NotImplementedError`**，或根本不注册；**不得**让 Cluster 出现 `if type == PEARSON`。

### 2.5 有符号相关 vs 图权重

- 仓储可存原始 `score`（Pearson ∈ [-1,1]）。  
- **构图默认**：`weight = max(score, 0)`，并要求 `confidence >= conf_min`（默认 0.5，可配）。  
- 负相关边保留在库中供「负相关邻居」查询，**默认不进凝聚聚类图**。

---

## 3. SimilarityGraph（框架中心）

### 3.1 图对象

```python
@dataclass
class SimilarityGraph:
    nodes: set[str]
    # weight 已按 Request 归一/融合；可附带 edge_id 回指仓储
    edges: list[GraphEdge]   # (a, b, weight, confidence, sources_meta?)

@dataclass(frozen=True)
class GraphEdge:
    code_a: str
    code_b: str
    weight: float            # 融合后用于社区发现
    confidence: float        # 融合后置信度
    breakdown: dict[str, float] | None  # 可选：融合后的加权 breakdown
    sources: tuple[str, ...] # 参与融合的 SimilarityType，仅元数据
```

### 3.2 SimilarityGraphRequest（替代单 type 加载）

```python
@dataclass(frozen=True)
class SimilarityGraphRequest:
    types: list[str]
    """例: ["PEARSON"] 或 ["PEARSON","PATTERN","FEATURE"]"""

    window: str | dict[str, str]
    """统一窗口，或按 type 映射 {"PEARSON":"W60","PATTERN":"ASOF"}"""

    merge_strategy: Literal["SINGLE", "WEIGHTED", "MAX", "MIN"] = "SINGLE"
    weights: dict[str, float] | None = None
    """WEIGHTED 时必填，且和为 1（或自动归一）"""

    w_min: float = 0.45              # 融合后 weight 门槛
    conf_min: float = 0.5            # 融合后 confidence 门槛
    sign: Literal["pos", "neg", "abs"] = "pos"
    calc_date: date | None = None    # 默认最新快照
```

**Merge / Fusion 语义（WEIGHTED，锁定；上位名见 16 Relationship Fusion）**：

```text
对每对 (a,b)：
  收集各 type 的边（缺边视为不参与，或 weight=0 且不计分母——采用「仅对存在的类型重新归一权重」）
  weight     = Σ w_i' * score_i^{+}     # score^{+} 按 sign 处理
  confidence = Σ w_i' * confidence_i
  breakdown  = Σ w_i' * breakdown_i（按 key 对齐，缺 key=0）
  sources    = 实际参与的 types
```

`SINGLE`：`types` 长度必须为 1，等价旧 `load_graph(type=…)`。

**可选物化**：融合结果写入 `similarity_type=COMPOSITE` + `meta.merge_spec=…`，便于复现；非必须。

### 3.3 GraphBuilder

```python
class SimilarityGraphBuilder:
    def __init__(self, repo: SimilarityRepository): ...

    def build(self, req: SimilarityGraphRequest) -> SimilarityGraph:
        # 1) 按 types 拉边  2) merge  3) 过滤 w_min/conf_min  4) 返回 Graph
        ...
```

**Cluster 唯一入口**：`graph = builder.build(req)`。  
禁止 Cluster 持有 `SimilarityRepository` 以外的 Calculator 引用；更禁止 `if PEARSON`.

---

## 4. 存储（表名兼容，字段一次补齐）

### 4.1 边表 `stock_relationship`（逻辑名 SimilarityEdgeStore）

| 字段 | 说明 |
|------|------|
| `relation_type` | SimilarityType |
| `window` | |
| `stock_code_a` / `stock_code_b` | `a < b` |
| `relation_value` | **= score**（列名兼容） |
| `confidence` | **新增** Numeric，`[0,1]` |
| `sample_size` | |
| `direction` | |
| `breakdown_json` | **新增** JSON，**非空**（新写入强制） |
| `meta_json` | **新增** JSON，可 `{}` |
| `is_same_industry` | |
| `calc_date` / `created_at` | |

主键不变。旧行迁移：`confidence` 按 sample 回填或 1.0；`breakdown_json={"price": relation_value}`。

### 4.2 `stock_relationship_run`

增加（或 `params_json` 承载）：

- `calculator_version` / `code_hash`  
- 完整 context 摘要  

### 4.3 落库门槛（按 Calculator Profile，非框架写死）

通用三层仍可用：样本 / `|score|` 阈值 / max_neighbors。  
**另**：可配置 `min_confidence` 落库门槛（默认 0，聚类侧再用 `conf_min` 滤）。

### 4.4 只留最新快照

同 `type+window` 事务内 replace；与现网一致。

---

## 5. 代码目录（目标结构）

```text
quant_system/similarity/          # 新中心包
  types.py                        # SimilarityType 常量
  protocol.py                     # Result / Edge / Calculator / Context
  calculators/
    pearson.py                    # 首期唯一完整实现
    spearman.py                   # 可后填
    pattern.py                    # stub → 实现
    feature.py
    embedding.py
    lead_lag.py
  repository.py                   # SimilarityRepository（可适配现有 RelationRepo）
  graph.py                        # Graph / GraphEdge / Request / Builder / Merge
  service.py                      # refresh 编排：算边 →（可选）调 Cluster
  query.py                        # neighbors / pair / explain

# 过渡期：quant_system/relationship/ 变为 thin re-export，避免一次性炸裂 import
```

CLI / 任务：

```text
qs similarity refresh --types PEARSON --windows 60,250 [--cluster]
qs similarity graph-dry-run --types PEARSON,PATTERN --merge WEIGHTED --weights ...
qs similarity explain CODE_A CODE_B --types PEARSON
```

旧 `qs relationship *` 保留为别名。

---

## 6. 与 Cluster / Strategy / AI 的契约

| 消费者 | 允许依赖 | 禁止 |
|--------|----------|------|
| **Cluster (15)** | `SimilarityGraph` / `SimilarityGraphRequest` | Calculator、Type 分支、收益率矩阵 |
| **Strategy** | Graph、Cluster 成员、edge.score/confidence | 写死 Pearson |
| **AI / Web Explain** | `pair` + `breakdown` + `confidence` | 前端拼公式 |
| **个股邻居 UI** | Query by type（可多 tab） | |

**默认编排**（产品）：`similarity.refresh` = 指定 types 批算落库 → 按 Cluster Profile 的 `GraphRequest` 建图 → Louvain → 落簇。  
首期 Profile：`types=[PEARSON]`，两窗；接口已支持日后改成多类型加权而不改 Cluster。

---

## 7. Calculator 实现节奏（框架已完整，实现可分期）

| 优先级 | Calculator | 说明 |
|--------|------------|------|
| **P0** | `PearsonSimilarity` | 完整 Result + 落库 + 进默认 refresh |
| P0′ | GraphBuilder SINGLE + WEIGHTED（单类型即 WEIGHTED 退化） | **与 P0 同交付** |
| P1 | `PatternSimilarity` | Pattern 框架就绪后填肉 |
| P1 | `FeatureSimilarity` | |
| P2 | Embedding / Spearman / LeadLag | |
| 随时 | 任意新 Type | 只加文件 + 注册 |

验收框架完整性（与是否有 Pattern 无关）：

1. 单测用 **FakeCalculator** 写入边 → GraphBuilder WEIGHTED 双 Fake → Cluster mock 跑通。  
2. 新增 FakeB 零改 Graph/Cluster。  
3. Pearson 生产路径：`breakdown`/`confidence` 非空。

---

## 8. 数据口径（Pearson Calculator，非框架中心）

| 项 | 规则 |
|----|------|
| 输入 | **默认** 16 中台产出的残差/变换序列；对照用 raw recipe |
| 窗口 | W60 / W250 |
| breakdown | `{"price": score}`（语义=所用序列上的相关） |
| confidence | f(sample_size, window) |
| meta | 必须带 `PipelineRecipe` / Extractor 口径（见 16） |
| 不 fill / 不插值 | 硬规则 |

其它 Calculator 自带口径，写入 `meta`。凡依赖序列预处理的，一律声明 16 的 recipe / representation，禁止 Calculator 内私有公共结构剥离。

---

## 9. 性能与体量

- 边表仍稀疏阈值 + max_neighbors。  
- `breakdown_json` 小对象（数个 float），可接受。  
- 融合在构图时做，默认不强制物化 COMPOSITE。  
- 多 type 批算可并行；refresh 任务 heavy-mutex。

---

## 10. 落地顺序（框架优先）

1. **协议 + 表字段**（confidence / breakdown_json / meta_json）+ 迁移旧行  
2. 包结构调整：`similarity/` + relationship re-export  
3. `PearsonSimilarity` 适配完整 Result  
4. `SimilarityGraphBuilder`（SINGLE + WEIGHTED）+ FakeCalculator 单测  
5. 与 15 对接：Cluster 只收 GraphRequest  
6. `similarity.refresh --cluster` 默认一次出边+簇  
7. API：`explain` 返回 breakdown；clusters 见 15  
8. 后续只加 Calculator，不动 2–6

---

## 11. 决策速查

| # | 决策 |
|---|------|
| 1 | **中心 = SimilarityGraph**，不是 Pearson |
| 2 | Result：**score + confidence + breakdown + meta** 一次定齐 |
| 3 | breakdown **标准必填**（Pearson 也要） |
| 4 | GraphRequest 支持多 type + WEIGHTED merge |
| 5 | Cluster **零 Type 分支** |
| 6 | 代码包名目标 `similarity/`；DB 表名可保留 relationship |
| 7 | 扩展只加 Calculator；Repository/Graph/Cluster/API 骨架冻结 |
| 8 | 产品上边+簇仍默认一次编排；框架上职责分离 |
| 9 | 表示与预处理在 **16**；本文负责 Relationship + Fusion；Cluster 只吃 Unified Graph |
| 10 | GraphBuilder 的多 type merge = Relationship Fusion 的主实现（语义见 16） |

---

## 12. 与现状偏差

| 现状 | 目标 |
|------|------|
| 仅 Pearson，无 confidence/breakdown | 补字段 + Pearson 填标准 Result |
| `relationship/` 包名 | 迁到 `similarity/`（过渡 re-export） |
| 任务只建边 | refresh 默认带 cluster（15） |
| 阈值/行业等运维问题 | 独立于框架，继续用 run 表记录 |
