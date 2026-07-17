from __future__ import annotations

from dataclasses import replace
from datetime import date

import pandas as pd

from quant_system.patterns.definition import CONTEXT_STAGE, ContextSpec, TargetValue
from quant_system.patterns.definitions.range_breakout import build_range_breakout_definition
from quant_system.patterns.evaluator import LinearToleranceEvaluator
from quant_system.patterns.features.catalog import (
    extract_close_vs_window_high,
    extract_consecutive_up_ratio,
    extract_gap_open,
    extract_peak_day,
    extract_price_percentile,
    extract_price_position,
    extract_stall_score,
    extract_total_return,
    extract_volume_acceleration,
    list_features,
)
from quant_system.patterns.matcher import GenericPatternMatcher
from quant_system.patterns.result import FeatureValue


def _make_series(
    *,
    platform_n: int = 20,
    breakout_n: int = 2,
    platform_base: float = 10.0,
    break_up: float = 0.03,
    history_n: int = 240,
    history_base: float = 16.0,
) -> pd.DataFrame:
    rows = []
    # 前置更高位历史，使当前平台落在一年相对低位（context 特征用）
    price = history_base
    for i in range(history_n):
        # 缓慢下行到平台附近
        target = history_base + (platform_base - history_base) * (i + 1) / max(history_n, 1)
        o = price
        c = o * 0.7 + target * 0.3
        h = max(o, c) * 1.01
        l = min(o, c) * 0.99
        rows.append(
            {
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1_200_000,
            }
        )
        price = c

    price = platform_base
    for i in range(platform_n):
        o = price
        c = price * (1.0 + (0.002 if i % 2 == 0 else -0.002))
        h = max(o, c) * 1.005
        l = min(o, c) * 0.995
        rows.append(
            {
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1_000_000 * (0.8 if i > platform_n // 2 else 1.2),
            }
        )
        price = c

    plat_high = max(r["high"] for r in rows[-platform_n:])
    price = plat_high * (1.0 + break_up)
    for j in range(breakout_n):
        o = price * 0.99
        c = price * (1.0 + 0.02)
        h = c * 1.01
        l = o * 0.995
        rows.append(
            {
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 2_000_000 * (1.0 + 0.3 * j),
            }
        )
        price = c

    start = date(2025, 6, 1)
    for idx, row in enumerate(rows):
        row["trade_date"] = date.fromordinal(start.toordinal() + idx)
    return pd.DataFrame(rows)


def test_evaluator_modes() -> None:
    ev = LinearToleranceEvaluator()
    high = ev.evaluate(
        FeatureValue("x", 3.0),
        TargetValue(ideal=2.0, tolerance=1.0, mode="one_sided_high"),
    )
    assert high.similarity == 100.0
    low = ev.evaluate(
        FeatureValue("y", 0.05),
        TargetValue(ideal=0.10, tolerance=0.05, mode="one_sided_low"),
    )
    assert low.similarity == 100.0
    two = ev.evaluate(
        FeatureValue("z", 0.12),
        TargetValue(ideal=0.10, tolerance=0.05, mode="two_sided"),
    )
    assert 50.0 < two.similarity < 70.0


def test_short_stage_features_distinguish_stall() -> None:
    # 连涨连放量
    strong = pd.DataFrame(
        [
            {"open": 10.0, "high": 10.5, "low": 9.9, "close": 10.4, "volume": 1_000_000},
            {"open": 10.4, "high": 11.0, "low": 10.3, "close": 10.9, "volume": 1_500_000},
        ]
    )
    # 首日冲、次日滞
    stall = pd.DataFrame(
        [
            {"open": 10.0, "high": 10.8, "low": 9.9, "close": 10.7, "volume": 2_000_000},
            {"open": 10.7, "high": 10.85, "low": 10.6, "close": 10.72, "volume": 900_000},
        ]
    )
    assert extract_consecutive_up_ratio(strong).value == 1.0
    assert extract_stall_score(strong).value is not None
    assert extract_stall_score(strong).value < extract_stall_score(stall).value
    assert extract_volume_acceleration(strong).value > 1.0
    assert extract_volume_acceleration(stall).value < 1.0


def test_total_return_single_day_uses_prior_close() -> None:
    df = pd.DataFrame(
        [{"open": 6.7, "high": 6.9, "low": 6.6, "close": 6.84, "volume": 1}]
    )
    df.attrs["prior_close"] = 6.55
    fv = extract_total_return(df)
    assert fv.value is not None
    assert abs(fv.value - (6.84 / 6.55 - 1.0)) < 1e-9


def test_gap_open_uses_prior_close() -> None:
    df = pd.DataFrame(
        [{"open": 6.7, "high": 6.9, "low": 6.6, "close": 6.84, "volume": 1}]
    )
    df.attrs["prior_close"] = 6.55
    fv = extract_gap_open(df)
    assert fv.value is not None
    assert abs(fv.value - (6.7 / 6.55 - 1.0)) < 1e-9


def test_context_price_position_and_percentile() -> None:
    # 高位区间后落到底部
    rows = [{"open": 20, "high": 21, "low": 19, "close": 20, "volume": 1}] * 50
    rows += [{"open": 10, "high": 10.5, "low": 9.5, "close": 10.0, "volume": 1}] * 5
    df = pd.DataFrame(rows)
    pos = extract_price_position(df).value
    pct = extract_price_percentile(df).value
    assert pos is not None and pos < 0.25
    assert pct is not None and pct < 0.25


def test_platform_geometry_rejects_peak_then_dump() -> None:
    # 先冲高再阴跌：高点在前、收盘远离窗内高点
    rows = []
    price = 10.0
    for i in range(10):
        if i < 3:
            price *= 1.04
        else:
            price *= 0.97
        rows.append(
            {
                "open": price / 1.01,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "volume": 1_000_000,
            }
        )
    df = pd.DataFrame(rows)
    assert extract_peak_day(df).value is not None
    assert extract_peak_day(df).value < 0.4
    assert extract_close_vs_window_high(df).value is not None
    assert extract_close_vs_window_high(df).value < -0.08


def test_feature_catalog_has_short_stage_set() -> None:
    names = set(list_features())
    required = {
        "return_first", "return_last", "return_acceleration",
        "up_day_ratio", "consecutive_up_ratio", "stall_score",
        "volume_up_ratio", "consecutive_volume_up_ratio",
        "volume_acceleration", "volume_last_vs_avg", "volume_climax_day",
        "upper_shadow_ratio", "lower_shadow_ratio", "close_strength",
        "break_hold_ratio", "close_vs_platform_mid",
        "price_position", "price_percentile", "close_vs_high",
        "linearity", "gap_open",
        "close_vs_window_high", "peak_day",
    }
    assert required.issubset(names)


def test_platform_targets_are_orthogonal_set() -> None:
    definition = build_range_breakout_definition()
    platform = definition.timeline[0]
    assert set(platform.targets) == {
        "amplitude", "slope", "linearity",
        "close_vs_window_high", "peak_day", "volume_shrink_ratio",
    }
    assert abs(sum(t.weight for t in platform.targets.values()) - 1.0) < 1e-9


def test_definition_required_history_includes_context_lookback() -> None:
    definition = build_range_breakout_definition()
    assert definition.required_history_bars() >= 252
    assert any(c.name == "price_position" for c in definition.context_features)


def test_generic_matcher_finds_range_breakout() -> None:
    definition = replace(build_range_breakout_definition(), threshold=50.0)
    series = _make_series(platform_n=10, breakout_n=2, break_up=0.03)
    trade_date = series["trade_date"].iloc[-1]
    result = GenericPatternMatcher().match(
        "000001.SZ",
        trade_date,
        series,
        definition,
        meta={"is_st": False, "list_date": date(2010, 1, 1)},
        last_amount=5.0e8,
    )
    assert result.similarity > 50
    assert definition.timeline[0].window.min_length <= result.chosen_windows["platform"]
    assert result.chosen_windows["platform"] <= definition.timeline[0].window.max_length
    assert result.chosen_windows["breakout"] in {1, 2}
    assert "platform" in result.stage_similarity
    assert CONTEXT_STAGE in result.stage_similarity
    assert any("breakout_distance" in k for k in result.feature_similarity)
    assert any("price_position" in k for k in result.feature_similarity)
    assert any("stall_score" in k for k in result.feature_similarity)


def test_hard_min_max_on_target_value() -> None:
    t = TargetValue(ideal=0.0, tolerance=0.01, hard_min=-0.01, hard_max=0.005)
    assert t.hard_failed(-0.01, 50.0) is False
    assert t.hard_failed(0.005, 50.0) is False
    assert t.hard_failed(-0.011, 100.0) is True
    assert t.hard_failed(0.006, 100.0) is True
    assert t.hard_failed(None, 100.0) is True


def test_context_hard_fail_skips_window_search() -> None:
    definition = replace(
        build_range_breakout_definition(),
        threshold=0.0,
        context_features=[
            ContextSpec(
                name="price_position",
                lookback_bars=50,
                target=TargetValue(
                    ideal=0.2, tolerance=0.1, weight=1.0, mode="one_sided_low",
                    hard_max=0.2,
                ),
            ),
        ],
    )
    # 全程抬升到高位 → price_position 高 → hard fail
    series = _make_series(
        platform_n=8, breakout_n=2, history_n=60, history_base=8.0, platform_base=12.0,
    )
    trade_date = series["trade_date"].iloc[-1]
    result = GenericPatternMatcher().match(
        "000001.SZ",
        trade_date,
        series,
        definition,
        meta={"is_st": False, "list_date": date(2010, 1, 1)},
        last_amount=5.0e8,
    )
    assert result.matched is False
    assert any("price_position" in x for x in result.hard_failed)


def test_hard_target_blocks_match_even_if_score_high() -> None:
    # 去掉 context hard，单独验证突破段 bull_ratio hard
    definition = replace(
        build_range_breakout_definition(),
        threshold=0.0,
        context_features=[],
    )
    # 突破段第二天收阴：bull_ratio < 1，hard 应直接否决
    series = _make_series(platform_n=10, breakout_n=2, break_up=0.03)
    # 把最后一天改成阴线
    series.loc[series.index[-1], "open"] = 12.0
    series.loc[series.index[-1], "close"] = 11.5
    series.loc[series.index[-1], "high"] = 12.1
    series.loc[series.index[-1], "low"] = 11.4
    trade_date = series["trade_date"].iloc[-1]
    result = GenericPatternMatcher().match(
        "000001.SZ",
        trade_date,
        series,
        definition,
        meta={"is_st": False, "list_date": date(2010, 1, 1)},
        last_amount=5.0e8,
    )
    assert result.matched is False
    assert any("bull_ratio" in x for x in result.hard_failed)


def test_window_search_prefers_better_fit() -> None:
    definition = replace(build_range_breakout_definition(), threshold=0.0)
    series = _make_series(platform_n=10, breakout_n=2, break_up=0.04)
    trade_date = series["trade_date"].iloc[-1]
    result = GenericPatternMatcher().match(
        "000001.SZ",
        trade_date,
        series,
        definition,
        meta={"is_st": False, "list_date": date(2010, 1, 1)},
        last_amount=5.0e8,
    )
    assert result.chosen_windows["breakout"] in {1, 2}
    w = definition.timeline[0].window
    assert w.min_length <= result.chosen_windows["platform"] <= w.max_length
