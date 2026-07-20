from __future__ import annotations

ENGINE_VERSION = "1.0.0"
AGGREGATION_VERSION = "1.0.0"
CALENDAR_V1 = "ChinaTradingCalendar"
ANCHOR_MODE_V1 = "t1_close"
PRICE_ADJ_V1 = "qfq"
OUTCOME_MODE_OBSERVATION = "observation"

DEFAULT_HORIZON_BARS = 20
DEFAULT_RETURN_HORIZONS = (1, 3, 5, 10, 20, 60)
DEFAULT_DEDUP_POLICY = "cooldown_h"  # H = horizon_bars

STANDARD_METRIC_COLUMNS = (
    "return_1",
    "return_3",
    "return_5",
    "return_10",
    "return_20",
    "return_60",
    "return_horizon",
    "mfe",
    "mae",
    "max_drawdown",
    "volatility",
    "bull_ratio",
    "up_days",
    "continuous_up_days",
    "highest_day",
    "lowest_day",
    "time_to_mfe",
    "time_to_mae",
    "forward_bars_available",
    "forward_status",
)
