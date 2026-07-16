"""关系层单测：calculator（纯函数）+ returns_matrix（对齐）+ repository + service 冒烟。

全部离线：不触发 akshare / 交易日历网络调用（用 monkeypatch 替换日历）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from quant_system.database.models import (
    Base,
    DailyKline,
    StockBasic,
    StockPool,
    StockPoolMember,
)
from quant_system.relationship import returns_matrix as rm
from quant_system.relationship.calculator import LeadLagCalculator, PearsonCalculator


# ============================================================================
# calculator（纯函数，无 DB、无网络）
# ============================================================================

def _returns_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=200, freq="D")
    rng = np.random.default_rng(0)
    base = rng.normal(size=200)
    a = base + rng.normal(scale=0.02, size=200)
    b = base + rng.normal(scale=0.02, size=200)   # 与 a 高度相关
    c = rng.normal(size=200)                        # 独立
    return pd.DataFrame(
        {"000001.SZ": a, "000002.SZ": b, "600000.SH": c}, index=dates,
    )


def test_pearson_basic_pair_and_canonical_order():
    calc = PearsonCalculator()
    res = calc.compute_window(
        _returns_frame(), "FULL", None,
        min_sample=120, value_threshold=0.7, max_neighbors=200,
    )
    assert res.universe_effective == 3
    assert len(res.pairs) == 1  # 只有 a~b 达标
    p = res.pairs[0]
    assert p["code_a"] == "000001.SZ" and p["code_b"] == "000002.SZ"  # 规范 a<b
    assert p["value"] > 0.9
    assert p["sample_size"] == 200


def test_min_sample_skips_pair():
    df = _returns_frame()
    # 只保留前 50 行有效，其余置 NaN → 共同样本 < min_sample
    df.iloc[50:, :] = np.nan
    calc = PearsonCalculator()
    res = calc.compute_window(
        df, "FULL", None, min_sample=120, value_threshold=0.7, max_neighbors=200,
    )
    assert res.pairs == []
    assert res.evaluated == 0


def test_threshold_filters_low_corr():
    df = _returns_frame()
    calc = PearsonCalculator()
    high = calc.compute_window(df, "FULL", None, min_sample=120, value_threshold=0.7, max_neighbors=200)
    # 阈值抬到 0.9999 → 无对入选，但候选评估数不变
    strict = calc.compute_window(df, "FULL", None, min_sample=120, value_threshold=0.9999, max_neighbors=200)
    assert len(high.pairs) == 1
    assert strict.pairs == []
    assert strict.evaluated == high.evaluated == 3


def test_halt_reduces_common_sample():
    df = _returns_frame()
    df.loc[df.index[100:], "000002.SZ"] = np.nan  # 后 100 天停牌
    calc = PearsonCalculator()
    res = calc.compute_window(df, "FULL", None, min_sample=50, value_threshold=0.5, max_neighbors=200)
    # a~b 仍可能达标，但共同样本应为 100
    ab = [p for p in res.pairs if {p["code_a"], p["code_b"]} == {"000001.SZ", "000002.SZ"}]
    assert ab and ab[0]["sample_size"] == 100


def test_max_neighbors_cap():
    dates = pd.date_range("2024-01-01", periods=200, freq="D")
    rng = np.random.default_rng(1)
    base = rng.normal(size=200)
    cols = {f"00000{i}.SZ": base + rng.normal(scale=0.01, size=200) for i in range(1, 6)}
    df = pd.DataFrame(cols, index=dates)  # 5 只两两强相关
    calc = PearsonCalculator()
    res = calc.compute_window(df, "FULL", None, min_sample=120, value_threshold=0.7, max_neighbors=1)
    # 每只正相关邻居 ≤ 1
    pos_count: dict[str, int] = {}
    for p in res.pairs:
        pos_count[p["code_a"]] = pos_count.get(p["code_a"], 0) + 1
        pos_count[p["code_b"]] = pos_count.get(p["code_b"], 0) + 1
    assert all(v <= 1 for v in pos_count.values())
    assert res.capped > 0


# ============================================================================
# LeadLagCalculator（先后关系，纯函数）
# ============================================================================

def test_lead_lag_detects_leader():
    dates = pd.date_range("2024-01-01", periods=200, freq="D")
    rng = np.random.default_rng(3)
    a = rng.normal(size=200)                       # 领先者
    b = np.empty(200)
    b[:2] = rng.normal(size=2)
    b[2:] = a[:-2] + rng.normal(scale=0.05, size=198)  # b 滞后 a 两天
    df = pd.DataFrame({"000001.SZ": a, "000002.SZ": b}, index=dates)

    calc = LeadLagCalculator()
    pairs = calc.compute_pairs(
        df, [("000001.SZ", "000002.SZ")], days=None, max_lag=5,
        min_sample=120, value_threshold=0.5, min_lead_gain=0.0,
    )
    assert len(pairs) == 1
    p = pairs[0]
    assert p["direction"] == 2          # 000001 领先 000002 两天
    assert p["value"] > 0.9


def test_lead_lag_skips_synchronous():
    # 完全同步的两只票不应被判为领先-滞后
    df = _returns_frame()  # a~b 同期强相关，无滞后结构
    calc = LeadLagCalculator()
    pairs = calc.compute_pairs(
        df, [("000001.SZ", "000002.SZ")], days=None, max_lag=5,
        min_sample=120, value_threshold=0.5, min_lead_gain=0.03,
    )
    assert pairs == []


# ============================================================================
# returns_matrix（对齐：不同上市时间 / 停牌 → NaN；离线）
# ============================================================================

class _FakeRepo:
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def read_prices(self, codes, start, end):  # noqa: ANN001
        d = self._df[self._df["code"].isin(codes)]
        d = d[(d["trade_date"] >= start) & (d["trade_date"] <= end)]
        return d.reset_index(drop=True)


def test_returns_matrix_listing_and_halt(monkeypatch):
    d0 = date(2024, 1, 1)
    days = [d0 + timedelta(days=i) for i in range(20)]
    rows = []
    for i, d in enumerate(days):
        # X 全程有数据；第 10 天停牌（volume=0）
        rows.append({"code": "000001.SZ", "trade_date": d,
                     "close": 10.0 + i, "adj_factor": 1.0,
                     "volume": 0 if i == 10 else 1000})
        # Y 第 5 天才上市
        if i >= 5:
            rows.append({"code": "000002.SZ", "trade_date": d,
                         "close": 20.0 + i, "adj_factor": 1.0, "volume": 1000})
    fake = _FakeRepo(pd.DataFrame(rows))
    monkeypatch.setattr(rm.tc, "previous_trading_day", lambda cd, n: d0)

    mat = rm.build_returns_matrix(fake, ["000002.SZ", "000001.SZ"], days[-1], 250, use_cache=False)

    assert list(mat.columns) == ["000001.SZ", "000002.SZ"]  # 升序
    # Y 上市前（前 5 天）应为 NaN
    assert mat["000002.SZ"].iloc[:5].isna().all()
    # X 停牌日(10)与其后一日(11)收益率为 NaN（停牌价被剔除）
    assert pd.isna(mat["000001.SZ"].iloc[10])
    assert pd.isna(mat["000001.SZ"].iloc[11])


# ============================================================================
# repository + service（临时内存 SQLite，离线）
# ============================================================================

@pytest.fixture
def sess():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    s = factory()
    try:
        yield s
        s.commit()
    finally:
        s.close()
        engine.dispose()


def _seed_stock(sess, code, industry="IND1"):
    sess.add(StockBasic(
        code=code, name=f"名{code[:6]}", exchange="SZ",
        industry_code=industry, industry_name=industry,
        is_st=False, updated_at=datetime.utcnow(),
    ))


def test_repository_roundtrip(sess):
    from quant_system.data.repository import SQLARelationRepository

    for c in ("000001.SZ", "000002.SZ", "600000.SH"):
        _seed_stock(sess, c, industry="A" if c.startswith("0000") else "B")
    sess.flush()

    repo = SQLARelationRepository(sess)
    recs = [
        {"relation_type": "PEARSON", "window": "W250",
         "stock_code_a": "000001.SZ", "stock_code_b": "000002.SZ",
         "relation_value": 0.95, "sample_size": 240, "is_same_industry": True,
         "calc_date": date(2026, 7, 15)},
        {"relation_type": "PEARSON", "window": "W250",
         "stock_code_a": "000001.SZ", "stock_code_b": "600000.SH",
         "relation_value": -0.82, "sample_size": 200, "is_same_industry": False,
         "calc_date": date(2026, 7, 15)},
    ]
    assert repo.bulk_insert(recs) == 2

    # neighbors 合并 a/b 两侧
    nb = repo.neighbors("000002.SZ", window="W250")
    assert len(nb) == 1 and nb[0]["peer"] == "000001.SZ"
    nb1 = repo.neighbors("000001.SZ", window="W250")
    assert {r["peer"] for r in nb1} == {"000002.SZ", "600000.SH"}
    neg = repo.neighbors("000001.SZ", window="W250", sign=-1)
    assert len(neg) == 1 and neg[0]["peer"] == "600000.SH"

    # get_pair 规范化顺序
    pair = repo.get_pair("600000.SH", "000001.SZ", window="W250")
    assert pair and abs(pair["relation_value"] + 0.82) < 1e-6

    # list_strong 负相关
    strong_neg = repo.list_strong(window="W250", sign=-1, min_abs=0.8)
    assert len(strong_neg) == 1

    # replace_snapshot 清旧
    assert repo.replace_snapshot("PEARSON", "W250") == 2
    assert repo.neighbors("000001.SZ", window="W250") == []


def test_service_build_and_idempotency(sess, monkeypatch):
    from quant_system.data.repository import build_repositories
    from quant_system.relationship import service

    # 宇宙：4 只，两两一对强相关
    codes = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"]
    for c in codes:
        _seed_stock(sess, c)
    sess.add(StockPool(code="TESTPOOL", name="t", pool_type="CUSTOM",
                       is_active=True, updated_at=datetime.utcnow()))
    d0 = date(2024, 1, 1)
    days = [d0 + timedelta(days=i) for i in range(300)]
    for c in codes:
        sess.add(StockPoolMember(pool_code="TESTPOOL", code=c, in_date=d0, out_date=None))

    rng = np.random.default_rng(7)
    base_a = np.cumsum(rng.normal(size=300)) + 100
    base_b = np.cumsum(rng.normal(size=300)) + 100
    price = {
        "000001.SZ": base_a + rng.normal(scale=0.05, size=300),
        "000002.SZ": base_a + rng.normal(scale=0.05, size=300),   # ~ 000001
        "000003.SZ": base_b + rng.normal(scale=0.05, size=300),
        "000004.SZ": base_b + rng.normal(scale=0.05, size=300),   # ~ 000003
    }
    now = datetime.utcnow()
    for c in codes:
        prev = None
        for i, d in enumerate(days):
            px = float(price[c][i]) + 50
            sess.add(DailyKline(
                code=c, trade_date=d, open=px, high=px, low=px, close=px,
                pre_close=px if prev is None else prev, volume=10000,
                amount=px * 10000, adj_factor=1.0, created_at=now,
            ))
            prev = px
    sess.flush()

    monkeypatch.setattr(service.build_returns_matrix.__globals__["tc"],
                        "previous_trading_day", lambda cd, n: d0)

    repos = build_repositories(sess)
    report = service.build_relationships(
        repos, calc_date=days[-1], windows=["W250"], pool_code="TESTPOOL",
        board_filter="ALL", min_sample=120, value_threshold=0.5, max_neighbors=50,
        use_cache=False,
    )
    assert report.universe_size == 4
    assert report.pair_written_total >= 2  # 至少两对强相关
    assert not report.skipped

    stats = repos.relation.snapshot_stats()
    assert stats["windows"][0]["rows"] == report.pair_written_total

    # 幂等：再次跑（非 force）→ 跳过
    again = service.build_relationships(
        repos, calc_date=days[-1], windows=["W250"], pool_code="TESTPOOL",
        board_filter="ALL", min_sample=120, value_threshold=0.5, max_neighbors=50,
        use_cache=False,
    )
    assert again.skipped
