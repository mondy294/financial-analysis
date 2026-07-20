from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from quant_system.eventstats.aggregate import aggregate_events
from quant_system.eventstats.observe import compute_observation
from quant_system.eventstats.tags import board_tag, enrich_tags


def _bars(n: int, *, start_close: float = 10.0, daily: float = 0.01) -> pd.DataFrame:
    rows = []
    c = start_close
    d0 = date(2024, 1, 2)
    for i in range(n):
        o = c
        c = o * (1 + daily)
        h = max(o, c) * 1.01
        l = min(o, c) * 0.99
        rows.append(
            {
                "trade_date": d0 + timedelta(days=i),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
            }
        )
    return pd.DataFrame(rows)


def test_observation_no_lookahead_signal_not_in_returns() -> None:
    """forward_bars 第 0 根是 T+1；收益相对信号收盘。"""
    anchor = 10.0
    forward = _bars(5, start_close=10.0, daily=0.02)
    # 人为把 T+1 open/close 设为可知
    m = compute_observation(forward, anchor_close=anchor, horizon_bars=5, return_horizons=[1, 3, 5])
    assert m["forward_status"] == "ok"
    assert m["forward_bars_available"] == 5
    assert m["return_1"] is not None
    # return_1 = close[0]/anchor - 1，不应等于 0 除非碰巧
    assert abs(m["return_1"] - (float(forward.iloc[0]["close"]) / anchor - 1)) < 1e-9


def test_observation_truncated() -> None:
    forward = _bars(3, start_close=10.0)
    m = compute_observation(forward, anchor_close=10.0, horizon_bars=20, return_horizons=[1, 5, 20])
    assert m["forward_status"] == "truncated"
    assert m["return_1"] is not None
    assert m["return_20"] is None
    assert m["mfe"] is not None
    assert m["mae"] is not None


def test_observation_insufficient() -> None:
    m = compute_observation(pd.DataFrame(), anchor_close=10.0, horizon_bars=20)
    assert m["forward_status"] == "insufficient"
    assert m["return_1"] is None


def test_mae_mfe_positive_convention() -> None:
    # 先跌后涨
    rows = []
    prices = [9.0, 8.5, 8.0, 9.5, 11.0]
    for i, c in enumerate(prices):
        rows.append(
            {
                "trade_date": date(2024, 1, 2) + timedelta(days=i),
                "open": c,
                "high": c * 1.02,
                "low": c * 0.98,
                "close": c,
            }
        )
    forward = pd.DataFrame(rows)
    anchor = 10.0
    m = compute_observation(forward, anchor_close=anchor, horizon_bars=5)
    assert m["mfe"] is not None and m["mfe"] > 0
    assert m["mae"] is not None and m["mae"] > 0


def test_aggregate_basic() -> None:
    events = [
        {"code": "A", "forward_status": "ok", "return_5": 0.1, "mae": 0.02, "mfe": 0.15},
        {"code": "B", "forward_status": "ok", "return_5": -0.05, "mae": 0.04, "mfe": 0.08},
        {"code": "A", "forward_status": "truncated", "return_5": 0.02, "mae": 0.01, "mfe": 0.03},
    ]
    s = aggregate_events(events, universe_size_hint=100)
    assert s["coverage"]["event_count"] == 3
    assert s["coverage"]["stock_count"] == 2
    assert s["metrics"]["return_5"]["n_valid"] == 3
    assert abs(s["metrics"]["return_5"]["win_rate"] - 2 / 3) < 1e-9


def test_board_tags() -> None:
    assert board_tag("300750.SZ") == "创业板"
    assert board_tag("688981.SH") == "科创板"
    assert "创业板" in enrich_tags("300750.SZ", {"industry_name": "电池"})
    assert "电池" in enrich_tags("300750.SZ", {"industry_name": "电池"})
