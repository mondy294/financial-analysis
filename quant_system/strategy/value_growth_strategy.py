"""低估成长策略。

触发条件（默认）：
- pe_min <= pe_ttm <= pe_max（估值合理，默认 0-30）
- roe_latest >= 12%（净资产收益率≥12）
- net_profit_yoy_latest > 0（净利润同比为正）
- revenue_yoy_latest > 0（营收同比为正）

子分：
- 全命中：75~95（ROE 越高、利润增速越大越高）
- 缺 1 项：60~74（WATCH）

**注意**：如果基本面字段缺失，直接跳过（不判 hit 也不判 WATCH）。
"""
from __future__ import annotations

import pandas as pd

from quant_system.strategy.base_strategy import (
    SIGNAL_HIT,
    SIGNAL_WATCH,
    BaseStrategy,
    StrategyResult,
)


class ValueGrowthStrategy(BaseStrategy):
    code = "VALUE_GROWTH"
    name = "低估成长策略"
    category = "value"
    version = "v1.0"

    def evaluate(self, features: pd.DataFrame) -> list[StrategyResult]:
        params = self.params
        pe_min = float(params.get("pe_min", 0.0))
        pe_max = float(params.get("pe_max", 30.0))
        roe_min = float(params.get("roe_min", 12.0))
        np_yoy_min = float(params.get("net_profit_yoy_min", 0.0))
        rev_yoy_min = float(params.get("revenue_yoy_min", 0.0))

        results: list[StrategyResult] = []
        for _, row in features.iterrows():
            code = row["code"]
            pe = self._as_float(row.get("pe_ttm"))
            roe = self._as_float(row.get("roe_latest"))
            np_yoy = self._as_float(row.get("net_profit_yoy_latest"))
            rev_yoy = self._as_float(row.get("revenue_yoy_latest"))

            # 基本面缺失：跳过
            if pe is None and roe is None and np_yoy is None and rev_yoy is None:
                continue

            cond_pe = pe is not None and pe_min <= pe <= pe_max
            cond_roe = roe is not None and roe >= roe_min
            cond_np = np_yoy is not None and np_yoy > np_yoy_min
            cond_rev = rev_yoy is not None and rev_yoy > rev_yoy_min

            hits = sum([cond_pe, cond_roe, cond_np, cond_rev])

            if hits == 4:
                reasons = [
                    f"PE {pe:.1f}（区间 [{pe_min:.0f}, {pe_max:.0f}]）",
                    f"ROE {roe:.1f}%（≥{roe_min:.0f}%）",
                    f"净利润同比 {np_yoy:.1f}%",
                    f"营收同比 {rev_yoy:.1f}%",
                ]
                # ROE 从 12 到 30 → 75-95
                score = 75.0 + min(20.0, max(0.0, (roe - roe_min) / 18.0 * 20))
                results.append(StrategyResult(
                    code=code, strategy_code=self.code,
                    signal_type=SIGNAL_HIT, sub_score=score,
                    reasons=reasons, category=self.category,
                ))
            elif hits == 3:
                r = []
                if cond_pe: r.append(f"PE {pe:.1f}")
                if cond_roe: r.append(f"ROE {roe:.1f}%")
                if cond_np: r.append(f"净利润同比 {np_yoy:.1f}%")
                if cond_rev: r.append(f"营收同比 {rev_yoy:.1f}%")
                results.append(StrategyResult(
                    code=code, strategy_code=self.code,
                    signal_type=SIGNAL_WATCH, sub_score=60.0,
                    reasons=r, category=self.category,
                ))

        return results
