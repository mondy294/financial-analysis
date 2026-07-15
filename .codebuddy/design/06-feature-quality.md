# 06 · 特征计算 + 数据质量 + 板块过滤

## 核心原则

1. **指标全部手写**：不依赖 TA-Lib / pandas-ta；后续要接第三方再说。
2. **不做未来才用的模块**：ML / 向量 / LLM 保留字段/接口预留即可，不写实体。
3. **数据层零过滤，使用层过滤**：kline / feature 表存全部（含创业板、科创板），过滤发生在 selector / backtest 读取时。

## 板块过滤（infra/board.py）

### 板块定义

| 板块 | 代码前缀 |
|---|---|
| MAIN 沪市主板 | 600 / 601 / 603 / 605 |
| MAIN 深市主板（含原中小板）| 000 / 001 / 002 / 003 |
| STAR 科创板 | 688 / 689 |
| GEM 创业板 | 300 / 301 |
| BSE 北交所 | 8 / 4 / 9 开头 |
| B 股 | 200 / 900 |

### 配置

```
QS_BOARD_FILTER=MAIN           # 默认
QS_BOARD_FILTER=MAIN,GEM       # 主板+创业
QS_BOARD_FILTER=MAIN,STAR      # 主板+科创
QS_BOARD_FILTER=MAIN,GEM,STAR  # 三板不含北交所
QS_BOARD_FILTER=ALL            # 不过滤
```

### 关键函数

```python
Board.classify(code) -> Board                      # 判断板块
parse_board_filter(raw) -> set[Board]              # 解析配置
is_allowed(code, filter_str=None) -> bool          # 单只判定
filter_codes(codes, filter_str=None) -> list[str]  # 批量过滤
```

## 技术指标（indicators/technical.py）

全部手写，纯 numpy/pandas，无第三方依赖。

| 指标 | 函数 | 备注 |
|---|---|---|
| 简单均线 | `ma(close, window)` | |
| 指数均线 | `ema(close, span)` | alpha = 2/(n+1) |
| MACD | `macd(close, fast=12, slow=26, signal=9)` | 返回 (dif, dea, hist)；hist=(dif-dea)*2 国内习惯 |
| MACD 金叉 | `macd_golden_cross(dif, dea)` | 当日金叉 = True |
| RSI | `rsi(close, window=14)` | Wilder 平滑（与主流软件一致） |
| KDJ | `kdj(high, low, close, n=9, m1=3, m2=3)` | 国内 EMA 递推算法 |
| True Range | `true_range(h, l, c)` | max(H-L, |H-PC|, |L-PC|) |
| ATR | `atr(h, l, c, window=14)` | EMA(TR, window) |
| 布林带 | `bollinger(close, window=20, std_mult=2.0)` | 返回 (upper, mid, lower, width) |
| 量比 | `volume_ratio(volume, window=20)` | vol / vol_ma20 |
| N 日新高 | `break_new_high(close, high, window=20)` | 用**前 N-1 日高**避免自比 |
| N 日收益 | `returns(close, window)` | 百分比 |
| 多头排列 | `bull_arrangement(ma_short, ma_mid, ma_long)` | |

**综合函数**：`compute_all(df)` 一次算全套，append 到 DataFrame。

## 特征聚合（feature_store/builder.py）

### 单只构造

```python
build_feature_row(code, trade_date, repos, lookback_days=120, feature_version)
    → dict | None
```

流程：
1. 读 K 线（前复权，lookback 120 天保 60 日均线有值）
2. `compute_all()` 算全套指标
3. 取目标日一行
4. 拼最近财报快照的基本面（**含 `financial_snapshot_date` + `financial_ann_date` 血缘**）
5. 拼 stock_basic 的 market_cap

### 批量入口

```python
build_features_for_date(codes, trade_date, repos) → (list[dict], list[str])
```

失败股票（K 线不足、当日无数据）返回在第二个列表，不阻塞。

### 关键：Decimal 转换

`_to_decimal(x)` 统一把 numpy 数值、pandas NaN、Python float 转成 `Decimal` 或 `None`，保证入库精度。

## 数据质量（data_quality/checker.py）

### 检查项

| check_type | 触发 | severity |
|---|---|---|
| MISSING_KLINE | 池成员当日无 K 线 | WARN |
| SUSPENDED | volume=0 | WARN |
| ABNORMAL_PRICE | |pct| > 22% | ERROR |
| FEATURE_NULL_RATE_HIGH | 特征关键列空值率 > 5% | WARN |
| SYNC_STALE | data_sync_state 落后 > 3 天 | INFO |

### 前置黑名单接口

```python
get_blacklist_for_selector(trade_date, repos, filter_level=None) → set[str]
```

三档：
- `OFF` → 空集
- `ERROR` → 只剔除 ERROR 级 STOCK（**默认**）
- `WARN_AND_ABOVE` → ERROR + WARN 都剔

**硬约束**：selector 拿到的是**已过滤后的 features**，策略层永远不判 quality。

## Repository 增补

```python
class FeatureRepository(Protocol):
    def upsert_features(records) -> int: ...
    def read_features_on(trade_date, codes=None) -> list[DailyFeature]: ...
    def count_features_on(trade_date) -> int: ...
```

Repositories bundle 加上 `feature: FeatureRepository`。

## CLI 新增

```
qs feature [--date --codes --pool]   算特征
qs quality [--date]                  数据质量巡检
```

## 冒烟验证结果

- ✅ 手动 mock 20 只股票 × 369 交易日 kline
- ✅ `qs feature --date 2026-07-14` → 20 只成功，278 只因无 K 线失败（预期）
- ✅ 指标 SQL 查看：MACD/RSI/量比/突破/金叉/多头排列全部正常
- ✅ `qs quality --date 2026-07-14` → 278 条 MISSING_KLINE WARN
- ✅ 板块过滤：`filter_codes(['300347','600000','688008'], 'MAIN')` → 只留 600000

## 明确未来才做

| 未来能力 | 当前状态 |
|---|---|
| feature_store/reader.py 统一读接口封装 | 暂不做，直接 SQL 或 repository 够用 |
| feature_store/vector.py + FAISS | 只在 daily_feature 表留 vector_version/embedding_id 字段 |
| market/market_features.py 复杂市场特征 | 暂不做，先用 index_daily 的 MA20 位置判断牛熊 |
| indicators/factors.py 复合因子 | 暂时合并在 technical.py 里 |
