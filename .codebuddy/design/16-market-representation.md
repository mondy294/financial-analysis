# 16 · Market Representation Framework（市场表示框架）

> 状态：🚧 **设计稿 v3 + P0 骨架已落地**（`quant_system/representation/`；默认 `return_cfr_auto_v1`）  
> 取代关系：  
> - [v1 中性化](./16-factor-neutralization.md) → 作废  
> - [v2 Pipeline](./16-series-transformation.md) → 收为本框架的一章，不再作为顶层叙事  
> 协作：[09 Similarity / Relationship](./09-stock-relationship-engine.md)、[15 Cluster](./15-stock-clustering.md)、[10 Pattern](./10-abnormal-detector.md)、[14 Feature/Stage](./14-stage-role-feature-system.md)  
> 定位：量化系统的 **Research / 数据表示中台**——不围绕「去公共因子」或「服务 Similarity」设计，而围绕 **Market Representation（市场如何被表示）** 设计。

---

## 0. 核心思想

**Residual、Exposure、Embedding、Graph、Feature Matrix……都只是市场的一种表示（Representation）。**  
Similarity、Cluster、Pattern、ML、Alpha、策略、AI 消费的是 **Representation**，不是某一种算法或某一种数据结构。

三层主表示（长期并存）：

| 表示 | 典型形态 | 典型消费者 |
|------|----------|------------|
| **序列** Series | 原始 / 残差时间序列面板 | Pearson、波动、部分 Pattern |
| **关系** Relationship | Graph / Distance / Kernel / KNN / … | Cluster、传播、相似股 |
| **向量** Vector / Exposure | β、风格、Embedding、风险、标签… | ANN、画像、过滤、ML、AI |

接入 GNN / Transformer / Graph Embedding / 多模态 / LLM 时：  
**只新增 Representation 或 Relationship Calculator**，不推翻拓扑。

---

## 1. 终局拓扑（冻结）

```text
Raw Market Data
        │
        ▼
Series Processing Pipeline（系统公共基建，DAG）
        │
        ▼
Common Structure Extraction（公共结构抽取；方法可插拔）
        │
        ├────────► Residual Series
        ├────────► Exposure / Representation Vector
        ├────────► Embedding
        ├────────► Feature Matrix
        └────────► Other Representation
                     │
                     ▼
Relationship Engine（多 Calculator：Pearson / Pattern / Feature / Exposure / Event / Embedding / LeadLag …）
                     │
                     ▼
Relationship Fusion
                     │
                     ▼
Unified Relationship（默认可物化为 Unified Graph）
                     │
                     ├────────► Cluster
                     ├────────► Similar Stocks
                     ├────────► Pattern Search
                     ├────────► AI Explain
                     ├────────► Strategy
                     └────────► Event Propagation

（旁路：任意 Representation 也可直接被 Feature / ML / Forecast / Explain 消费，不必先过 Graph）
```

**硬约束**：

1. Pipeline **不是** Similarity 私有前置，而是全系统中台。  
2. Cluster **只**消费 Unified Relationship（通常是 Graph），不知道边如何产生。  
3. 「去公共因子」只是 Common Structure Extraction 的一种实现，不是框架标题。

---

## 2. 相对 v2 的翻转

| v2 | v3 |
|----|-----|
| Pipeline 定位为 Similarity 前置 | Pipeline = **Quant System 公共基建** |
| CFR ≈ Selection + Regression | **CommonComponentExtractor**（OLS/PCA/ICA/AE/… 均可） |
| FactorCatalog | **DataCatalog**（一切可作解释变量/结构源的数据） |
| AUTO → corr_topk + OLS | AUTO = **选配方的策略**，不是某个算法 |
| Exposure = β | **ExposurePanel / Representation** 可含 β、embedding、tags、risk… |
| Pipeline 线性 steps | 协议支持 **DAG**；P0 可只跑线性 |
| Graph 为相似度唯一输出 | Graph 是 Relationship Representation 的一种 |
| 融合在 09 GraphBuilder | 升格为显式 **Relationship Fusion Layer**（09 实现可演进对齐） |
| 叙事中心 = 去公共因子 | 叙事中心 = **Market Representation** |

---

## 3. Series Processing Pipeline（公共中台）

### 3.1 消费者（非穷尽）

同一份 Pipeline Output 可被：

- Similarity / Relationship  
- Pattern Recognition  
- Feature Engineering  
- Machine Learning  
- Alpha Research  
- Strategy / Forecast  
- AI Explain  

**禁止**再为 Pattern、Feature、ML 各写一套私有「减指数 / 标准化」黑逻辑；一律声明消费的 `recipe_id` / `representation_id`。

### 3.2 协议：线性是特例，DAG 是一等公民

```python
@dataclass(frozen=True)
class SeriesPanel:
    series_kind: str            # RETURN | VOLUME | TURNOVER | VOLATILITY | FEATURE | …
    codes: list[str]
    dates: list[date]
    values: Any
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TransformNodeSpec:
    node_id: str                # DAG 内唯一
    transform_id: str           # missing | standardize | common_structure | …
    params: dict[str, Any] = field(default_factory=dict)
    inputs: tuple[str, ...] = ()  # 上游 node_id；空 = 读 pipeline 原始输入
    # 多输入时由 transform 定义 merge 语义


@dataclass(frozen=True)
class PipelineRecipe:
    recipe_id: str
    nodes: tuple[TransformNodeSpec, ...]
    outputs: tuple[str, ...]    # 暴露给下游的 node_id 列表（可多个出口）
    # 线性管线 = 链式 inputs 的退化 DAG


class SeriesPipeline:
    def run(self, sources: Mapping[str, SeriesPanel], *, recipe: PipelineRecipe, ctx: TransformContext) -> PipelineResult:
        ...
```

P0：**只实现线性执行器**（校验 DAG 实为链）；协议层允许分叉与 Merge 节点，避免以后推翻。

示例（未来，非 P0 必做）：

```text
Raw ─┬─► Standardize ─► ResidualBranch ─► …
     ├─► FeatureBranch ─► …
     └─► EmbeddingBranch ─► …
              └─► Merge ─► …
```

---

## 4. DataCatalog（不是 FactorCatalog）

Catalog 回答：**有哪些数据可作为结构抽取 / 解释 / 特征的来源**，不限于「因子」。

```python
@dataclass(frozen=True)
class DataSeriesDef:
    data_id: str
    name: str
    family: str     # BROAD_INDEX | INDUSTRY | STYLE | THEME | MACRO | ETF | FLOW | COMMODITY | PCA | BARRA | CUSTOM | …
    source: str
    meta: dict[str, Any] = field(default_factory=dict)


class DataCatalog(Protocol):
    catalog_id: str
    version: str

    def list(self, *, families: Sequence[str] | None = None) -> list[DataSeriesDef]: ...
    def load(self, data_ids: Sequence[str], *, start: date, end: date) -> DataPanel: ...
```

**Source 插件（示例）**：`IndexSource` / `IndustrySource` / `ETFSource` / `MacroSource` / `ThemeSource` / `PcaSource` / `BarraSource` / `CustomSignalSource`。

Catalog **不**决定：谁入模、用 OLS 还是 PCA、AUTO 选哪条路。

---

## 5. Common Structure Extraction

### 5.1 目标重述

去掉可建模的**公共结构（Common Structure）**，保留特异运动；  
方法可以是回归，也可以完全不是回归。

### 5.2 统一抽象：CommonComponentExtractor

```python
@dataclass(frozen=True)
class ExtractionResult:
    residual: SeriesPanel                    # 特异序列（若该方法有残差语义）
    representation: RepresentationBundle     # 向量/暴露/成分等（可空）
    method_id: str
    method_version: str
    meta: dict[str, Any] = field(default_factory=dict)


class CommonComponentExtractor(Protocol):
    method_id: str

    def extract(
        self,
        target: SeriesPanel,
        *,
        catalog: DataCatalog,
        ctx: TransformContext,
    ) -> ExtractionResult:
        """
        内部可自行：选数据子集 / 拟合 / 分解 / 滤波。
        不要求产出 β；无回归方法 representation 里可以没有 betas。
        """
        ...
```

| method_id（示例） | 是否 naturally 有 β | 说明 |
|-------------------|---------------------|------|
| `ols_selected` | 是 | Selection + OLS（v2 路径收编为此处一种实现） |
| `ridge` / `lasso` | 是 | |
| `pca` / `sparse_pca` / `robust_pca` | 成分载荷 ≠ 传统 β | |
| `ica` | 否/弱 | |
| `autoencoder` | 否 | |
| `kalman` / `dynamic_factor` | 状态 | |
| `graph_signal_filter` | 否 | |
| `mixed` | 混合 | AUTO 策略可能选出 |

Pipeline 中的节点 `common_structure` **只依赖 Extractor 协议**，不写死 Selector+Regressor。

> v2 的 `FactorSelector` + `FactorRegressor` 降为 `ols_selected` 实现内部细节，**不再是框架中心接口**。

### 5.3 AUTO = 策略，不是算法

```python
class ExtractionAutoPolicy(Protocol):
    """观察数据特征，选择 Extractor（及参数），而不是绑定 corr_topk。"""
    def choose(self, target: SeriesPanel, *, catalog: DataCatalog, ctx: TransformContext) -> ExtractorSpec:
        ...
```

AUTO 可考虑（语义层，实现可分期）：

- 是否宽基驱动 / 行业驱动 / 主题驱动 / 风格驱动  
- 是否存在显著低秩公共结构 → 倾向 PCA  
- 候选解释变量极度共线 → 倾向 ridge/lasso/pca  
- 默认回退 `ols_selected`  

**禁止**：文档或代码写 `AUTO ≡ corr_topk + OLS`。  
P0 的 AutoPolicy 可以很笨（恒定选 `ols_selected`），但类型上必须是 Policy。

---

## 6. Representation Layer

### 6.1 RepresentationBundle

```python
@dataclass(frozen=True)
class RepresentationBundle:
    """股票在某一 asof 的向量/画像表示；字段可演进，禁止只留 betas。"""
    asof: date
    recipe_id: str
    codes: list[str]
    # 以下均为可选槽位——有则填，无则 None
    features: dict[str, dict[str, float]] | None      # code → {name: value}  含传统 β、风格、流动性…
    embeddings: dict[str, list[float]] | None         # code → vector
    tags: dict[str, tuple[str, ...]] | None           # code → 离散标签
    risk: dict[str, dict[str, float]] | None
    style: dict[str, dict[str, float]] | None
    meta: dict[str, Any] = field(default_factory=dict)
```

命名上可用 `ExposurePanel` 作为 `features` 侧重风险暴露时的别名视图，但**框架类型不要叫 FactorExposure 且仅含 betas**。

消费：画像、风格漂移、策略过滤、`EXPOSURE`/`EMBEDDING` Relationship、ML 特征、AI Explain。

### 6.2 三种主表示并存

```text
Pipeline / Extraction
        ├── Series Representation
        ├── Vector Representation（Bundle）
        └──（经 Relationship Engine 后）Relationship Representation
```

---

## 7. Relationship Engine 与 Fusion

### 7.1 Relationship Representation（Graph 不是唯一）

```python
class RelationKind(str, Enum):
    GRAPH = "GRAPH"                 # 稀疏加权无向/有向图
    DISTANCE = "DISTANCE"           # 密/疏距离
    KERNEL = "KERNEL"
    AFFINITY = "AFFINITY"
    KNN = "KNN"
    DIRECTED_GRAPH = "DIRECTED_GRAPH"
    HYPERGRAPH = "HYPERGRAPH"       # 预留


@dataclass(frozen=True)
class RelationshipObject:
    kind: RelationKind
    calc_date: date
    payload: Any                    # GraphEdges | matrix handle | knn lists …
    sources: tuple[str, ...]        # 参与的 calculator ids
    meta: dict[str, Any] = field(default_factory=dict)
```

不同聚类/检索算法消费不同 kind；**Cluster 默认声明需要 `GRAPH`（或 Fusion 输出的 Unified Graph）**。

09 现有 `SimilarityGraph` = `RelationshipObject(kind=GRAPH)` 的主实现；矩阵类可后加，协议预留。

### 7.2 Relationship Calculators

与 09 `SimilarityCalculator` 对齐并扩称（实现可仍叫 similarity）：

Pearson / Spearman / Pattern / Feature / Exposure / Event / Embedding / LeadLag / …

各自读取所需 Representation（残差序列 / Bundle / 事件表…），产出 `RelationshipObject`（或先产出边再适配为 Graph）。

### 7.3 Relationship Fusion Layer

```text
Pearson Graph
Pattern Graph
Exposure Graph
Event Graph
Embedding Graph
        │
        ▼
Relationship Fusion
        │
        ▼
Unified Relationship（常为 Unified Graph）
        │
        ▼
Cluster / 传播 / …
```

Fusion 策略（与 09 WEIGHTED/MAX/MIN 对齐并扩展）：

| strategy | 语义 |
|----------|------|
| `SINGLE` | 单源 |
| `WEIGHTED` | 多源权重融合（现网） |
| `MAX` / `MIN` | |
| `STACK` | 多视图保留，供多图算法（P2） |

**产品含义**：Pattern 成熟后必须能进 Fusion，否则「Pattern 做了 Cluster 却用不上」。  
Cluster **只**挂 Unified Graph，不挂某个 Calculator。

---

## 8. 与现有文档的分工

| 文档 | 职责（v3 后） |
|------|----------------|
| **16（本文）** | 表示中台：Pipeline DAG、DataCatalog、Extractor、Representation、Relationship 形态与 Fusion 定位 |
| **09** | Relationship Engine 细节：Calculator 协议、边存储、GraphBuilder/Fusion 实现、查询 API |
| **15** | Cluster = f(Unified Graph)；零 Calculator / 零 Pipeline |
| **10 / 14** | Pattern / Feature 声明消费哪些 Representation / recipe |

09 中已有 WEIGHTED merge：**语义上升为 Relationship Fusion**；字段/类名可渐进改，不必一次改库表。

---

## 9. P0 诚实切片（协议按终局，实现可薄）

| 能力 | P0 |
|------|----|
| Pipeline | 线性执行器 + recipe 序列化；DAG 校验「必须是链」 |
| DataCatalog | 薄宇宙（现有 index_daily + 可扩展接口） |
| Extractor | 只实现 `ols_selected`；AutoPolicy 可恒定选它 |
| RepresentationBundle | 先填 `features`（含 β）；embeddings/tags 槽位留空 |
| Relationship | 继续以 Graph + 边表为主 |
| Fusion | 沿用 09 WEIGHTED；文档称 Fusion |
| 全系统接入 | Similarity refresh 走 Pipeline；Pattern/Feature **声明接口**，实现可仍暂用原序列但打债 |

**P0 不可接受**：

- Pipeline 包落在 `similarity/` 且对外只能给 Pearson 用  
- AUTO 写死四指数或写死 corr_topk  
- Exposure 类型只有 `betas: dict` 且无扩展槽位  
- Cluster 读某个 Calculator 或某 recipe 分支  

---

## 10. 包结构（目标）

```text
quant_system/
  representation/                 # 中台根包（名可 bikeshed，见待评审）
    catalog/                      # DataCatalog + sources
    pipeline/                     # Recipe DAG + runner
    extract/                      # CommonComponentExtractor 实现
    types.py                      # SeriesPanel, RepresentationBundle, RelationshipObject
  similarity/                     # 09：calculators + repo + fusion→graph（Relationship Engine）
  cluster/                        # 15：只吃 Unified Graph
```

---

## 11. 决策速查

| # | 决策 |
|---|------|
| 1 | 顶层叙事 = **Market Representation Framework** |
| 2 | Pipeline = 全系统公共基建，不是 Similarity 私有 |
| 3 | 公共结构 = **CommonComponentExtractor**，不绑回归 |
| 4 | Catalog = **DataCatalog** |
| 5 | AUTO = **Policy**，不是某个 Selector |
| 6 | RepresentationBundle 通用，β 只是 features 的子集 |
| 7 | Relationship 多种形态；Graph 是一种 |
| 8 | **Fusion → Unified Graph → Cluster** |
| 9 | 协议支持 Pipeline **DAG**；P0 可只跑线性 |
| 10 | 扩展只加 Representation / Extractor / Calculator / Source |

---

## 12. 非目标

- P0 实现 ICA/AE/GNN  
- P0 密矩阵全市场 Distance 落库  
- 用 Representation 取代交易所官方行业  
- 一次迁完所有 Pattern/Feature 旧路径（允许打技术债，但新代码走中台）  

---

## 13. 待评审问题

1. 中台根包名：`representation/` vs `researchkit/` vs `serieskit/`？  
2. 09 类名是否渐进改名为 Relationship*，还是长期 Similarity* 别名并存？  
3. P0 AutoPolicy：恒定 `ols_selected` 是否可接受？  
4. RepresentationBundle 首期是否单独建表？  
5. Fusion 多视图 `STACK` 是否进 P1？  
6. Pattern 强制绑定 recipe 的时间点（P0′ 还是 P1）？  

---

## 14. 一句话收束

不要围绕「去公共因子」设计系统，而要围绕 **市场如何被表示、表示如何被组合与消费** 设计系统。  
公共结构抽取、相似度、聚类、AI、策略，都是 Representation 上的算子。  
