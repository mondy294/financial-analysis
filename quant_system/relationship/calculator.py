"""关系算法（纯函数，无 DB / IO）。

扩展点：新增关系算法 = 新增一个 BaseCalculator 子类并注册到 CALCULATORS，
数据库 / Repository / CLI 均不改动。

第一版只实现 PearsonCalculator（基于收益率的皮尔逊相关）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time

import numpy as np
import pandas as pd
from loguru import logger

# 展示用的绝对值分档阈值
_HIST_THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9]


@dataclass
class WindowResult:
    """单窗口计算结果。"""
    window: str
    pairs: list[dict] = field(default_factory=list)   # {code_a, code_b, value, sample_size}
    evaluated: int = 0                                 # 共同样本达标的候选对数（阈值过滤前）
    universe_effective: int = 0                        # 有效参与股票数
    hist: dict = field(default_factory=dict)           # 绝对值分布 + 各阈值命中数
    capped: int = 0                                    # 因 max_neighbors 被裁掉的对数


class BaseCalculator(ABC):
    """关系算法基类。子类声明 relation_type 并实现 compute_window。"""

    relation_type: str = ""

    @abstractmethod
    def compute_window(
        self,
        returns: pd.DataFrame,
        window: str,
        days: int | None,
        *,
        min_sample: int,
        value_threshold: float,
        max_neighbors: int,
    ) -> WindowResult:
        ...


class PearsonCalculator(BaseCalculator):
    relation_type = "PEARSON"

    def compute_window(
        self,
        returns: pd.DataFrame,
        window: str,
        days: int | None,
        *,
        min_sample: int,
        value_threshold: float,
        max_neighbors: int,
    ) -> WindowResult:
        result = WindowResult(window=window)
        if returns is None or returns.empty:
            return result

        sub = returns if days is None else returns.tail(days)

        # 短窗口的样本门槛必须 <= 窗口长度：min_sample 视为「长窗地板」，
        # 短窗按窗口长度的 80% 折算（下限 20），否则 W60 永远配不出 120 样本。
        eff_min = min_sample if days is None else min(min_sample, max(20, int(round(days * 0.8))))

        # 预筛：单列有效样本 < eff_min 的股票直接剔除（无论如何配不出达标对）
        valid_counts = sub.notna().sum()
        keep_cols = [c for c in sub.columns if valid_counts.get(c, 0) >= eff_min]
        if len(keep_cols) < 2:
            return result
        sub = sub[sorted(keep_cols)]  # 升序 → 上三角 i<j 天然满足 code_a < code_b

        codes = list(sub.columns)
        n = len(codes)
        result.universe_effective = n
        logger.info(
            "Pearson {}：有效股票 {}，矩阵 {}×{}，开始 corr…",
            window, n, sub.shape[0], n,
        )
        t0 = time.monotonic()

        mask = sub.notna().to_numpy()
        corr = sub.corr(method="pearson", min_periods=eff_min).to_numpy()
        samp = mask.astype(np.int32).T @ mask.astype(np.int32)
        logger.info(
            "Pearson {}：corr 完成 {:.1f}s，开始筛边…",
            window, time.monotonic() - t0,
        )

        iu = np.triu_indices(n, k=1)
        v = corr[iu]
        s = samp[iu]

        finite = ~np.isnan(v)
        valid = finite & (s >= eff_min)
        result.evaluated = int(valid.sum())
        result.hist = self._histogram(np.abs(v[valid]))

        sel = valid & (np.abs(v) >= value_threshold)
        ia = iu[0][sel]
        ib = iu[1][sel]
        vv = v[sel]
        ss = s[sel]

        pairs, capped = self._apply_cap(codes, ia, ib, vv, ss, max_neighbors)
        result.pairs = pairs
        result.capped = capped
        logger.info(
            "Pearson {}：完成 总耗时 {:.1f}s，候选对 {}，写入候选 {}，裁剪 {}",
            window, time.monotonic() - t0, result.evaluated, len(pairs), capped,
        )
        return result

    @staticmethod
    def _histogram(absv: np.ndarray) -> dict:
        if absv.size == 0:
            return {"total": 0, "ge": {}, "bins": {}}
        ge = {str(t): int((absv >= t).sum()) for t in _HIST_THRESHOLDS}
        edges = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001]
        counts, _ = np.histogram(absv, bins=edges)
        labels = ["<0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", ">=0.9"]
        return {
            "total": int(absv.size),
            "ge": ge,
            "bins": dict(zip(labels, [int(c) for c in counts], strict=True)),
        }

    @staticmethod
    def _apply_cap(
        codes: list[str],
        ia: np.ndarray,
        ib: np.ndarray,
        vv: np.ndarray,
        ss: np.ndarray,
        max_neighbors: int,
    ) -> tuple[list[dict], int]:
        """按 |value| 降序贪心保留，正负各限制每只股票 max_neighbors 个邻居。"""
        order = np.argsort(-np.abs(vv))
        pos_count: dict[str, int] = {}
        neg_count: dict[str, int] = {}
        kept: list[dict] = []
        capped = 0
        for idx in order:
            a = codes[ia[idx]]
            b = codes[ib[idx]]
            val = float(vv[idx])
            counter = pos_count if val > 0 else neg_count
            if counter.get(a, 0) >= max_neighbors or counter.get(b, 0) >= max_neighbors:
                capped += 1
                continue
            counter[a] = counter.get(a, 0) + 1
            counter[b] = counter.get(b, 0) + 1
            kept.append({
                "code_a": a,
                "code_b": b,
                "value": round(val, 4),
                "sample_size": int(ss[idx]),
            })
        return kept, capped


def _corr_at_lag(a: np.ndarray, b: np.ndarray, k: int, min_sample: int) -> tuple[float, int]:
    """corr(a_t, b_{t+k})。k>0 → a 领先 b k 天；返回 (corr, 共同样本数)。"""
    if k > 0:
        aa, bb = a[:-k], b[k:]
    elif k < 0:
        aa, bb = a[-k:], b[:k]
    else:
        aa, bb = a, b
    m = ~np.isnan(aa) & ~np.isnan(bb)
    n = int(m.sum())
    if n < min_sample:
        return float("nan"), n
    x = aa[m] - aa[m].mean()
    y = bb[m] - bb[m].mean()
    denom = float(np.sqrt((x @ x) * (y @ y)))
    if denom == 0.0:
        return float("nan"), n
    return float((x @ y) / denom), n


class LeadLagCalculator:
    """领先-滞后：对候选对做互相关（lag∈[-max_lag,+max_lag]），取 |corr| 最大的 lag。

    不走 BaseCalculator.compute_window（那是全量上三角对称算法），
    而是只在给定候选对上逐对搜 lag——先后关系只在共动的票之间才有意义。
    存储：direction=最优 lag（+ 表示 code_a 领先 code_b），relation_value=该 lag 下相关度。
    """

    relation_type = "LEAD_LAG"

    def compute_pairs(
        self,
        returns: pd.DataFrame,
        candidate_pairs: list[tuple[str, str]],
        *,
        days: int | None,
        max_lag: int = 5,
        min_sample: int = 120,
        value_threshold: float = 0.6,
        min_lead_gain: float = 0.0,
    ) -> list[dict]:
        if returns is None or returns.empty or not candidate_pairs:
            return []
        sub = returns if days is None else returns.tail(days + max_lag)
        eff_min = min_sample if days is None else min(min_sample, max(20, int(round(days * 0.8))))
        arrs = {c: sub[c].to_numpy() for c in sub.columns}

        out: list[dict] = []
        for a, b in candidate_pairs:
            if a not in arrs or b not in arrs:
                continue
            best_c, best_lag, best_n = 0.0, 0, 0
            c0 = 0.0
            for k in range(-max_lag, max_lag + 1):
                c, n = _corr_at_lag(arrs[a], arrs[b], k, eff_min)
                if np.isnan(c):
                    continue
                if k == 0:
                    c0 = c
                if abs(c) > abs(best_c):
                    best_c, best_lag, best_n = c, k, n
            if best_lag == 0 or abs(best_c) < value_threshold:
                continue
            # 领先信号需比同期相关更强，避免把同步关系误判成先后
            if abs(best_c) - abs(c0) < min_lead_gain:
                continue
            out.append({
                "code_a": a, "code_b": b,
                "value": round(float(best_c), 4),
                "sample_size": int(best_n),
                "direction": int(best_lag),
            })
        return out


# 关系算法注册表：relation_type → Calculator 实例
CALCULATORS: dict[str, BaseCalculator] = {
    PearsonCalculator.relation_type: PearsonCalculator(),
}


def get_calculator(relation_type: str) -> BaseCalculator:
    key = relation_type.upper()
    if key not in CALCULATORS:
        raise ValueError(f"未注册的 relation_type: {relation_type}（已注册 {list(CALCULATORS)}）")
    return CALCULATORS[key]
