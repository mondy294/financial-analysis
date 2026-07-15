"""突破策略。

触发条件（默认）：
- break_high_20d = True（当日突破 20 日新高）
- volume_ratio >= 1.5（量能放大 1.5 倍以上）
- close > ma20（收盘站上 20 日均线，隐含在 ma_position > 0）

子分：
- 满足全部：80~100（量比越大分越高）
- 满足 2/3：60~79
- 满足 1/3：不 hit，可选 WATCH
"""
from __future__ import annotations

import pandas as pd

from quant_system.strategy.base_strategy import (
    SIGNAL_HIT,
    SIGNAL_WATCH,
    BaseStrategy,
    StrategyResult,
)


class BreakoutStrategy(BaseStrategy):
    code = "BREAKOUT_20D"
    name = "20 日突破策略"
    category = "technical"
    version = "v1.0"

    def evaluate(self, features: pd.DataFrame) -> list[StrategyResult]:
        params = self.params
        volume_ratio_min = float(params.get("volume_ratio_min", 1.5))
        require_above_ma20 = bool(params.get("require_above_ma20", True))

        results: list[StrategyResult] = []
        for _, row in features.iterrows():
            code = row["code"]
            break_flag = self._as_bool(row.get("break_high_20d"))
            vr = self._as_float(row.get("volume_ratio")) or 0.0
            ma_pos = self._as_float(row.get("ma_position")) or -999.0

            cond_break = break_flag
            cond_volume = vr >= volume_ratio_min
            cond_above_ma20 = (ma_pos > 0) if require_above_ma20 else True

            hits = sum([cond_break, cond_volume, cond_above_ma20])

            if cond_break and cond_volume and cond_above_ma20:
                # 全命中
                reasons = [
                    "突破 20 日新高",
                    f"量比放大 {vr:.2f}x",
                    f"站上 MA20（位置 {ma_pos*100:+.2f}%）",
                ]
                # 子分：基础 80 + 量比奖励（1.5→0，3.0→+15，5.0→+20）
                bonus = min(20.0, max(0.0, (vr - volume_ratio_min) * 10))
                sub_score = min(100.0, 80.0 + bonus)
                results.append(StrategyResult(
                    code=code, strategy_code=self.code,
                    signal_type=SIGNAL_HIT, sub_score=sub_score,
                    reasons=reasons, category=self.category,
                ))
            elif hits >= 2:
                # WATCH：满足 2/3
                reasons_watch = []
                if cond_break:
                    reasons_watch.append("突破 20 日新高")
                if cond_volume:
                    reasons_watch.append(f"量比放大 {vr:.2f}x")
                if cond_above_ma20:
                    reasons_watch.append(f"站上 MA20")
                results.append(StrategyResult(
                    code=code, strategy_code=self.code,
                    signal_type=SIGNAL_WATCH, sub_score=60.0,
                    reasons=reasons_watch, category=self.category,
                ))

        return results
