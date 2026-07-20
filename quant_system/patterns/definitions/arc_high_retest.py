from __future__ import annotations

from quant_system.patterns.definition import (
    ContextSpec,
    HardConstraints,
    PatternDefinition,
    RelationSpec,
    Stage,
    TargetValue,
    WindowConstraint,
)


def build_arc_high_retest_definition() -> PatternDefinition:
    """弧形突破回踩后确认上涨。

    结构（信号日 = 买点日 = bounce 末日）：
      decline（弧形下跌，左高→谷底）
        → rally（弧形拉升，末日首次收盘站上左高）
        → retest（回踩不深破前高、收在前高附近）
        → bounce（回踩后 1~2 日上涨；末日必须阳线，作为买点）

    核心硬约束：
      1. 拉升末日首次收盘 >= 下跌段最高价
      2. 回踩最低价相对前高 >= -1%，收盘贴前高
      3. 回踩后 1~2 日全部阳线且上涨，买点日收在前高之上附近
    """
    # ------------------------------------------------------------------
    # Stage 1: decline —— 从左高弧形下行到谷底
    # ------------------------------------------------------------------
    decline = Stage(
        name="decline",
        role="down",
        window=WindowConstraint(min_length=3, max_length=10),
        targets={
            "total_return": TargetValue(
                ideal=-0.06,
                tolerance=0.08,
                weight=0.18,
                mode="one_sided_low",
                hard_max=-0.03,
            ),
            "slope": TargetValue(
                ideal=-0.008,
                tolerance=0.012,
                weight=0.16,
                mode="one_sided_low",
                hard_max=-0.004,
            ),
            "peak_day": TargetValue(
                ideal=0.15,
                tolerance=0.35,
                weight=0.14,
                mode="one_sided_low",
                hard_max=0.45,
            ),
            "trough_day": TargetValue(
                ideal=0.85,
                tolerance=0.35,
                weight=0.16,
                mode="one_sided_high",
                hard_min=0.45,
            ),
            "down_day_ratio": TargetValue(
                ideal=0.7,
                tolerance=0.35,
                weight=0.12,
                mode="one_sided_high",
                hard_min=0.4,
            ),
            "amplitude": TargetValue(
                ideal=0.08,
                tolerance=0.07,
                weight=0.12,
                mode="two_sided",
                hard_min=0.025,
                hard_max=0.22,
            ),
            "linearity": TargetValue(
                ideal=0.55,
                tolerance=0.40,
                weight=0.12,
                mode="one_sided_high",
            ),
        },
    )

    # ------------------------------------------------------------------
    # Stage 2: rally —— 从谷底拉升，末日首次收盘突破左高
    # ------------------------------------------------------------------
    rally = Stage(
        name="rally",
        role="up",
        window=WindowConstraint(min_length=3, max_length=8),
        targets={
            "total_return": TargetValue(
                ideal=0.07,
                tolerance=0.08,
                weight=0.16,
                mode="one_sided_high",
                hard_min=0.02,
            ),
            "slope": TargetValue(
                ideal=0.01,
                tolerance=0.015,
                weight=0.14,
                mode="one_sided_high",
                hard_min=0.001,
            ),
            "up_day_ratio": TargetValue(
                ideal=0.75,
                tolerance=0.35,
                weight=0.12,
                mode="one_sided_high",
                hard_min=0.45,
            ),
            "peak_day": TargetValue(
                ideal=0.9,
                tolerance=0.35,
                weight=0.10,
                mode="one_sided_high",
                hard_min=0.4,
            ),
            "bull_ratio": TargetValue(
                ideal=0.75,
                tolerance=0.35,
                weight=0.08,
                mode="one_sided_high",
            ),
            "close_strength": TargetValue(
                ideal=0.7,
                tolerance=0.35,
                weight=0.08,
                mode="one_sided_high",
            ),
            "return_last": TargetValue(
                ideal=0.025,
                tolerance=0.035,
                weight=0.12,
                mode="one_sided_high",
                hard_min=0.0,
            ),
            "volume_last_vs_avg": TargetValue(
                ideal=1.25,
                tolerance=0.8,
                weight=0.10,
                mode="one_sided_high",
            ),
            "body_ratio": TargetValue(
                ideal=0.55,
                tolerance=0.35,
                weight=0.10,
                mode="one_sided_high",
            ),
        },
    )

    # ------------------------------------------------------------------
    # Stage 3: retest —— 破高后回踩（不再是买点，只确认不破）
    # ------------------------------------------------------------------
    retest = Stage(
        name="retest",
        role="down",
        window=WindowConstraint(min_length=1, max_length=1),
        targets={
            "total_return": TargetValue(
                ideal=-0.012,
                tolerance=0.03,
                weight=0.22,
                mode="two_sided",
                hard_min=-0.055,
                hard_max=0.018,
            ),
            "close_strength": TargetValue(
                ideal=0.55,
                tolerance=0.40,
                weight=0.16,
                mode="one_sided_high",
                hard_min=0.2,
            ),
            "lower_shadow_ratio": TargetValue(
                ideal=0.28,
                tolerance=0.30,
                weight=0.14,
                mode="two_sided",
            ),
            "upper_shadow_ratio": TargetValue(
                ideal=0.18,
                tolerance=0.25,
                weight=0.12,
                mode="one_sided_low",
                hard_max=0.55,
            ),
            "body_ratio": TargetValue(
                ideal=0.40,
                tolerance=0.35,
                weight=0.12,
                mode="two_sided",
            ),
            "volume_last_vs_avg": TargetValue(
                ideal=0.85,
                tolerance=0.55,
                weight=0.12,
                mode="one_sided_low",
            ),
            "gap_open": TargetValue(
                ideal=-0.005,
                tolerance=0.025,
                weight=0.12,
                mode="two_sided",
                hard_min=-0.04,
                hard_max=0.025,
            ),
        },
    )

    # ------------------------------------------------------------------
    # Stage 4: bounce —— 回踩不破后 1~2 日上涨；末日阳线 = 买点
    # ------------------------------------------------------------------
    bounce = Stage(
        name="bounce",
        role="up",
        window=WindowConstraint(min_length=1, max_length=2),
        targets={
            # 硬：段内全是阳线（含买点日）
            "bull_ratio": TargetValue(
                ideal=1.0,
                tolerance=0.01,
                weight=0.22,
                mode="one_sided_high",
                hard_min=1.0,
            ),
            # 硬：1~2 日收盘相对前收都上涨
            "up_day_ratio": TargetValue(
                ideal=1.0,
                tolerance=0.01,
                weight=0.18,
                mode="one_sided_high",
                hard_min=1.0,
            ),
            "consecutive_up_ratio": TargetValue(
                ideal=1.0,
                tolerance=0.01,
                weight=0.14,
                mode="one_sided_high",
                hard_min=1.0,
            ),
            "total_return": TargetValue(
                ideal=0.025,
                tolerance=0.03,
                weight=0.16,
                mode="one_sided_high",
                hard_min=0.005,
            ),
            # 买点日（末日）实体阳线偏强
            "return_last": TargetValue(
                ideal=0.015,
                tolerance=0.025,
                weight=0.12,
                mode="one_sided_high",
                hard_min=0.0,
            ),
            "close_strength": TargetValue(
                ideal=0.7,
                tolerance=0.35,
                weight=0.10,
                mode="one_sided_high",
                hard_min=0.35,
            ),
            "body_ratio": TargetValue(
                ideal=0.55,
                tolerance=0.35,
                weight=0.08,
                mode="one_sided_high",
                hard_min=0.25,
            ),
        },
    )

    relations = [
        RelationSpec(
            name="breakout_distance",
            attach_to_stage="rally",
            stage_map={"platform": "decline", "breakout": "rally"},
            target=TargetValue(
                ideal=0.015,
                tolerance=0.035,
                weight=0.28,
                mode="one_sided_high",
                hard_min=0.0,
            ),
        ),
        RelationSpec(
            name="breakout_on_last_day",
            attach_to_stage="rally",
            stage_map={"platform": "decline", "breakout": "rally"},
            target=TargetValue(
                ideal=1.0,
                tolerance=0.01,
                weight=0.32,
                mode="one_sided_high",
                hard_min=1.0,
            ),
        ),
        RelationSpec(
            name="volume_vs_platform",
            attach_to_stage="rally",
            stage_map={"platform": "decline", "breakout": "rally"},
            target=TargetValue(
                ideal=1.3,
                tolerance=0.9,
                weight=0.20,
                mode="one_sided_high",
            ),
        ),
        RelationSpec(
            name="close_vs_platform_mid",
            attach_to_stage="rally",
            stage_map={"platform": "decline", "breakout": "rally"},
            target=TargetValue(
                ideal=0.04,
                tolerance=0.08,
                weight=0.20,
                mode="one_sided_high",
            ),
        ),
        # 回踩收盘贴前高
        RelationSpec(
            name="breakout_distance",
            attach_to_stage="retest",
            stage_map={"platform": "decline", "breakout": "retest"},
            target=TargetValue(
                ideal=0.0,
                tolerance=0.022,
                weight=0.38,
                mode="two_sided",
                hard_min=-0.02,
                hard_max=0.03,
            ),
        ),
        RelationSpec(
            name="low_vs_prior_high",
            attach_to_stage="retest",
            stage_map={"platform": "decline", "breakout": "retest"},
            target=TargetValue(
                ideal=0.005,
                tolerance=0.02,
                weight=0.42,
                mode="one_sided_high",
                hard_min=-0.01,
            ),
        ),
        RelationSpec(
            name="volume_vs_platform",
            attach_to_stage="retest",
            stage_map={"platform": "rally", "breakout": "retest"},
            target=TargetValue(
                ideal=0.75,
                tolerance=0.55,
                weight=0.20,
                mode="one_sided_low",
            ),
        ),
        # 买点日仍站上前高附近
        RelationSpec(
            name="breakout_distance",
            attach_to_stage="bounce",
            stage_map={"platform": "decline", "breakout": "bounce"},
            target=TargetValue(
                ideal=0.01,
                tolerance=0.03,
                weight=0.45,
                mode="one_sided_high",
                hard_min=-0.005,
            ),
        ),
        RelationSpec(
            name="low_vs_prior_high",
            attach_to_stage="bounce",
            stage_map={"platform": "decline", "breakout": "bounce"},
            target=TargetValue(
                ideal=0.01,
                tolerance=0.025,
                weight=0.35,
                mode="one_sided_high",
                hard_min=-0.01,
            ),
        ),
        # 确认上涨相对回踩放量更好
        RelationSpec(
            name="volume_vs_platform",
            attach_to_stage="bounce",
            stage_map={"platform": "retest", "breakout": "bounce"},
            target=TargetValue(
                ideal=1.15,
                tolerance=0.8,
                weight=0.20,
                mode="one_sided_high",
            ),
        ),
    ]

    context_features = [
        ContextSpec(
            name="price_position",
            lookback_bars=120,
            target=TargetValue(
                ideal=0.55,
                tolerance=0.40,
                weight=1.0,
                mode="two_sided",
                hard_min=0.15,
                hard_max=0.92,
            ),
        ),
    ]

    return PatternDefinition(
        id="ARC_HIGH_RETEST",
        version="v1.3",
        display_name="弧形突破回踩",
        display_name_en="Arc High Retest",
        description=(
            "弧形下跌→拉升末日首破左高→回踩不破前高→其后1~2日阳线上涨；"
            "信号日为确认上涨末日（买点），要求当日阳线且仍站上前高附近。"
        ),
        timeline=[decline, rally, retest, bounce],
        threshold=72.0,
        stage_weights={
            "decline": 0.18,
            "rally": 0.26,
            "retest": 0.22,
            "bounce": 0.29,
            "context": 0.05,
        },
        relations=relations,
        context_features=context_features,
        history_bars=90,
        constraints=HardConstraints(
            exclude_st=True,
            min_list_days=90,
            min_amount=None,
            min_market_cap=None,
        ),
    )
