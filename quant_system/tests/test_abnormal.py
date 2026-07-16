"""Abnormal Pattern Engine 单测。"""
from __future__ import annotations

import pandas as pd

from quant_system.abnormal.patterns.range_breakout import RangeBreakoutPattern
from quant_system.abnormal.scan import run_pattern_scan
from quant_system.abnormal.score_utils import anchor_score, volume_ratio_score


def test_anchor_log_volume():
    assert abs(volume_ratio_score(2.0) - 60.0) < 1e-6
    assert abs(volume_ratio_score(5.0) - 100.0) < 1e-6
    assert 60 < volume_ratio_score(3.0) < 100


def test_scan_keeps_best_level_and_order():
    """L1 命中排在 L2 之前；同一 code 只保留最严档。"""
    rows = []
    # L1 候选
    rows.append({
        "code": "000001.SZ", "amplitude_20d": 8.0, "volume_ratio": 3.5,
        "break_high_20d": True, "return_1d": 6.0, "amount": 4e8,
        "break_distance_20d": 0.8, "relative_return": 3.0,
        "is_yang": True, "is_one_word": False, "is_st": False,
    })
    # 仅 L3 能过
    rows.append({
        "code": "000002.SZ", "amplitude_20d": 14.0, "volume_ratio": 2.1,
        "break_high_20d": True, "return_1d": 3.2, "amount": 2.1e8,
        "break_distance_20d": 0.2, "relative_return": 1.0,
        "is_yang": True, "is_one_word": False, "is_st": False,
    })
    # 一字板应被公共过滤剔除
    rows.append({
        "code": "000003.SZ", "amplitude_20d": 5.0, "volume_ratio": 4.0,
        "break_high_20d": True, "return_1d": 9.0, "amount": 5e8,
        "break_distance_20d": 1.0, "relative_return": 4.0,
        "is_yang": True, "is_one_word": True, "is_st": False,
    })
    df = pd.DataFrame(rows)
    hits = run_pattern_scan(RangeBreakoutPattern(), df)
    codes = [h.code for h in hits]
    assert "000003.SZ" not in codes
    assert codes[0] == "000001.SZ"
    assert hits[0].scan_level == 1
    assert hits[1].code == "000002.SZ"
    assert hits[1].scan_level == 3


def test_scan_level_monotonic_subset():
    """更严档命中应 ⊆ 更松档（在构造数据上）。"""
    p = RangeBreakoutPattern()
    # 一只刚好卡在 L2
    df = pd.DataFrame([{
        "code": "600000.SH", "amplitude_20d": 11.0, "volume_ratio": 2.6,
        "break_high_20d": True, "return_1d": 4.5, "amount": 2.6e8,
        "break_distance_20d": 0.4, "relative_return": 2.0,
        "is_yang": True, "is_one_word": False, "is_st": False,
    }])
    from quant_system.abnormal.scan import apply_common_excludes
    base = apply_common_excludes(df)
    l1 = set(p.filter(base, p.scan_levels[0])["code"])
    l2 = set(p.filter(base, p.scan_levels[1])["code"])
    l3 = set(p.filter(base, p.scan_levels[2])["code"])
    assert l1 <= l2 <= l3
    assert "600000.SH" in l2 and "600000.SH" not in l1


def test_anchor_score_edges():
    assert anchor_score(0.0, [(0.0, 0.0), (1.0, 100.0)]) == 0.0
    assert anchor_score(1.0, [(0.0, 0.0), (1.0, 100.0)]) == 100.0
    assert abs(anchor_score(0.5, [(0.0, 0.0), (1.0, 100.0)]) - 50.0) < 1e-6
