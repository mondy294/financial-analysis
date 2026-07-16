# 09 · Stock Relationship Layer（股票关系层）设计方案

> 状态：📐 设计稿（未落地，仅架构 + 数据库设计）
> 依赖阶段：1(架构) / 2-3(数据库) / 5(数据层) / 6(特征质量)
> 定位：在 `daily_kline / daily_feature / stock_basic / market_feature_daily` 之上，构建**可复用的股票关系层**，长表存储、按 `relation_type + window` 扩展，为联动分析 / 相似股票推荐 / 龙头跟随 / 聚类 / AI 特征 / 回测提供**统一关系数据来源**。

---

## 0. 一句话概述

用已有日线数据，离线批量计算「股票之间的关系」，以**长表**（一行一个 `type × window × 股票对`）落库，通过**样本门槛 + 强度门槛 + 每只硬上限**三层控制行数，只留最新快照。P1 只实现基于收益率的 Pearson，但表结构和代码分层为 Spearman / Cosine / Lead-Lag / Mutual-Info 预留，新增算法不改表结构。

> **本版相对旧稿的核心变化**：
> 1. 宽表多窗口列 → **长表 `relation_type + window`**（扩展性）。
> 2. 只存 Top-N → **阈值 + 每只硬上限 + 强制 `--dry-run`**（防行数爆炸，避免近似查询）。
> 3. 明确**对称规范化存储**（`code_a < code_b`）+ 双索引。
> 4. 保留 `run` 血缘表（幂等 / 复现 / 监控）。
> 5. 计算口径统一到**收益率**，共同交易日交集，必存 `sample_size`。

---

## 1. 设计目标与边界

### 1.1 能力全景（分阶段）

| 能力 | 说明 | 阶段 |
|---|---|---|
| 历史/滚动相关度 | 收益率 Pearson，共同交易区间对齐 | **P1 必做** |
| 联动增强/减弱 | 短窗 vs 长窗对比（W60 vs W250） | **P1 必做** |
| 负相关 | 由 `relation_value <= 阈值` 派生 | **P1 必做（派生）** |
| 行业/概念关系 | 复用 `stock_basic.industry_code`（概念板块 P2 接） | **P1 复用 + P2 扩展** |
| 稳健相关 | Spearman（抗极值/涨跌停） | P2 建议 |
| 领先-滞后 Lead-Lag | 互相关 + 最优 lag（`direction` 字段承载） | P2 建议 |
| 相似度 Cosine / 相似 K 线 DTW | 形态/多因子相似 | 未来 |
| Embedding / 关系图谱 | 向量相似 / 边表 + 图算法 | 未来（AI 阶段） |

### 1.2 第一版范围（P1）

只做**最有价值、成本可控、可维护**的部分：

- 指标：**Pearson**（`relation_type=PEARSON`）
- 计算对象：**日收益率**（`close/pre_close - 1`，共同交易日交集对齐）
- 窗口：**W60 + W250 双窗口**（P1 已定，双窗口即可支撑「联动增强/减弱」；同一份收益率矩阵多算一次，成本几乎不增）
- 落库：满足**样本门槛 + 强度门槛 + 每只硬上限**的所有对（非 Top-N 裁剪）
- 行业维度：复用 `stock_basic.industry_code`，不建新表
- 只留**最新快照**，不存历史

### 1.3 不做（明确排除）

- 不新增行情/收益率表（收益率从 `daily_kline` 复权价现算 + parquet 缓存）
- 不存全量 `C(3192,2)≈5.09M` 对（阈值 + 硬上限过滤）
- 不做 ML / 向量 / 图数据库（仅预留 `relation_type` / `window` / `direction` 字段与分层）
- 不做真·增量流式协方差（滚动窗口本质仍是当窗重算）

---

## 2. 数据来源（全部复用，零重复存储）

| 用途 | 来源表 | 字段 | 说明 |
|---|---|---|---|
| 收益率序列 | `daily_kline` | `close` + `adj_factor` | `read_kline(adj="hfq")` 后复权价 → `return = close/pre_close - 1`（或 log return，锁死其一） |
| 停牌判定 | `daily_kline` | `volume` | `volume==0` → 当日收益率置 NaN，成对丢弃 |
| 上市/退市 | `stock_basic` | `list_date` / `delist_date` | 决定进入/退出计算宇宙 |
| ST 标记 | `stock_basic` | `is_st` | 可选过滤（配置） |
| 行业分组 | `stock_basic` | `industry_code` / `industry_name` | `is_same_industry` 冗余字段来源 |
| 计算宇宙 | `stock_pool_member` | 时间序列成分 | 结合板块过滤确定 code 列表 |
| 市场基准（P2） | `market_feature_daily` / `index_daily` | — | Lead-Lag / 剔市场 β 时用 |

> **收益率不落库**：复用 `daily_kline`，计算时现算宽表（parquet 磁盘缓存），不新增 `stock_return_daily` 表。

---

## 3. 上市时间 / 停牌 / 退市处理（硬要求）

统一在**收益率宽表构建阶段**处理，下游计算零感知。**不补 0、不 fill、不前向填充、不插值。**

| 场景 | 处理规则 |
|---|---|
| 上市时间不同 | 宽表按 `trade_date` 外连接，个股上市前天然 NaN |
| 两只股票配对 | **只用共同交易日交集**（pandas `corr` pairwise-complete = inner join on 非 NaN） |
| 停牌 | 当日 `volume==0` → 收益率设 NaN，成对时自动剔除 |
| 退市 | `delist_date <= as_of` 不进入宇宙 |
| 样本不足 | 共同有效样本 `< min_sample`（默认 120，可配 250）→ **该对不保存** |
| 新股 | 窗口内有效样本不足 → 不保存 |

**对齐算法**（伪逻辑，仅描述）：

```
window_days = trailing N trading_days ending at calc_date   # 用 trading_calendar
R = wide DataFrame(index=window_days, columns=universe)     # 后复权收益率
R[volume==0] = NaN                                          # 停牌剔除
corr   = R.corr(method="pearson", min_periods=min_sample)   # pairwise inner-join 语义
sample = R.notna().T @ R.notna()                            # 每对共同样本数矩阵
```

---

## 4. 数据库设计（2 张表，`ALL_MODELS` 23 → 25）

沿用 v2 约定：DB 中立（不用 SQLite 独有语法）、大表 `sqlite_with_rowid=False`、`BigInteger().with_variant(Integer(),"sqlite")` 自增主键。

### 4.1 表 1：`stock_relationship`（关系长表）

一行 = 一个 `relation_type × window × 股票对` 的关系。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BigInt/Int autoincrement, PK | 代理主键 |
| `relation_type` | String(16) | `PEARSON`(P1)；预留 `SPEARMAN`/`COSINE`/`LEAD_LAG`/`MUTUAL_INFO` |
| `window` | String(8) | `W250`(P1)、`W60`(P1.5)；预留 `W20/W120/FULL` |
| `stock_code_a` | String(16) | 规范化后**较小**的 code |
| `stock_code_b` | String(16) | 规范化后**较大**的 code |
| `relation_value` | Numeric(7,4) | 关系值（Pearson ∈ [-1,1]） |
| `sample_size` | Integer | 该对该窗口的共同有效样本数 |
| `direction` | SmallInteger, default 0 | 对称方法=0；`LEAD_LAG` 用 ±lag 表达 a→b 领先/滞后 |
| `is_same_industry` | Boolean | 同 `industry_code` 冗余标记（查询加速） |
| `calc_date` | Date | 快照日（计算基准日） |
| `created_at` | DateTime | 写入时间 |

**约束/索引**：

```
uq_rel        UNIQUE (relation_type, window, stock_code_a, stock_code_b, calc_date)
ix_rel_a      (relation_type, window, stock_code_a, relation_value)   # 查 X 邻居（a 侧）
ix_rel_b      (relation_type, window, stock_code_b, relation_value)   # 查 X 邻居（b 侧）
ix_rel_value  (relation_type, window, relation_value)                 # 全局强/负相关扫描
ix_rel_sample (relation_type, window, sample_size)                    # sample_size 过滤
```

> **对称规范化存储（`code_a < code_b`）**：Pearson 对称，`C(n,2)` 已是无序对，只存一行省一半空间。代价是「查 X 的所有邻居」要 union `code_a=X` 与 `code_b=X` 两侧，由 Repository 封装，上层无感。有向类型（Lead-Lag）用 `direction`/lag 承载方向，不破坏此规范。

### 4.2 表 2：`stock_relationship_run`（批次 / 血缘表）

对齐 `backtest_task`，保证幂等、可复现、可监控。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BigInt/Int autoincrement, PK | 批次 ID |
| `calc_date` | Date | 快照日 |
| `relation_type` | String(16) | 方法 |
| `windows` | JSON | 本次计算窗口，如 `["W250","W60"]` |
| `pool_code` | String(32) | 计算宇宙来源池 |
| `board_filter` | String(32) | 板块过滤（如 `MAIN`） |
| `min_sample` | Integer | 最小共同样本阈值（默认 120） |
| `value_threshold` | Numeric(4,3) | 落库阈值 `|value|`（默认 **0.7**，dry-run 后可调） |
| `max_neighbors` | Integer | 每只硬上限（safety cap，默认 200） |
| `universe_size` | Integer | 参与股票数 |
| `pair_evaluated` | Integer | 评估对数 |
| `pair_written` | Integer | 实际写入行数 |
| `code_hash` | String(40) | 计算模块 SHA256（复现，复用 `infra/code_hash`） |
| `status` | String(16) | `RUNNING/SUCCESS/FAILED` |
| `duration_ms` | Integer | 耗时 |
| `error_msg` | Text, null | 失败信息 |
| `created_at` | DateTime | — |

**索引**：`ix_rel_run (calc_date, relation_type)`、`ix_rel_run_status (status)`。

> `ALL_MODELS` 从 23 → **25**，`assert len(ALL_MODELS)==25`，`migrations.check_schema_integrity` 自动纳入。

### 4.3 落库策略（解决行数爆炸）

A 股日收益率受市场共振影响普遍高度正相关，单一 `|value|>=0.6` 阈值在普涨期可能命中百万级行。**三层控制，缺一不可**：

1. **样本门槛**：`sample_size >= min_sample`（默认 120），不足丢弃。
2. **强度门槛**：`|relation_value| >= value_threshold`（默认 **0.7**，正负都留）。
3. **每只硬上限**：每只股票正负各最多 `max_neighbors`（默认 200）行，防止某只命中上千邻居。兜底，正常不触发。

> **上线前强制 `--dry-run`**：只统计不落库，打印 `relation_value` 直方图 + 各阈值下预估行数 + 峰值内存，据此微调 `value_threshold`（默认从 0.7 起）。绝不能盲存。

### 4.4 数据量预估（默认主板 ~3192 只，单窗口）

| 项 | 计算 | 量级 |
|---|---|---|
| 全量无序对 | C(3192,2) | 5.09M（评估，不全落库） |
| `|corr|>=0.6` 命中（估） | 视行情 10%~30% | ~50 万~150 万行 |
| 每行体积（长表） | ~50~60 B | — |
| 单窗口快照体积（估） | 100 万 × 55B | **~55 MB** |
| 两窗口（W250+W60） | ×2 | ~110 MB |
| 只留最新快照 | replace 覆盖 | 常驻上述量级 |

> dry-run 的意义：把「估」变成「实测」再定阈值和上限。

### 4.5 更新策略

| 模式 | 触发 | 行为 |
|---|---|---|
| **首次全量** | 手动 | 全宇宙 × 指定窗口全量计算 |
| **每日增量** | 每日收盘后 / 调度 | 新增一个交易日后，重算最新窗口（滚动窗口本质仍是当窗重算） |
| **保存** | 每次 | 只留最新快照：同 `relation_type+window` **事务内先删旧再写新**（replace，非 upsert 混合），保证快照干净 |

**幂等**：`stock_relationship_run` 记 `calc_date+relation_type`，同日重跑若 `SUCCESS` 则 skip（除非 `--force`）。

> 只存最新快照 → 不占历史空间，但放弃关系强度时间序列。P2 若要趋势，另加周级历史粗表。

---

## 5. 关联指标方案对比与推荐

| 指标 | 优点 | 缺点 | 成本 | 结论 |
|---|---|---|---|---|
| **Pearson** | 线性联动直观、可矩阵化、快 | 对极值/涨跌停敏感、只测线性 | 低 | **P1 必做** |
| **多窗口对比** | 捕捉关系时变（增强/减弱） | 需 ≥2 窗口 | 低（同一收益率矩阵多算一次） | **P1 必做（W60+W250）** |
| **Spearman** | 抗极值/涨跌停、单调关系 | 丢失幅度、略慢 | 中 | P2（Pearson 稳健对照） |
| **Cosine** | 多因子/向量相似 | 需先定义向量 | 中 | 未来 |
| **Lead-Lag** | 领先-滞后、联动预警 | lag 搜索放大计算 | 中高 | P2（`direction` 已预留） |
| **Cointegration** | 配对交易/长期均衡 | 需平稳检验、易伪协整 | 高 | P2 选做（限同行业候选对） |
| **DTW / Embedding** | 形态/语义相似 | 计算重 / 需模型+向量库 | 很高 | 未来 |

### 阶段结论

- **P1（必做）**：Pearson + **W60+W250 双窗口** + 收益率 + 共同交易日 + 三层落库门槛（阈值默认 0.7）+ run 表 + Repository/Service/CLI + `--dry-run` 验证 + 联动增强（W60 vs W250）。
- **P2**：Spearman 稳健对照、Lead-Lag、周级历史快照、同行业候选对协整、概念板块 Provider、`relation_context` 接入 `ai/analyzer`。
- **未来**：Cosine / DTW / Embedding + 向量库、关系图谱（边表 + 中心度/社区）。

---

## 6. 性能设计（默认主板 ~3192 只）

### 6.1 复杂度

- 收益率宽表：`3192 列 × 250 行` float64 ≈ **6.4 MB**。
- 相关矩阵：`3192² × 8B` ≈ **81 MB/窗口**（内存可承受）。
- 无缺失走 BLAS `RᵀR` 秒级；**有缺失（min_periods 强制 pairwise）** pandas 慢路径，可能数十秒~数分钟/窗口。
- 全量单次预计：**分钟级**（每日/周级调度可接受）。

### 6.2 优化手段（P1 不过度优化）

| 手段 | 说明 |
|---|---|
| 缓存收益率宽表 | 按 `calc_date` 存 parquet 到 `infra/cache`，多窗口共用一次构建 |
| 减少 NaN 慢路径 | 缺失少的子集走 BLAS 快路径；长尾新股单独 pairwise |
| 分块提取 | 算完矩阵按行块（base 分批）过滤门槛 + 组装 records，控峰值内存 |
| 分批写入 | 复用 `_upsert_batch` 的 chunk 切分（SQLite 变量上限） |

> 后续若性能成瓶颈再上多进程 / DuckDB / Polars / Numba。**P1 优先代码清晰可维护，不预先复杂化。**

### 6.3 关键判断

| 问题 | 结论 |
|---|---|
| 需要缓存吗？ | **需要**：缓存收益率宽表（parquet），不缓存相关矩阵 |
| 需要分批吗？ | 主板 3192 不必；扩全 A 或多窗口时按 base 行块分批 |
| SQLite 够吗？ | **够**：最新快照 ~55~110 MB，分块写无压力 |
| 需要中间结果表吗？ | **不建**收益率表（复用 kline）；`stock_relationship` 本身即物化中间结果 |

---

## 7. Repository / Service / CLI 接口设计

### 7.1 Provider —— **不新增**

关系层是**纯内部计算**（输入全部来自 DB），不接外部数据源。唯一例外：P2 接「概念板块成分」需 `ConceptProvider`（akshare `stock_board_concept_*`），届时再加。

### 7.2 代码结构 —— 新增 `quant_system/relationship/`

与 `strategy/`、`feature_store/` 平级。L4 应用层，依赖 L1 repository + L0 infra，**不被数据层反向依赖**。

```
quant_system/relationship/
├── returns_matrix.py   # 收益率宽表构建 + 停牌/上市对齐 + parquet 缓存
├── calculator.py       # 纯函数：BaseCalculator + PearsonCalculator（多窗口 + 门槛过滤，无 DB/IO）
├── repository.py       # RelationRepository（DB 读写唯一入口，遵守 R4）
└── service.py          # 编排：宇宙解析 → 算 → 组装 records → repo 写 + run 记录
```

**扩展点**：新增算法 = 新增一个 `Calculator` 子类（实现 `calc(returns_matrix) -> records`），注册到 service 方法映射，DB / Repository / CLI **全不动**。

### 7.3 Repository 接口

挂入 `Repositories` bundle 与 `build_repositories()`，遵守 R4。

```python
@runtime_checkable
class RelationRepository(Protocol):
    # 写
    def replace_snapshot(self, relation_type: str, window: str, calc_date: date) -> int: ...  # 事务内清旧
    def bulk_insert(self, records: Iterable[dict]) -> int: ...            # 复用 _upsert_batch 分块
    def start_run(self, record: dict) -> int: ...
    def finish_run(self, run_id: int, status: str,
                   stats: Optional[dict] = None, error: Optional[str] = None) -> None: ...

    # 读（内部 union 两侧，上层无感对称性）
    def neighbors(self, code: str, *, relation_type: str = "PEARSON", window: str = "W250",
                  sign: Optional[int] = None, min_sample: int = 120, limit: int = 20) -> list[...]: ...   # 场景 A
    def get_pair(self, code_x: str, code_y: str, *, relation_type: str = "PEARSON",
                 window: str = "W250") -> Optional[...]: ...                                              # 场景 B
    def list_strong(self, *, relation_type: str = "PEARSON", window: str = "W250", sign: int = 1,
                    min_abs: float = 0.8, min_sample: int = 120, limit: int = 50) -> list[...]: ...       # 场景 D
    def relation_context(self, code: str, trade_date: date) -> dict: ...                                  # 场景 F（AI）
```

- `neighbors`：对 `code_a=X` 与 `code_b=X` 各查一次合并，方向统一成「以 X 为中心」，走 `ix_rel_a` / `ix_rel_b`。
- `list_strengthening`（联动增强）留到 ≥2 窗口后加：join 同一对的 W60 vs W250 求差。
- `relation_context(code, date)`：取该股强邻居 + 同行业股票**当日** `pct_change`（join `daily_kline`），供 AI explain「今天为什么涨」。

### 7.4 CLI —— 新增 `qs relationship` 子命令组

风格对齐 `qs update`（Typer sub-app、`_boot()`、`job_run_log` 包裹）。

```
qs relationship build   [--date --type pearson --windows 60,250 --pool --board MAIN
                         --min-sample 120 --threshold 0.7 --max-neighbors 200
                         --dry-run --force --replace]
qs relationship top     <code> [--type pearson --window 250 --sign +/- --limit 20 --date]   # 场景 A
qs relationship pair    <code_x> <code_y> [--type --window --date]                          # 场景 B
qs relationship strong  [--type --window --sign --min-abs 0.8 --limit 50 --date]            # 场景 D
qs relationship stats   [--date]     # 快照概览：行数 / value 分布 / 平均样本数
```

- `build` 用 `job_run_log` + `stock_relationship_run` 双记录；宇宙 = `list_pool_members(pool) ∩ board.filter_codes()`，退市剔除。
- `--dry-run` 只算分布不落库（见 §4.3），**首次上线必跑**。
- 未来 `qs pipeline` 可选挂一步 `relationship build`，或独立调度，不阻塞日频链路。

---

## 8. 最终目标 → 实现映射

| 目标查询 | 实现方式 | 依赖字段/索引 |
|---|---|---|
| A. 某股最相关 Top20 | `neighbors(code, sign=+1, limit=20)` | `ix_rel_a` / `ix_rel_b` |
| B. 两股关系值 + 样本 | `get_pair(x, y)` | `uq_rel` |
| C. 联动明显增强（P1.5） | join W60 vs W250 求差 | `ix_rel_a`（两窗口） |
| D. 出现负相关 / 强关系榜 | `list_strong(sign=-1, min_abs)` | `ix_rel_value` |
| E. 日报「联动分析」 | `report/` 调 `relationship` 查询，出「Top 联动 / 增强 / 负相关」小节 | 核心表读 |
| F. Agent explain「今天为何涨」 | `relation_context(code, date)`：强邻居 + 同行业当日涨跌归因 | 核心表 join `daily_kline` |

### Agent / AI 衔接

- `ai/analyzer.py` 的 `StockAIInput` 增补 `relation_context`（强邻居当日表现、同行业联动强度），让 LLM 解释有「联动证据」。
- 图谱阶段：可在核心表上抽边（`code_a→code_b, weight=relation_value`）跑中心度/社区，无需改表结构。

---

## 9. 验收（避免「只是多了一张高级的表」）

`qs relationship stats` 之外，上线前跑一个小型验证，至少证明：

- Top 邻居对未来 1~5 日的**同涨同跌命中率** > 随机基线；
- 同行业对关系值显著高于跨行业基线（lift）；
- （有 W60 时）「增强榜」前 20 对短窗确实 > 长窗且有解释力。

---

## 10. 落地顺序建议（供下阶段拆步）

1. 建表（`stock_relationship` + `stock_relationship_run`）+ `RelationRepository` + DI 接入 + `assert 25`。
2. `returns_matrix.py`（对齐/停牌/缓存）+ `calculator.py`（`BaseCalculator` + `PearsonCalculator`，多窗口 + 门槛过滤）纯函数 + 单测（含上市时间不同、停牌、样本不足）。
3. `service.py` 编排 + `qs relationship build`（`job_run_log` + run 表 + 幂等 + `--dry-run`）。
4. 查询封装 + `qs relationship top/pair/strong/stats` 冒烟。
5. §9 验证报告（Top 邻居 lift / 同行业 lift / 增强榜可解释性）。
6. 日报「联动分析」小节 + `relation_context` 接入 `ai/analyzer`。
7. （P2）Spearman / Lead-Lag / 周级历史 / 概念 Provider。

---

## 11. 关键决策速查

| # | 决策 | 原因 |
|---|---|---|
| 1 | 长表 `relation_type + window` | 新增算法/窗口不改表结构，可复用关系层 |
| 2 | 阈值 + 每只硬上限 + 强制 dry-run | 防 A 股共振导致行数爆炸，避免近似查询 |
| 3 | 对称规范化 `code_a < code_b` + 双索引 | 省一半空间、查询无歧义；有向类型走 `direction` |
| 4 | 基于收益率、共同交易日交集 | 正确处理不同上市时间/停牌/新股，不 fill/插值 |
| 5 | 必存 `sample_size` | 区分「0.9@30d」与「0.9@250d」可信度 |
| 6 | 只留最新快照 + 事务内 replace | 快照干净、不占历史空间；趋势留 P2 |
| 7 | 保留 run 血缘表 | 幂等 / 复现 / 监控，对齐 `backtest_task` 约定 |
| 8 | P1 = Pearson + W60+W250 双窗口，阈值默认 0.7 | 双窗口即支撑「联动增强」，0.7 聚焦强关系控行数 |
| 9 | Calculator/Repository/Service 分层 | 新增算法只加 Calculator，其余不动 |
| 10 | 独立 `relationship/` 模块（L4） | 不污染数据层，依赖方向自下而上 |
