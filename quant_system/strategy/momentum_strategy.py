"""均线多头趋势策略。

触发条件（默认）：
- ma_bull_arrange = True（MA5 > MA10 > MA20）
- macd_golden_cross = True（当日 MACD 金叉）
- return_20d > 5%（20 日累计上涨 5% 以上）

子分：
- 全命中：80~95（return_20d 越大越高）
- 满足 2/3：60~75
"""
from __future__ import annotations

import pandas as pd

from quant_system.strategy.base_strategy import (
    SIGNAL_HIT,
    SIGNAL_WATCH,
    BaseStrategy,
    StrategyResult,
)


class MomentumStrategy(BaseStrategy):
    code = "MOMENTUM_MA"
    name = "均线多头趋势策略"
    category = "momentum"
    version = "v1.0"

    def evaluate(self, features: pd.DataFrame) -> list[StrategyResult]:
        params = self.params
        min_return_20d = float(params.get("min_return", 0.05)) * 100  # 转百分比
        require_bull = bool(params.get("require_ma_bull_arrange", True))
        require_golden = bool(params.get("require_macd_golden", True))

        results: list[StrategyResult] = []
        for _, row in features.iterrows():
            code = row["code"]
            bull = self._as_bool(row.get("ma_bull_arrange"))
            gc = self._as_bool(row.get("macd_golden_cross"))
            r20 = self._as_float(row.get("return_20d")) or -999.0

            cond_bull = bull if require_bull else True
            cond_gc = gc if require_golden else True
            cond_r20 = r20 >= min_return_20d

            hits = sum([cond_bull, cond_gc, cond_r20])

            if cond_bull and cond_gc and cond_r20:
                reasons = [
                    "MA5>MA10>MA20（多头排列）",
                    "MACD 当日金叉",
                    f"20 日累计上涨 {r20:.2f}%",
                ]
                # return_20d 从 5% 到 30% 线性 → 80~95 分
                score_bonus = min(15.0, max(0.0, (r20 - min_return_20d) / 25.0 * 15))
                sub_score = min(95.0, 80.0 + score_bonus)
                results.append(StrategyResult(
                    code=code, strategy_code=self.code,
                    signal_type=SIGNAL_HIT, sub_score=sub_score,
                    reasons=reasons, category=self.category,
                ))
            elif hits >= 2:
                r = []
                if cond_bull: r.append("多头排列")
                if cond_gc: r.append("MACD 金叉")
                if cond_r20: r.append(f"20 日上涨 {r20:.2f}%")
                results.append(StrategyResult(
                    code=code, strategy_code=self.code,
                    signal_type=SIGNAL_WATCH, sub_score=55.0,
                    reasons=r, category=self.category,
                ))

        return results
