"""在网络不通时，往 daily_kline 塞一批合成 K 线，用于跑通 feature/quality/select 冒烟。

行为：
- 取 stock_pool_member(HS300) 前 20 只股票
- 从 2025-01-01 到 2026-07-14 生成合成日线（几何布朗运动）
- upsert 到 daily_kline

真实数据回来后跑 `qs update kline` 会覆盖这些 mock 数据（upsert）。
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from quant_system.data.repository import build_repositories
from quant_system.infra import trading_calendar as tc
from quant_system.infra.db import session_scope
from quant_system.infra.logger import setup_logging


def gen_kline(code: str, start: date, end: date, seed: int) -> list[dict]:
    days = tc.trading_days_between(start, end)
    if not days:
        return []

    rng = np.random.default_rng(seed)
    n = len(days)
    # 几何布朗运动
    mu = 0.0002
    sigma = 0.02
    log_returns = rng.normal(mu, sigma, size=n)
    prices = 10 * np.exp(np.cumsum(log_returns))
    prices = np.round(prices, 2)

    records = []
    prev_close = prices[0]
    for i, d in enumerate(days):
        close = float(prices[i])
        # 日内 open/high/low 模拟
        open_ = float(round(prev_close * (1 + rng.normal(0, 0.003)), 2))
        high = float(round(max(open_, close) * (1 + abs(rng.normal(0, 0.006))), 2))
        low = float(round(min(open_, close) * (1 - abs(rng.normal(0, 0.006))), 2))
        volume = int(rng.integers(1_000_000, 20_000_000))
        amount = float(round(volume * (open_ + close) / 2, 2))
        pct = float(round((close - prev_close) / prev_close * 100, 4)) if prev_close else 0.0
        turnover = float(round(abs(rng.normal(2.0, 1.0)), 4))

        records.append({
            "code": code,
            "trade_date": d,
            "open": Decimal(str(open_)),
            "high": Decimal(str(high)),
            "low": Decimal(str(low)),
            "close": Decimal(str(close)),
            "pre_close": Decimal(str(round(prev_close, 4))),
            "volume": volume,
            "amount": Decimal(str(amount)),
            "turnover_rate": Decimal(str(turnover)),
            "pct_change": Decimal(str(pct)),
            "adj_factor": Decimal("1.0"),
        })
        prev_close = close
    return records


def main() -> None:
    setup_logging()
    start = date(2025, 1, 1)
    end = date(2026, 7, 14)

    with session_scope() as session:
        repos = build_repositories(session)
        members = repos.stock.list_pool_members("HS300")[:20]
        print(f"→ 前 20 只 HS300 股票")
        total_inserted = 0
        for i, code in enumerate(members):
            records = gen_kline(code, start, end, seed=hash(code) & 0xFFFFFFFF)
            n = repos.kline.upsert_klines(records)
            repos.sync_state.set_cursor("akshare.kline", code, end)
            total_inserted += n
            print(f"  {code}: {n} rows")
        print(f"总计 upsert {total_inserted} 条")


if __name__ == "__main__":
    main()
