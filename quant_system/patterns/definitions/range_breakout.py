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


def build_range_breakout_definition() -> PatternDefinition:
    """横盘突破 Definition。

    结构：
      platform（横盘段）→ breakout（突破段）
      + 跨段 RelationFeature
      + ContextSpec（股票级价位，按 lookback 对全历史算一次）

    TargetValue 通用语义：
      ideal      理想值（小数比例，0.08=8%）
      tolerance  偏离尺度；|actual-ideal|=tolerance 时该特征 similarity≈0
      weight     在所属 Stage（或 attach 的 Stage）内聚合权重
      mode
        two_sided       离 ideal 越近越好
        one_sided_high  >= ideal 不罚，低于才扣分（越大越好）
        one_sided_low   <= ideal 不罚，高于才扣分（越小越好）
      hard_min/hard_max  特征值硬约束（优先）：如 hard_min=-0.01, hard_max=0.005
      hard + hard_min_similarity  旧版按相似度门槛（不推荐）
    """
    # ------------------------------------------------------------------
    # Stage 1: platform —— 突破前的横盘整理（正交几何 + 量能）
    #
    # 横盘 = 窄箱体 + 近水平漂移 + 路径近似直线货架
    #       + 收盘未深砸破窗口高点 + 高点不落在段首倾销区
    #       + 后段相对缩量
    #
    # 维度拆分（避免重复）：
    #   amplitude              箱体高度（多大）
    #   slope                  漂移方向（往哪倾斜）
    #   linearity              路径是否像一条线（形纯不纯）
    #   close_vs_window_high   收盘相对窗内高点（有没有冲高回落砸下去）
    #   peak_day               高点时间位置（峰在前还是在中后）
    #   volume_shrink_ratio    唯一量能维（后半/前半均量）
    #
    # 已去掉：volatility（与 amplitude 重叠）、bull_ratio/body_ratio（与 slope 重叠，留给突破段）
    # ------------------------------------------------------------------
    platform = Stage(
        name="platform",
        role="range",
        window=WindowConstraint(min_length=4, max_length=10),
        targets={
            # 箱体高度：(high_max - low_min) / low_min
            "amplitude": TargetValue(
                ideal=0.08, tolerance=0.06, weight=0.18, mode="one_sided_low",
                hard_max=0.15,
            ),
            # 漂移：拟合斜率/均价；硬区间约每天 -1.0% ~ +0.5%
            "slope": TargetValue(
                ideal=-0.0025, tolerance=0.01, weight=0.22, mode="two_sided",
                hard_min=-0.01, hard_max=0.005,
            ),
            # 形纯度：直线拟合 R²；货架状横盘应较高
            "linearity": TargetValue(
                ideal=0.85, tolerance=0.30, weight=0.18, mode="one_sided_high",
            ),
            # 相对窗内高点：close_last/high_max - 1；打掉“长窗吃进前高再阴跌”
            "close_vs_window_high": TargetValue(
                ideal=-0.02, tolerance=0.06, weight=0.18, mode="one_sided_high",
                hard_min=-0.08,
            ),
            # 高点位置 [0,1]；禁止高点落在最前段（冲高后单边砸的典型结构）
            "peak_day": TargetValue(
                ideal=0.45, tolerance=0.40, weight=0.12, mode="one_sided_high",
                hard_min=0.15,
            ),
            # 量能：后半均量/前半均量；横盘末期偏缩量
            "volume_shrink_ratio": TargetValue(
                ideal=0.80, tolerance=0.35, weight=0.12, mode="one_sided_low",
            ),
        },
    )

    # ------------------------------------------------------------------
    # Stage 2: breakout —— 突破后的短上涨段（日序特征为主）
    # ------------------------------------------------------------------
    breakout = Stage(
        name="breakout",
        role="up",
        # 只看最近 1~2 个交易日的突破表现
        window=WindowConstraint(min_length=1, max_length=1),
        targets={
            # ---------- 段收益与 K 线质量 ----------
            # total_return：多日=段末/段首-1；单日=当日收盘/前收-1
            # 理想约 4%；越高越好
            "total_return": TargetValue(
                ideal=0.04, tolerance=0.05, weight=0.12, mode="one_sided_high",
            ),
            # gap_open = 段首开盘 / 前收 - 1
            # 理想约 2%+ 跳高开；异动日跳空高开加分
            "gap_open": TargetValue(
                ideal=0.02, tolerance=0.03, weight=0.12, mode="one_sided_high",
            ),
            # bull_ratio = 阳线天数占比（close > open）
            # 硬约束：必须全是阳线（bull_ratio >= 1.0）
            "bull_ratio": TargetValue(
                ideal=1.0, tolerance=0.01, weight=0.05, mode="one_sided_high",
                hard_min=1.0,
            ),
            # body_ratio = 实体占当日振幅比例的均值
            # 理想实体主导（约 60%+），减少长影线骗线
            "body_ratio": TargetValue(
                ideal=0.60, tolerance=0.30, weight=0.05, mode="one_sided_high",
            ),
            # close_strength = mean((close - low) / (high - low))
            # 理想收在当日振幅偏上沿（约 0.75）；越低说明收盘软弱
            "close_strength": TargetValue(
                ideal=0.75, tolerance=0.35, weight=0.06, mode="one_sided_high",
            ),
            # upper_shadow_ratio = mean((high - max(open,close)) / (high - low))
            # 理想上影较短（约 15%）；上影过大常见于冲高回落/滞涨
            "upper_shadow_ratio": TargetValue(
                ideal=0.15, tolerance=0.25, weight=0.05, mode="one_sided_low",
            ),

            # ---------- 价格路径：连涨 / 不滞涨 ----------
            # up_day_ratio = 上涨日占比
            #   多日：close[i] > close[i-1] 的比例；单日：close > open
            # 理想 1.0：段内交易日都在上涨
            "up_day_ratio": TargetValue(
                ideal=1.0, tolerance=0.5, weight=0.10, mode="one_sided_high",
            ),
            # consecutive_up_ratio = 从段首起连续上涨天数 / 可比较天数
            # 理想 1.0：全程连涨（区别于涨跌交错）
            "consecutive_up_ratio": TargetValue(
                ideal=1.0, tolerance=0.5, weight=0.12, mode="one_sided_high",
            ),
            # return_acceleration = 尾日涨幅 - 首日涨幅
            #   单日涨幅口径：(close/open - 1)
            # 理想 >= 0：加速或至少不减速；负值偏向“首日冲、次日弱”
            "return_acceleration": TargetValue(
                ideal=0.0, tolerance=0.03, weight=0.08, mode="one_sided_high",
            ),
            # stall_score = max(0, 首日涨幅 - 尾日涨幅) / |首日涨幅|
            # 理想 0：无滞涨；越大越像“第一天猛涨、后面跟不上”
            "stall_score": TargetValue(
                ideal=0.0, tolerance=0.8, weight=0.10, mode="one_sided_low",
            ),
            # return_last = 尾日 (close/open - 1)
            # 理想尾日仍有约 2%+ 涨幅，避免最后一天走弱
            "return_last": TargetValue(
                ideal=0.02, tolerance=0.03, weight=0.06, mode="one_sided_high",
            ),

            # ---------- 量能路径：连续放量 / 尾日仍有量 ----------
            # volume_up_ratio = 放量日占比（volume[i] > volume[i-1]）
            # 理想 1.0：多数日子量能在扩大
            "volume_up_ratio": TargetValue(
                ideal=1.0, tolerance=0.5, weight=0.06, mode="one_sided_high",
            ),
            # consecutive_volume_up_ratio = 从段首起连续放量天数占比
            # 理想 1.0：全程连续放量（区别于只某天突然放量）
            "consecutive_volume_up_ratio": TargetValue(
                ideal=1.0, tolerance=0.5, weight=0.08, mode="one_sided_high",
            ),
            # volume_acceleration = 尾日成交量 / 首日成交量
            # 理想约 1.2 倍：量能相对段初继续放大
            "volume_acceleration": TargetValue(
                ideal=1.2, tolerance=0.8, weight=0.06, mode="one_sided_high",
            ),
            # volume_last_vs_avg = 尾日成交量 / 段内均量
            # 理想约 1.1：最后一天量不低于段内平均
            "volume_last_vs_avg": TargetValue(
                ideal=1.1, tolerance=0.6, weight=0.04, mode="one_sided_high",
            ),
            # volume_climax_day = 最大量出现位置，归一化到 [0,1]
            #   0=首日最大量，1=尾日最大量
            # 理想靠近 1：量能高潮落在后段，而不是开头一天冲完就没了
            "volume_climax_day": TargetValue(
                ideal=1.0, tolerance=0.8, weight=0.04, mode="one_sided_high",
            ),
        },
    )

    # ------------------------------------------------------------------
    # Relations —— 跨 Stage 关系（计入 attach_to_stage 的 Stage 分数）
    # ------------------------------------------------------------------
    relations = [
        # breakout_distance = breakout.close_last / platform.high_max - 1
        # 理想收盘相对平台最高价向上突破约 2%+
        RelationSpec(
            name="breakout_distance",
            attach_to_stage="breakout",
            stage_map={"platform": "platform", "breakout": "breakout"},
            target=TargetValue(
                ideal=0.02, tolerance=0.04, weight=0.10, mode="one_sided_high",
            ),
        ),
        # volume_vs_platform = breakout.avg_volume / platform.avg_volume
        # 理想突破段均量约为平台均量的 2 倍+
        RelationSpec(
            name="volume_vs_platform",
            attach_to_stage="breakout",
            stage_map={"platform": "platform", "breakout": "breakout"},
            target=TargetValue(
                ideal=1.7, tolerance=1.0, weight=0.5, mode="one_sided_high",hard_min=1.7,
            ),
        ),
        # break_hold_ratio = 突破段中 close >= platform.high_max 的天数占比
        # 理想 1.0：突破后每天收盘都站上平台高点（降低假突破）
        RelationSpec(
            name="break_hold_ratio",
            attach_to_stage="breakout",
            stage_map={"platform": "platform", "breakout": "breakout"},
            target=TargetValue(
                ideal=1.0, tolerance=0.5, weight=0.1, mode="one_sided_high",
            ),
        ),
        # close_vs_platform_mid = (breakout.close_last - platform_mid) / platform_mid
        #   platform_mid = (platform.high_max + platform.low_min) / 2
        # 理想收盘相对平台中轴高出约 5%+，确认不只是勉强摸到上沿
        RelationSpec(
            name="close_vs_platform_mid",
            attach_to_stage="breakout",
            stage_map={"platform": "platform", "breakout": "breakout"},
            target=TargetValue(
                ideal=0.015, tolerance=0.08, weight=0.012, mode="one_sided_high",
            ),
        ),
    ]

    # ------------------------------------------------------------------
    # Context —— 股票级价位（对 lookback 历史算一次，不随窗口枚举）
    # ------------------------------------------------------------------
    context_features = [
        # price_position@252：一年高低区间位置 [0,1]
        # 硬约束：必须 <= 0.23（回溯期低位）
        ContextSpec(
            name="price_position",
            lookback_bars=252,
            target=TargetValue(
                ideal=0.23, tolerance=0.20, weight=1.0, mode="one_sided_low",
                hard_max=0.23,
            ),
        ),
    ]

    return PatternDefinition(
        id="RANGE_BREAKOUT",
        version="tl-v2.5",
        display_name="横盘突破",
        description="窄箱近水平货架后突破；平台用正交几何防冲高回落假窗，一年价位<=0.23，市值>=500亿。",
        timeline=[platform, breakout],
        # overall similarity >= 72 才算 matched
        threshold=70.0,
        # context 硬门槛为主；权重仍参与总分
        stage_weights={"platform": 0.4, "breakout": 0.6, "context": 0.10},
        relations=relations,
        context_features=context_features,
        history_bars=260,
        constraints=HardConstraints(
            # 排除 ST
            exclude_st=True,
            # 上市不足 120 天不参与
            min_list_days=120,
            # 不做绝对成交额门槛（流动性用相对量能特征表达）
            min_amount=None,
            # 总市值下限（亿元，同 stock_basic.market_cap）；改数即可，None=不限
            min_market_cap=None,
        ),
    )
