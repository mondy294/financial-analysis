from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from quant_system.patterns.forward_returns import _returns_by_code


def test_returns_by_code_signal_close_to_forward() -> None:
    signal = date(2024, 1, 2)
    closes = [10.0, 10.5, 10.2, 11.0, 10.8, 12.0]
    rows = [
        {
            "code": "000001.SZ",
            "trade_date": signal + timedelta(days=i),
            "close": c,
            "adj_factor": 1.0,
        }
        for i, c in enumerate(closes)
    ]
    df = pd.DataFrame(rows)
    out = _returns_by_code(df, signal_date=signal, horizons=(1, 3, 5))
    r = out["000001.SZ"]
    assert abs(r["return_1"] - (10.5 / 10.0 - 1.0)) < 1e-9
    assert abs(r["return_3"] - (11.0 / 10.0 - 1.0)) < 1e-9
    assert abs(r["return_5"] - (12.0 / 10.0 - 1.0)) < 1e-9


def test_returns_by_code_truncated_and_adj() -> None:
    signal = date(2024, 1, 2)
    # 仅信号 + 2 根前瞻；adj 变化应归一到最新因子
    rows = [
        {"code": "A", "trade_date": signal, "close": 10.0, "adj_factor": 1.0},
        {"code": "A", "trade_date": signal + timedelta(days=1), "close": 11.0, "adj_factor": 2.0},
        {"code": "A", "trade_date": signal + timedelta(days=2), "close": 12.0, "adj_factor": 2.0},
    ]
    df = pd.DataFrame(rows)
    out = _returns_by_code(df, signal_date=signal, horizons=(1, 3, 5))
    r = out["A"]
    # qfq: close * adj/latest；latest=2 → signal 5, t+1 11, t+2 12
    assert abs(r["return_1"] - (11.0 / 5.0 - 1.0)) < 1e-9
    assert r["return_3"] is None
    assert r["return_5"] is None
