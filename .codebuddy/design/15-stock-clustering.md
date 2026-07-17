# 15 · Cluster Framework（股票聚类框架）

> 状态：📝 **设计稿 v4**（对齐 Similarity Framework v3：只消费 Graph）  
> 依赖：[09 Similarity Framework](./09-stock-relationship-engine.md)  
> 图源口径：[16 Market Representation](./16-market-representation.md) + [09 Fusion→Unified Graph](./09-stock-relationship-engine.md)  
> 关联：11 Web / 10 Pattern / 13 回测 / Strategy / AI  
> 目标：在 **Unified Graph** 上做社区发现并落库展示。Cluster **永远不知道**边来自何种 Calculator、何种 Pipeline、是否多源 Fusion。

---

## 0. 一句话

**Cluster = f(SimilarityGraph)。**  
图由 09 的 `SimilarityGraphBuilder.build(SimilarityGraphRequest)` 提供；换 Calculator、换 merge 权重，**本模块零修改**。

---

## 1. 在总拓扑中的位置

```text
16 Representations → 09 Relationship Calculators → Fusion → Unified Graph
                                                              ↓
                                                         Cluster Framework
                                                              ↓
                                                    Strategy / AI / Web

（RepresentationBundle / Embedding 与 Graph 平行；Cluster 默认只消费 Unified Graph）
```

算关系 / 算相似度的**产品目的**包含聚类；编排上仍可由 `similarity.refresh --cluster` 一次完成。  
**架构上** Cluster 不调用任何 Calculator。

---

## 2. 硬约束（冻结）

1. 唯一图入口：`SimilarityGraphBuilder.build(req: SimilarityGraphRequest)`  
2. **禁止** `if similarity_type == "PEARSON"` / import pearson / 读收益率矩阵  
3. **禁止** Cluster 直接扫边表拼业务逻辑（经 Repository 拉边只允许发生在 GraphBuilder 内，属 09）  
4. 检测器只吃 `(nodes, edges.weight)`；`confidence` 用于构图前过滤（在 Builder 或 Request 的 `conf_min`），不进 Louvain 公式也可  
5. Explain（为何同簇 / 为何相似）走 09 的 edge.breakdown，不在 Cluster 内重算相似

---

## 3. 组件

| 组件 | 职责 |
|------|------|
| `ClusterBuildRequest` | 内嵌或引用 `SimilarityGraphRequest` + 社区参数 |
| `CommunityDetector` | Graph → partition（Louvain / Leiden） |
| `ClusterBuilder` | build graph → detect → enrich → store |
| `ClusterStore` | run / cluster / member |

```python
@dataclass(frozen=True)
class ClusterBuildRequest:
    graph: SimilarityGraphRequest
    """唯一指定「用什么相似」——可单类型或 WEIGHTED 多类型。"""

    algo: str = "LOUVAIN"
    resolution: float | Literal["auto"] = "auto"
    seed: int = 42
    target_k: tuple[int, int] = (30, 50)


# ClusterBuilder.build(req):
#   g = graph_builder.build(req.graph)   # 来自 09
#   part = detector.run(g, ...)
#   store.replace(...)
```

**错误示范（禁止）**：

```python
# ❌
if req.graph.types == ["PEARSON"]:
    ...
```

---

## 4. 首期默认 Profile（仅配置，不是框架）

写在配置 / 任务参数里，**不是**写死在 Cluster 代码分支：

```yaml
# profiles/cluster_pearson_w60.yaml 概念示例
graph:
  types: [PEARSON]
  window: W60
  merge_strategy: SINGLE
  w_min: 0.45
  conf_min: 0.5
  sign: pos
algo: LOUVAIN
resolution: auto
target_k: [30, 50]
```

`similarity.refresh` 默认再跑一份 W250 Profile（同结构换 window）。  
未来 Composite：

```yaml
graph:
  types: [PEARSON, PATTERN, FEATURE]
  merge_strategy: WEIGHTED
  weights: { PEARSON: 0.4, PATTERN: 0.4, FEATURE: 0.2 }
  window: { PEARSON: W60, PATTERN: ASOF, FEATURE: LATEST }
```

ClusterBuilder **同一条代码路径**。

---

## 5. 社区发现与簇数

与前版相同：Louvain（或 Leiden）；resolution 自动扫描；目标 30～50；约束最大簇占比、singleton、模块度。  
`seed=42`。  
质量红线：`max_cluster_frac > 25%` 标红（融合图更容易糊成巨簇时，调权重/`w_min`，不改框架）。

---

## 6. 数据模型

### 6.1 `stock_cluster_run`

| 字段 | 说明 |
|------|------|
| `run_id` | PK |
| `calc_date` | |
| `graph_spec_json` | **完整** `SimilarityGraphRequest` 序列化（类型、权重、merge、窗口…） |
| `algo` / `resolution` / `seed` | |
| `universe_size` / `edge_used` / `n_clusters` | |
| `modularity` / `max_cluster_size` / `singleton_count` | |
| `params_json` / `status` / `duration_ms` / `created_at` | |

> **不再**用单独的 `similarity_type` 列作为真相源——以 `graph_spec_json` 为准（可冗余存 `primary_type` 仅便索引）。  
> 单类型 PEARSON 时 spec 仍是完整 Request，避免以后 COMPOSITE 改表。

### 6.2 `stock_cluster` / `stock_cluster_member`

同前：label、size、代表股（簇内加权度）、avg_internal_similarity（原 corr 语义升级）、centrality、rank。  
命名：`"{代表股}等{n}只"`；UI 标题由 graph_spec 生成「收益相关簇」/「融合簇」等展示名（映射表在前端或 meta，不进检测器）。

生效快照：按 `graph_spec` 哈希或显式 `profile_id` 区分多套并行簇（如 W60 vs W250 vs COMPOSITE）。

---

## 7. 任务与编排

| 任务 | 行为 |
|------|------|
| **`similarity.refresh`** | 09 批算指定 Calculators → 按 Profile 列表 `ClusterBuilder`（默认 pearson W60+W250） |
| `cluster.build` | 只建簇：输入 `graph_spec`（边须已存在） |
| `--no-cluster` | 只更新边 |

**禁止**默认「有边无簇」。

---

## 8. API / Web

```text
GET /api/clusters?profile=pearson_w60
GET /api/clusters/{id}
GET /api/stocks/{code}/cluster?profile=...
GET /api/meta/clusters

# Explain 在 09，不在 Cluster：
GET /api/similarity/explain?a=&b=&types=PEARSON
```

`/clusters`：profile / 窗口切换；文案「相似度社区，非官方行业」。  
股票页：所属簇 + 同簇同伴；旁边仍可挂「邻居」（09 query）。

---

## 9. 路线图

| 阶段 | 内容 |
|------|------|
| **P0** | GraphBuilder + Cluster + Pearson Profile×两窗 + refresh 编排 + UI |
| **P0 验收** | FakeCalculator 双类型 WEIGHTED → Cluster 单测不过业务代码 |
| **P1** | Pattern/Feature Calculator 就绪后只加配置 Profile（融合簇） |
| **P2** | 稳定性、粗/细两层；多源 Fusion 图（Pattern/Exposure 进入 Unified Graph） |

---

## 10. 验收

1. Cluster 源码对 `PEARSON` 字符串零业务分支（除测试夹具/默认 yaml）。  
2. Fake A/B 加权图可出簇。  
3. `similarity.refresh` 一次产出边+两窗簇。  
4. 切换 Profile 到未来 COMPOSITE **不改** ClusterBuilder 代码。  
5. Explain 使用 breakdown，与簇 API 分离。

---

## 11. 已锁定口径

| # | 决定 |
|---|------|
| 1 | Cluster 只依赖 Graph / GraphRequest |
| 2 | 默认产品 Profile = Pearson×W60（展示）+ W250（并建） |
| 3 | 融合在 09 GraphBuilder，不在 15 |
| 4 | run 真相 = `graph_spec_json` |
| 5 | Singleton 隐藏；目标 K 30～50 |
| 6 | Pipeline / Extractor / Representation 在 16；Cluster 不实现公共结构剥离 |
| 7 | Cluster 零依赖 Calculator / DataCatalog / Pipeline；只认 Unified Graph |
| 8 | 未来多源关系必须经 Fusion 再进 Cluster，禁止 Cluster 绑死 Pearson |

框架随 09 v3 冻结后，实现按 P0 开工即可。中性化落地见 16。
