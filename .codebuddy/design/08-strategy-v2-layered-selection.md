# 08 · 策略 v2：分层门控 + 组合共振

**状态**：🚧 已定稿（v1.2） · 阶段 A 待落地

**版本**：v1.2（2026-07-15）

**目标**：把当前 3 条策略"简单求和加分"升级为"多策略共振 + 硬否决 + regime 感知"的分层选股框架，让 `daily_feature` 里已经算好的 30+ 指标真正被用起来。

**v1.2 修订摘要**（在 v1.1 基础上）：

1. 🟡 维度自适应归一升级：**至少 2 维度有数据**（<2 硬淘汰）；**基本面维度 NULL 时 final_score 上限 75**（防次新股冲顶）
2. 🟡 一字板判定改用严格量化：`O==H==L==C` **且** `\|pct_change\| ≥ 涨跌停幅 × 0.98`（含浮点保护）；涨跌停幅按板块查
3. 🟡 `resonance_categories` 约定固定顺序 `[trend, reversal, volume_price, fundamental]`
4. 🟡 阶段 A 的 AI Prompt **不塞 regime 字段**（阶段 C 才加），避免 LLM 幻觉编造 regime
5. 🟡 假突破 soft penalty 从阶段 A 挪到 **B1**（顺带 `feature_store` 加 `fake_break_5d` 字段）
6. 🟢 `ENABLED_CATEGORIES` 语义澄清：关闭类别后共振门槛不自动下调，日志需给出"推空"告警
7. ⏱️ 阶段 A 工作量从 1h 重估为 1.5-2h

**v1.1 修订摘要**：

1. 🔴 修正 L2 硬过滤阈值：ATR 移到 soft penalty；涨跌停不淘汰改为"一字板"过滤；`return_5d` 按板块分档
2. 🔴 明确 regime 判断**只依赖 `index_daily.HS300`**，不依赖 `market_daily` 情绪（历史不可回填）
3. 🟡 阶段 B 拆分 B1/B2，每次只上 2 条新策略并观察 1-2 周
4. 🟡 `REVERSAL_MACD_BOTTOM` 改名 `REVERSAL_MACD_TURN`（避免"背离"误导）
5. 🟡 `VOL_SHRINK_TREND` 明确"突破无效"的量化定义
6. 🟡 加权公式加入"维度缺失自适应归一"，避免熊市小盘无财报直接被判死
7. 🟢 权重表改用 `dict` 常量，不再拆成 12 个环境变量
8. 🟢 被硬过滤股票不落 `data_quality_check`，只放内存 + 日报

---

## 一、当前问题诊断

### 1.1 覆盖面窄，指标浪费

`daily_feature` 存了 30+ 指标，实际被 3 条策略作为**触发条件**用到的只有 8 个：

- ✅ 用到：`break_high_20d, volume_ratio, ma_position, ma_bull_arrange, macd_golden_cross, return_20d, pe_ttm/roe_latest/*_yoy`
- ❌ 未用：`RSI, KDJ, BOLL(上/中/下/带宽), ATR, macd_hist, high_20d(数值本身), amount_ma5`

### 1.2 只做"顺势追涨"，缺场景覆盖

三条策略都是**"股票已经开始涨了才推荐"**的顺势策略：突破新高、均线多头 + 金叉、财报好。

缺失场景：超跌反弹、均线回踩、MACD 转折、价量背离预警。

### 1.3 组合规则过于宽松

当前 `stock_selector.py` 的组合逻辑：
```
只要命中 ≥ 1 条 → 进 Top 排序
final_score = tech + capital + fundamental + multi_hit_bonus (每额外命中 +5，上限 15)
```

问题：
- **假信号无法过滤**：BREAKOUT 命中但 RSI=95（严重超买）→ 系统照样推荐
- **市场环境不区分**：牛市和熊市推同一批"突破"股，熊市里几乎都是假突破
- **单策略过度自信**：只命中 1 条就能进 Top
- **同类内多命中的加分不合理**：现在同类命中 3 条 = +10，但同类信号本质是同一信息重复算

### 1.4 只加分，不扣分

系统没有"风险扣分"或"硬否决"。一只票 3 天涨 20% + break_high + 量能 3 倍 → 评 90 分（可能是主力出货诱多）。

---

## 二、总体方案：五层门控

```
输入：daily_feature（当日全体股票）
    │
    ▼
┌─── L1 · 市场态势判断（仅依赖 index_daily.HS300）─────────────────────┐
│    → regime ∈ { BULL_STRONG / BULL_WEAK / BEAR_WEAK / BEAR_STRONG } │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─── L2 · 股票风险硬否决（每股，板块自适应阈值）────────────────────────┐
│    RSI 极端超买 / 5日暴涨（按板块）/ 量价背离 / 一字板 / 关键指标缺失 │
│    → 直接淘汰                                                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  (通过的股票)
                               ▼
┌─── L3 · 策略池并行执行（4 类共 11 条）──────────────────────────────┐
│    Trend × 3   +   Reversal × 3   +   VolumePrice × 3   +           │
│    Fundamental × 2                                                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─── L4 · 共振门控（按 regime 决定最小共振度）────────────────────────┐
│    BULL_STRONG: ≥1 类；BULL_WEAK: ≥2 类；                            │
│    BEAR_WEAK: ≥2 类且含 Fundamental；BEAR_STRONG: ≥3 类含 Fundamental│
│    不满足 → 淘汰                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─── L5 · 加权综合评分（regime 感知 + 维度自适应归一）────────────────┐
│    final = adjusted_weighted(T, C, F)                                │
│            + resonance_bonus - soft_penalty                          │
│    产出：final_score / positive_reasons / risk_flags /              │
│         regime / resonance_categories                                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
                  排序 → Top N → strategy_signal → 日报 + AI 分析
```

---

## 三、L1：市场态势判断

用 **沪深300 日线**（`index_daily`, `index_code='000300.SH'`）判断当日大盘 regime。

| Regime | 判定（HS300 close 相对 MA） | 主推策略类别 |
|---|---|---|
| **BULL_STRONG** | close > MA20 > MA60 且 MA20 上行（5 日斜率>0） | Trend / VolumePrice |
| **BULL_WEAK** | close > MA20，但 MA20 未明显上行 | Trend / Reversal / VolumePrice |
| **BEAR_WEAK** | close < MA20 但 > MA60 | 只推 Reversal + Fundamental |
| **BEAR_STRONG** | close < MA60 | 极严条件 |

### 3.1 数据依赖（v1.1 明确）

**只依赖 `index_daily` 表的 HS300 收盘价**（趋势 + 均线），**不依赖 `market_daily` 的情绪数据**。

原因：`market/sentiment.py` 的 `_fetch_by_date_raw` 明确说明"涨跌家数历史精确统计成本太大，回填只写涨停数"。也就是说：
- `market_daily.up_count / down_count` 历史数据全 0
- 情绪型 regime 判断（涨停率、破板率）只能实时向前累积

**结论**：本设计里的 regime 判断**仅用 HS300 均线**，情绪型 regime 作为未来增强（阶段 D），需累积 30+ 交易日实时数据后启用。

### 3.2 实现位置

新增 `quant_system/market/regime.py`：

```python
from enum import Enum

class Regime(str, Enum):
    BULL_STRONG = "BULL_STRONG"
    BULL_WEAK   = "BULL_WEAK"
    BEAR_WEAK   = "BEAR_WEAK"
    BEAR_STRONG = "BEAR_STRONG"

def detect_regime(trade_date: date, repos: Repositories) -> Regime:
    """仅基于 HS300 均线判断，不依赖情绪数据。"""
    ...
```

---

## 四、L2：风险硬否决（Hard Filter）

命中任一 → 股票直接淘汰。阈值走配置，不硬编码。

### 4.1 修订后的规则（v1.1）

| 否决条件 | 默认阈值 | 依赖字段 | 说明 |
|---|---|---|---|
| ✅ 超买过高 | RSI(14) ≥ 85 | `rsi_14` | 保留，短期极度过热 |
| ⚠️ 暴涨过快（**板块自适应**） | 主板 20% / 创业板 30% / 科创板 30% | `return_5d + code` | 主板 30% 永远触发不了（日涨停 10%，5 天上限 61%），必须按板块分档 |
| ✅ 量价背离 | 突破新高但 `volume_ratio` < 0.8 | `break_high_20d + volume_ratio` | 保留，上涨无量 |
| ✅ 一字板（v1.2 精确化） | `O == H == L == C` **且** `\|pct_change\| ≥ 涨跌停幅 × 0.98`（浮点保护） | `daily_kline` 当日 OHLC + `pct_change` | **新增**（原方案的"涨跌停淘汰"过错） |
| ✅ 关键指标缺失 | `ma20 / macd / rsi_14` 任一为 NULL | 特征表 | 保留 |
| ❌ 涨跌停淘汰 | ~~\|pct_change\| ≥ 涨跌停幅~~ | | **删除**（涨停是 BREAKOUT 最想抓的信号） |
| ❌ ATR/close ≥ 6% | ~~淘汰~~ | | **改为 soft penalty**（见 L5） |

### 4.2 板块自适应阈值实现

复用 `quant_system.infra.board.classify()`：

```python
def _return_5d_threshold(code: str) -> float:
    """按板块返回 return_5d 硬过滤阈值。"""
    board = classify(code)
    if board == Board.MAIN:
        return 20.0
    elif board in (Board.GEM, Board.STAR):
        return 30.0
    else:
        return 30.0  # 北交所等


def _price_limit_pct(code: str) -> float:
    """按板块返回涨跌停幅（用于一字板判定）。

    - 主板 (MAIN): 10%
    - 创业板 (GEM) / 科创板 (STAR): 20%
    - ST 股: 5%（暂不支持，本系统已过滤 ST）
    - 北交所 (BSE): 30%
    """
    board = classify(code)
    if board in (Board.GEM, Board.STAR):
        return 20.0
    if board == Board.BSE:
        return 30.0
    return 10.0  # 主板 & 其它


def _is_one_word_limit(open_p, high, low, close, pct_change, code: str) -> bool:
    """一字板判定（O==H==L==C 且触及涨跌停幅 × 0.98）。"""
    if None in (open_p, high, low, close, pct_change):
        return False
    if not (open_p == high == low == close):
        return False
    limit = _price_limit_pct(code)
    return abs(pct_change) >= limit * 0.98
```

### 4.3 被过滤股票的处理（v1.1 修订）

不再写入 `data_quality_check`（避免语义混淆和撑爆表）：

- 写入 `SelectionReport.hard_filtered` 内存字段（`list[dict]`：`code / reason`）
- 日报"概览"块新增一行："**因风险硬过滤剔除 N 只**"
- 未来若需持久化，单独新增 `selection_filter_log` 表（阶段 D 考虑）

### 4.4 实现位置

新增 `quant_system/strategy/risk_filter.py`：
```python
def apply_hard_filters(
    df: pd.DataFrame, cfg: HardFilterConfig, kline_repo,
) -> tuple[pd.DataFrame, list[dict]]:
    """返回 (通过的 df, 被过滤的 [{code, reason}, ...])"""
```

---

## 五、L3：策略池扩展（3 → 11 条）

保留现有 3 条，新增 8 条。按"信号性质"分成 4 类。

### 5.1 类 A · 趋势跟随（TREND）

| 策略 | 触发条件 | sub_score | 状态 |
|---|---|---|---|
| `TREND_BREAKOUT` | break_high_20d + vol_ratio≥1.5 + ma_position>0 + RSI∈[50,75] | 75-95 | ✅ 现有增强（加 RSI 上限） |
| `TREND_MA_BULL` | ma_bull_arrange + return_20d≥5% + macd_hist>0 | 70-90 | ✅ 现有增强（加 hist>0） |
| `TREND_MACD_CROSS` | macd_golden_cross + MACD 值在 0 轴上方 + close>MA20 | 70-85 | 🆕 |

### 5.2 类 B · 反转与回踩（REVERSAL）

| 策略 | 触发条件 | sub_score | 状态 |
|---|---|---|---|
| `REVERSAL_OVERSOLD` | RSI<25 + close 接近 boll_lower（≤下轨×1.02）+ return_5d>-8% + 缩量止跌（vol_ratio<0.8） | 65-85 | 🆕（B1 首批） |
| `REVERSAL_MA_PULLBACK` | 5 天内触及 MA20 ±2% + MA20 上行 + 未跌破 MA60 | 60-80 | 🆕 |
| `REVERSAL_MACD_TURN`（v1.1 改名） | macd_hist 由负转正 + RSI 从<30 反弹到 30-50 | 60-80 | 🆕（原名 MACD_BOTTOM 误导为"背离"） |

**关于命名（v1.1）**：真正的"MACD 底背离"需要多周期峰谷检测（`scipy.signal.find_peaks` 对比价格 & MACD 的低点），工作量比这个规则大得多。本策略只是"MACD 柱由负转正 + RSI 低位反弹"，是普通反转信号，改名 `REVERSAL_MACD_TURN` 描述更准。真正的背离检测留作未来增强。

### 5.3 类 C · 量价与形态（VOLUME_PRICE）

| 策略 | 触发条件 | sub_score | 状态 |
|---|---|---|---|
| `VOL_PRICE_BREAK` | break_high_20d + volume_ratio≥2 + close>boll_mid | 75-90 | 🆕（B1 首批） |
| `VOL_SHRINK_TREND` | 上涨过程中 vol_ratio 从>1.5 回落到 0.8-1.2 + close>MA10 | 65-80 | 🆕 |
| `BOLL_MID_CROSS` | close 上穿 boll_mid 且 boll_width 从收敛转扩张 | 65-80 | 🆕 |

### 5.4 类 D · 基本面（FUNDAMENTAL）

| 策略 | 触发条件 | sub_score | 状态 |
|---|---|---|---|
| `VALUE_GROWTH` | PE∈[0,30] + ROE≥12% + 净利润 YoY>0 + 营收 YoY>0 | 75-95 | ✅ 保留 |
| `QUALITY_HIGH_ROE` | ROE≥18% + PE≤25 + 市值≥50 亿 | 70-85 | 🆕 |

### 5.5 策略实现约束

- **零 IO**：策略函数只吃 `pd.DataFrame` + params，不访问 DB
- **每条一个文件**：新增策略放 `quant_system/strategy/`
- **在 `stock_selector.build_strategies()` 中注册**
- **每条策略必须声明 `category`**：`trend / reversal / volume_price / fundamental`

---

## 六、L4：共振门控

**核心规则：单策略不能直接进 Top，必须满足 regime 对应的最小共振度。**

### 6.1 共振度定义

**共振度 = 命中策略所属的不同类别（category）数**，而不是命中策略的总条数。

- 命中 `TREND_BREAKOUT + TREND_MACD_CROSS` → 共振度 = 1（都是 trend）
- 命中 `TREND_BREAKOUT + VOL_PRICE_BREAK` → 共振度 = 2
- 命中 `TREND_BREAKOUT + VOL_PRICE_BREAK + VALUE_GROWTH` → 共振度 = 3

### 6.2 按 regime 的门槛

| Regime | 最小共振度 | 特别要求 |
|---|---|---|
| BULL_STRONG | 1 | 允许单类别通过 |
| BULL_WEAK | 2 | 必须两类共振 |
| BEAR_WEAK | 2 | 必须两类且**至少含 Fundamental** |
| BEAR_STRONG | 3 | 必须三类且**必须含 Fundamental** |

不满足 → 淘汰。

**实现位置**：`stock_selector.py` 里，`score_stock` 前先做门控。

---

## 七、L5：加权综合评分（regime 感知）

### 7.1 权重表（v1.1：用 dict 常量而非 12 个环境变量）

在 `settings.py` 里放常量：

```python
REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "BULL_STRONG": {"tech": 45, "capital": 30, "fund": 25, "bonus_per_cat": 5},
    "BULL_WEAK":   {"tech": 40, "capital": 25, "fund": 35, "bonus_per_cat": 5},
    "BEAR_WEAK":   {"tech": 30, "capital": 20, "fund": 50, "bonus_per_cat": 8},
    "BEAR_STRONG": {"tech": 20, "capital": 10, "fund": 70, "bonus_per_cat": 10},
}
```

如果确实要环境变量覆盖，用一个 JSON 字段：
```
QS_STRATEGY__REGIME_WEIGHTS_JSON='{"BULL_STRONG":{"tech":50,...}}'
```

pydantic-settings 有 `Field(default=..., validator=json.loads)` 的处理方式。

### 7.2 维度自适应归一（v1.2 强化）

**问题背景**：熊市中，小盘成长股常常 `roe_latest / pe_ttm / *_yoy` 全 NULL（还没披露财报），F=0，`final = 0.7 × 0 + 0.2 × T + 0.1 × C` → 直接判死。

**v1.1 方案**：若某维度核心特征全 NULL，该维度权重归零，剩余归一。

**v1.1 遗留隐患（v1.2 修复）**：
- 技术分几乎不可能 NULL（ma20 只要 20 天 K 线就有）→ "无数据淘汰"分支形同虚设
- 更常见场景是"**只有技术数据 T，C 和 F 都缺**"（次新股、冷门股）：
  - v1.1 逻辑下 `adjusted_w_tech = 100`，一个技术分 90 的次新股能拿 90 分冲到 Top
  - 但这只票**数据不全**，本不应该获得高置信度

**v1.2 修订**：加两条保险规则。

**规则 A（硬约束）**：至少 2 维度有数据，否则**硬淘汰**。

```python
def adjusted_weights(regime_w, has_tech_data, has_capital_data, has_fund_data):
    """v1.2：至少 2 维度必须有数据，否则返回 None 触发淘汰。"""
    active = {}
    if has_tech_data:    active["tech"]    = regime_w["tech"]
    if has_capital_data: active["capital"] = regime_w["capital"]
    if has_fund_data:    active["fund"]    = regime_w["fund"]

    if len(active) < 2:   # v1.2 新增：<2 维度直接淘汰
        return None

    total = sum(active.values())
    # 归一到 100（保持"分数上限 100"的直觉）
    return {k: v / total * 100 for k, v in active.items()}
```

**规则 B（软约束）**：基本面维度 NULL 时，`final_score` 上限 75（防冲顶）。

```python
if not has_fund_data:
    final_score = min(final_score, 75.0)
```

**判定数据有无的原则**：
- `has_tech_data` = `ma20 or macd or rsi_14 is not None`（几乎必有）
- `has_capital_data` = `volume_ratio or turnover_rate is not None`
- `has_fund_data` = `pe_ttm or roe_latest is not None`

**淘汰记录**：因维度不足被淘汰的股票，进 `SelectionReport.hard_filtered`，reason=`INSUFFICIENT_DIMENSIONS`。

### 7.3 分维度打分

- **技术分 T**（0-100）= max(命中的 Trend / Reversal / VolumePrice 类策略的 sub_score)
- **资金分 C**（0-100）= 量比 + 换手率 + 换手率变化（现有 `_score_capital` 复用）
- **基本面分 F**（0-100）= max(命中的 Fundamental 类 sub_score)，若都没命中且有基本面数据 → 用 `_score_fundamental_from_features` 兜底

### 7.4 共振奖励（跨类别）

```
resonance_bonus = (共振度 - 1) × bonus_per_cat
```

按 regime 取 `bonus_per_cat`（5/5/8/10）。

**同类别内多命中不再叠加加分**（只取子分最高的那条参与 T/F 维度打分）。

### 7.5 软风险扣分（Soft Penalty）

L2 是硬否决。L5 是"临界警告"：没到淘汰线但值得警惕。

| 风险项 | 触发阈值 | 扣分 | 依赖 |
|---|---|---|---|
| RSI 接近超买 | 75 ≤ RSI < 85 | -5 | `rsi_14` |
| 短期涨过多（板块自适应） | 主板 15-20% / 创业板 20-30% | -3 | `return_5d + code` |
| 数据质量 WARN | 该股当日有 WARN 记录 | -2 | `data_quality_check` |
| 布林带宽异常 | boll_width ≥ 15% | -3 | `boll_width` |
| **ATR/close 偏高（v1.1 迁自 L2）** | ATR/close ≥ 8% | -5 | `atr_14 + close` |
| **假突破**（v1.2 挪到 B1） | 过去 5 日曾 break_high_20d=True，但今日 close < high_20d × 0.95 | -5 | `daily_feature.fake_break_5d`（新字段） |

**v1.1/v1.2 说明**：
- ATR 从硬过滤下调为软扣分，避免高波动优质票（宁德、比亚迪牛市阶段）被误伤
- 未来可优化为 `ATR / ATR_60d_median`（自己跟自己比），本次先用绝对值
- **假突破在 v1.2 挪到阶段 B1 实现**：需在 `feature_store/builder.py` 加 `fake_break_5d` 字段（避免 selector 里额外查过去 5 日数据）

### 7.6 最终得分

```
final_score = adjusted_w_tech × T/100 + adjusted_w_cap × C/100
              + adjusted_w_fund × F/100
              + resonance_bonus - soft_penalty

clip(final_score, 0, 100)
```

---

## 八、L6：产出结构升级

`ScoredStock` 新增字段（不破坏兼容）：

```python
@dataclass
class ScoredStock:
    # 现有字段保留
    code: str
    final_score: float
    tech_score: float
    capital_score: float
    fundamental_score: float
    hit_strategies: list[str]
    reasons: list[str]
    raw_results: list[StrategyResult]

    # 🆕 新增
    regime: str = "UNKNOWN"                    # 当日市场态势
    resonance_count: int = 0                   # 共振度（=命中的不同类别数）
    resonance_categories: list[str] = []       # 命中哪几类，v1.2 按固定顺序输出
    positive_reasons: list[str] = []           # 命中理由（分开）
    risk_flags: list[str] = []                 # 风险标记（触发 soft penalty 的项）
```

**v1.2 说明**：
- 被 L2/L5(维度不足) **硬过滤**的股票**不会构造 ScoredStock**，只放 `SelectionReport.hard_filtered`。所以这里没有 `hard_filter_reason` 字段（旧版曾提过，其实没意义）。
- `resonance_categories` 按固定顺序输出，避免 `[trend, fundamental]` 与 `[fundamental, trend]` 表述不一致：
  ```python
  CATEGORY_ORDER = ["trend", "reversal", "volume_price", "fundamental"]
  resonance_categories = [c for c in CATEGORY_ORDER if c in hit_categories]
  ```

`SelectionReport` 新增：
```python
hard_filtered: list[dict] = []
# 每项: {"code": "000001.SZ", "reason": "RSI_TOO_HIGH" | "RETURN_5D_EXTREME"
#        | "VOLUME_PRICE_DIVERGENCE" | "ONE_WORD_LIMIT" | "MISSING_KEY_FEATURE"
#        | "INSUFFICIENT_DIMENSIONS"}
regime: str = "UNKNOWN"          # 当日 regime（阶段 A 保持 UNKNOWN，阶段 C 才真填）
```

**下游受益**：
- **日报**：单独展示"⚠️ 风险提示"块 + "共振度"标签 + "因风险硬过滤剔除 N 只"
- **AI 分析（已有）**：Prompt 里带上 regime + risk_flags，让 AI 判断"顺势"还是"警惕"（v1.1 待决策项 3 确认为**是**）
- **strategy_signal 表**：新增列 `regime`、`resonance_count`（nullable，兼容老数据）

---

## 九、配置扩展（.env）

```dotenv
# 策略共振门控
QS_STRATEGY__RESONANCE__BULL_STRONG_MIN=1
QS_STRATEGY__RESONANCE__BULL_WEAK_MIN=2
QS_STRATEGY__RESONANCE__BEAR_WEAK_MIN=2
QS_STRATEGY__RESONANCE__BEAR_STRONG_MIN=3

# 硬过滤阈值（v1.1 修订）
QS_STRATEGY__HARD_FILTER__RSI_MAX=85
QS_STRATEGY__HARD_FILTER__RETURN_5D_MAIN=20      # 主板
QS_STRATEGY__HARD_FILTER__RETURN_5D_GEM=30       # 创业板
QS_STRATEGY__HARD_FILTER__RETURN_5D_STAR=30      # 科创板
QS_STRATEGY__HARD_FILTER__DIVERGENCE_VOL_MIN=0.8 # 量价背离

# 关闭某类策略（示例：不喜欢反转类可关掉）
# v1.2 语义澄清：关闭类别后，共振门槛不自动下调；若配置过严导致 Top 为空，
# selector 会给出 WARN 日志（"共振门槛过严，Top 为空。建议放宽 CATEGORIES 或 RESONANCE_MIN"）
QS_STRATEGY__ENABLED_CATEGORIES=trend,reversal,volume_price,fundamental

# 权重表整体覆盖（v1.1：不再拆成 12 个变量）
# QS_STRATEGY__REGIME_WEIGHTS_JSON='{"BULL_STRONG":{"tech":50,"capital":25,"fund":25,"bonus_per_cat":5},...}'

# 软风险扣分（阶段 A）
QS_STRATEGY__SOFT_PENALTY__RSI_75_85=5
QS_STRATEGY__SOFT_PENALTY__RETURN_5D_UPPER=3
QS_STRATEGY__SOFT_PENALTY__DQ_WARN=2
QS_STRATEGY__SOFT_PENALTY__BOLL_WIDTH_HIGH=3
QS_STRATEGY__SOFT_PENALTY__ATR_HIGH=5             # v1.1 迁自 L2

# 阶段 B1 才启用
# QS_STRATEGY__SOFT_PENALTY__FAKE_BREAK=5           # 依赖 fake_break_5d 字段
```

---

## 十、数据 & 表结构影响

### 10.1 依赖已有表（无 schema 变更）
- `daily_feature` ✅
- `daily_kline` ✅（含 OHLC 用于一字板判定 + 假突破检测）
- `index_daily` ✅（regime 判断，需先 `qs update market`）
- ~~`data_quality_check`~~（v1.1 修订：**不再**用于记录 L2 过滤日志）

### 10.2 建议新增列（可选，加了更好）
- `strategy_signal.regime` (String(16), nullable)
- `strategy_signal.resonance_count` (Integer, nullable)
- `daily_report_item.risk_flags` (JSON, nullable)

**兼容策略**：老数据 NULL；新代码新旧兼容读。

### 10.3 数据回填限制（v1.1 明确）

- ✅ `index_daily.HS300` 历史可回填（`qs update market` 拉 2019 至今）
- ❌ `market_daily.up_count / down_count` 历史无法精确回填，需实时累积
- ❌ 情绪型 regime（涨停率、破板率）需累积 30+ 交易日后启用（阶段 D）

---

## 十一、分期落地

### 阶段 A（🅰️ 收益最大 · 改动最小）— 预计 1.5-2 小时（v1.2 重估）

**目标**：只做 L2（硬过滤）+ L4/L5（跨类别共振 + soft penalty + 维度自适应归一），不新增策略。

**v1.2 工作量重估理由**：
- 板块自适应阈值（return_5d + 一字板涨跌停幅）
- 一字板判定要读 `daily_kline` 的 OHLC
- 维度自适应归一 + 至少 2 维度约束
- 日报 UI 加"⚠️ 风险提示"块和"过滤汇总"块
- 假突破 soft penalty **不做**（挪到 B1，需配合 `feature_store` 加字段）

**具体动作**：
1. 新增 `strategy/risk_filter.py` + `HardFilterConfig`（含板块自适应 return_5d + 一字板 + 关键指标 NULL）
2. `stock_selector.py` 在 `run_selector` 里插入过滤，`SelectionReport.hard_filtered` 记录
3. `scoring.py`：
   - `multi_hit_bonus` 改成"共振度"（按 category 去重后计数）
   - 加 soft penalty（不含假突破）+ `risk_flags` 输出
   - 维度自适应归一（含"至少 2 维度"硬约束 + "基本面 NULL 上限 75"软约束）
   - `resonance_categories` 按固定顺序输出
4. `ScoredStock` 加 `risk_flags`、`resonance_count`、`resonance_categories` 字段
5. `SelectionReport` 加 `hard_filtered`、`regime`（阶段 A 保持 "UNKNOWN"）
6. Report/Markdown/HTML 展示 `risk_flags` + "因风险硬过滤剔除 N 只" + 共振度标签
7. **AI Prompt**：加入 `risk_flags` 列表；**不塞 regime 字段**（避免 LLM 幻觉编造 regime），等阶段 C 再加

**验证方式**：跑一次 `qs pipeline --skip-update`，对比新老 Top20 差异，观察：
- **hard_filtered 数量**：HS300 每天 20-50 只合理，>100 说明规则太严
- **Top 20 中带 risk_flags 的比例**：>50% 说明市场整体偏热或阈值太松
- **共振度分布**：Top 20 中共振度 ≥ 2 的比例应 >70%
- **老 Top 20 与新 Top 20 的重合度**：预期 40-60% 重合。<30% 说明改动过激；>80% 说明没起作用
- **被剔的老 Top**：手工看几只被踢出的，验证是否合理

### 阶段 B1（🅱️1 谨慎扩策略）— 预计 3-4 小时（v1.2 重估）

**目标**：先只上 2 条新策略 + 补 `qs signal stats` CLI + 补假突破 soft penalty。

**具体动作**：
1. 新增 `REVERSAL_OVERSOLD`（弱市反转）
2. 新增 `VOL_PRICE_BREAK`（强放量突破，比现有 BREAKOUT 更严）
3. **[v1.2 迁入]** `feature_store/builder.py` 新增字段 `fake_break_5d`（bool）：过去 5 日曾 `break_high_20d=True` 但今日 `close < high_20d × 0.95`
4. **[v1.2 迁入]** `scoring.py` 加入"假突破" soft penalty（-5 分）
5. 补 `qs signal stats --strategy CODE --days N` CLI（当前是 TODO）：
   - 该策略过去 N 天命中多少只
   - 命中之后 5/20 天平均收益 & 胜率
   - 各评分区间的胜率分层
6. 在两个新策略上跑一遍历史统计，看命中率和信号质量

**验证周期**：至少 1-2 周实盘观察，确认信号质量后再进 B2。

### 阶段 B2（🅱️2 补齐策略池）— 预计 3 小时

**目标**：补 3-4 条剩余策略（观察 B1 验证结论后决定具体顺序）。

候选：`REVERSAL_MA_PULLBACK / TREND_MACD_CROSS / QUALITY_HIGH_ROE / BOLL_MID_CROSS / VOL_SHRINK_TREND / REVERSAL_MACD_TURN`

不追求一次性全上，按 signal_stats 表现挑最有意义的先加。

### 阶段 C（🅲️ regime 感知）— 预计 2 小时

**目标**：加基于 HS300 均线的 regime 判断 + 动态权重（不依赖情绪数据）。

**具体动作**：
1. 新增 `market/regime.py`，`detect_regime(trade_date, repos) -> Regime`
2. `settings.py` 加 `REGIME_WEIGHTS` 常量字典
3. `stock_selector` 读 regime → 传给 scoring / 共振门控
4. `SelectionReport.regime` 落库到 `strategy_signal.regime`

**依赖**：`qs update market` 已跑过，`index_daily` 有 HS300 至少 60 日数据。

### 阶段 D（🅳 未来 · 情绪型 regime）— 待启动

需 `market_daily.up_count / down_count` 从今天起实时累积 30+ 交易日后开启。加入"涨停率、破板率、大盘破位"作为 regime 二级判定。

---

## 十二、待决策项（v1.1 已回答）

1. **共振度是否要 category 粒度硬约束**？→ ❌ 不做。`BEAR_WEAK` 已用"必须含 Fundamental"部分实现，其他 regime 保持数量阈值。
2. **被硬过滤的股票是否记录**？→ ❌ 不进 `data_quality_check`。只放内存 + 日报"过滤汇总"块。持久化未来单开表。
3. **风险扣分是否给 AI 展示**？→ ✅ 是。`risk_flags` 直接进 AI prompt，让 LLM 输出"警惕"而非无脑推荐。
4. **REVERSAL 类在牛市是否静默**？→ ❌ 不静默。让共振门槛决定能否进 Top；数据仍写库供未来回测。

---

## 十三、非目标（本设计不做的事）

- 不接入行业/板块联动分析（未来 `sector_features` 时做）
- 不接入 LLM 判 regime（保持规则化可回测）
- 不做仓位管理 / 组合优化（属于 execution 层）
- ~~不改 `feature_store`~~（v1.2 修订：阶段 B1 会加 `fake_break_5d` 字段，其它维持）
- 不实现真正的 MACD 底背离检测（需峰谷检测，工作量大，作为未来增强）
- 不做情绪型 regime（数据回填不可用，阶段 D 起步）
- 不做"ATR 相对历史中位数"的自适应波动率（`ATR/ATR_60d_median`），本轮先用绝对值

---

## 十四、评审历史

### v1.0（2026-07-15 早）
初版，五层门控 + 3→11 条策略 + regime 感知。评审得分 **75/100**。

### v1.1（2026-07-15 晚）
根据评审意见修订。评审得分 **90/100**，主要修订：

**🔴 硬伤修复（4 处）**：
- ATR 硬过滤 → 迁移到 soft penalty
- 涨跌停淘汰 → 改为"一字板"过滤
- `return_5d ≥ 30%` → 按板块分档（主板 20% / 创业板&科创板 30%）
- regime 数据依赖 → 明确只用 HS300，不用情绪数据

**🟡 打磨（4 处）**：
- 阶段 B 拆分 B1/B2
- `REVERSAL_MACD_BOTTOM` 改名 `REVERSAL_MACD_TURN`
- `VOL_SHRINK_TREND` 的"突破无效"量化定义
- 加权公式加维度自适应归一

**🟢 优化（2 处）**：
- 权重表用 dict 常量而非 12 个环境变量
- 被硬过滤股票不落 `data_quality_check`

### v1.2（2026-07-15 深夜）—— 定稿
第二轮评审后修订。**核心决策：加"至少 2 维度"硬约束**，堵住次新股高分冲顶漏洞。

**🟡 修订 7 处**：
1. **维度自适应归一升级**（关键）：至少 2 维度有数据（<2 硬淘汰）；基本面 NULL 时 `final_score` 上限 75
2. **一字板判定精确化**：`O==H==L==C` 且 `\|pct_change\| ≥ 涨跌停幅 × 0.98`；涨跌停幅按板块查
3. **resonance_categories 固定顺序**：`[trend, reversal, volume_price, fundamental]`
4. **AI Prompt 不塞 regime**（阶段 A）：避免 LLM 幻觉编造 regime
5. **假突破 soft penalty 挪到 B1**：需在 `feature_store` 加 `fake_break_5d` 字段配合
6. **`ENABLED_CATEGORIES` 语义澄清**：关闭类别后共振门槛不自动下调，selector 需 WARN
7. **阶段 A 工作量重估**：从 1h 改为 1.5-2h（更符合实际）

**📌 v1.2 定稿后进入实现阶段**，不再对本文档做规范性修订，仅在落地后补"完成状态"和"实施差异"。

---

## 十五、后续文档链接

- 落地后 PR → 更新头部状态为 `✅ 已实现（提交 XXX）`
- 阶段 A / B1 / B2 / C 各自单独 PR，各自更新 `十一、分期落地` 完成状态
- `qs signal stats` CLI 落地文档留在 07（策略）文档做补充
