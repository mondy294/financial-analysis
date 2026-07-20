from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class StockBriefOut(BaseModel):
    code: str
    name: str
    industry_name: str | None = None
    is_st: bool = False


class StockDetailOut(BaseModel):
    code: str
    name: str
    exchange: str
    industry_code: str | None = None
    industry_name: str | None = None
    list_date: date | None = None
    is_st: bool = False
    market_cap: float | None = None  # 亿元
    float_market_cap: float | None = None
    pe_ttm: float | None = None
    pe_static: float | None = None
    pb: float | None = None
    ps_ttm: float | None = None
    valuation_date: date | None = None


class KlineBarOut(BaseModel):
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None
    pct_change: float | None = None


class FeaturePointOut(BaseModel):
    trade_date: date
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    rsi_14: float | None = None
    atr_14: float | None = None
    boll_upper: float | None = None
    boll_mid: float | None = None
    boll_lower: float | None = None
    return_1d: float | None = None
    return_5d: float | None = None
    return_20d: float | None = None
    ma_position: float | None = None
    ma_bull_arrange: bool | None = None


class SnapshotOut(BaseModel):
    code: str
    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    amount: float | None = None
    pct_change: float | None = None
    features: dict[str, float | bool | None] = {}
    # 估值（as_of=trade_date，单位：市值亿元）
    pe_ttm: float | None = None
    pe_static: float | None = None
    pb: float | None = None
    ps_ttm: float | None = None
    market_cap: float | None = None
    float_market_cap: float | None = None
    valuation_date: date | None = None


class EarningsFairAnchorOut(BaseModel):
    """近几日业绩对应的公允价锚点（详情页 K 线）。"""

    available: bool = False
    reason: str | None = None
    detail: str | None = None
    code: str = ""
    lookback_days: int = 5
    event: dict | None = None
    model_scope: str | None = None
    ref_close: float | None = None
    ref_date: str | None = None
    fair_price: float | None = None
    premium_pct: float | None = None
    implied_fair_mcap: float | None = None
    expected_return_20d: float | None = None
    price_at_expected_20d: float | None = None
    model: dict | None = None
    prediction: dict | None = None


class DisclosureItemOut(BaseModel):
    code: str
    name: str = ""
    board: str = ""
    board_label: str = ""
    category: str
    category_label: str = ""
    notice_type: str = ""
    title: str = ""
    notice_date: date
    url: str | None = None
    # 业绩 enrich：扣非净利润（字段名历史兼容 parent_np_*，语义为扣非）
    parent_np_yoy: float | None = None
    parent_np_value: float | None = None
    predict_type: str | None = None
    report_period: date | None = None
    # 单季环比（扣非口径，由累计报表差分推算）
    parent_np_sq: float | None = None
    parent_np_qoq: float | None = None
    parent_np_qoq_prev: float | None = None
    parent_np_qoq_delta: float | None = None
    # 公告日收盘 → 其后第 1/5/10 交易日、以及最新收盘（前复权）
    return_1d: float | None = None
    return_5d: float | None = None
    return_10d: float | None = None
    return_since_notice: float | None = None
    # 最新总市值（亿元，daily_valuation / stock_basic）
    market_cap: float | None = None


class DisclosuresByDateOut(BaseModel):
    start_date: date
    end_date: date
    notice_date: date | None = None  # 兼容：等于 end_date
    main_only: bool = False
    enrich_forecast: bool = False
    enrich_returns: bool = False
    total: int = 0
    counts: dict[str, int] = {}
    items: list[DisclosureItemOut] = []


class StockDisclosuresOut(BaseModel):
    """个股近期财务类公告（与披露页同源）。"""

    code: str
    name: str = ""
    start_date: date
    end_date: date
    total: int = 0
    items: list[DisclosureItemOut] = []


class ForecastFactorCoefOut(BaseModel):
    key: str
    label: str
    coef: float
    std_coef: float
    mean: float
    std: float


class ForecastFactorFormulaOut(BaseModel):
    text: str
    intercept: float
    coefs: dict[str, float] = {}
    means: dict[str, float] = {}
    stds: dict[str, float] = {}
    note: str = ""


class ForecastFactorRowOut(BaseModel):
    code: str
    name: str = ""
    notice_date: date
    predict_type: str | None = None
    report_period: date | None = None
    valuation_date: date | None = None
    pe_ttm: float
    market_cap: float
    ln_mcap: float
    parent_np_h1: float
    parent_np_annualized: float
    parent_np_yoy: float
    parent_np_yoy_pct: float
    forecast_pe: float
    forecast_ey: float
    forecast_ey_pct: float
    return_since_notice: float
    return_pct: float
    fitted_return_pct: float | None = None
    residual_pct: float | None = None


class ForecastFactorGroupsOut(BaseModel):
    up_n: int = 0
    down_n: int = 0
    flat_n: int = 0
    up_rate: float = 0.0
    down_rate: float = 0.0
    up_means: dict[str, float | None] = {}
    down_means: dict[str, float | None] = {}
    diff_down_minus_up: dict[str, float | None] = {}


class ForecastFactorAnalysisOut(BaseModel):
    start_date: date
    end_date: date
    main_only: bool = True
    candidates: int = 0
    dropped_n: int = 0
    dropped: list[dict[str, str]] = []
    drop_hint: str | None = None
    ok: bool = False
    message: str | None = None
    n: int = 0
    feature_keys: list[str] = []
    feature_labels: dict[str, str] = {}
    intercept: float | None = None
    r_squared: float | None = None
    std_intercept: float | None = None
    std_r_squared: float | None = None
    coefficients: list[ForecastFactorCoefOut] = []
    formula: ForecastFactorFormulaOut | None = None
    corr: dict[str, dict[str, float | None]] = {}
    groups: ForecastFactorGroupsOut | None = None
    rows: list[ForecastFactorRowOut] = []


class FinancialHighlightPointOut(BaseModel):
    """单期财务亮点（年报或最新季报/中报）。金额单位：元；同比/ROE 为比率。"""

    year: int
    report_period: date
    report_name: str = ""
    notice_date: date | None = None
    is_annual: bool = True
    revenue: float | None = None
    revenue_yoy: float | None = None
    parent_net_profit: float | None = None
    parent_net_profit_yoy: float | None = None
    ded_net_profit: float | None = None
    ded_net_profit_yoy: float | None = None
    roe: float | None = None
    # 报告发布时估值（as_of=notice_date，取当日或之前最近交易日）
    pe_ttm: float | None = None
    pe_static: float | None = None
    valuation_date: date | None = None


class EarningsGuidanceMetricOut(BaseModel):
    metric: str
    predict_type: str | None = None
    value_lower: float | None = None
    value_upper: float | None = None
    value_mid: float | None = None
    yoy_lower: float | None = None
    yoy_upper: float | None = None
    yoy_mid: float | None = None
    content: str | None = None
    reason: str | None = None
    preyear_value: float | None = None


class EarningsGuidanceOut(BaseModel):
    """业绩预告（forecast）或业绩快报（express）。"""

    kind: str  # forecast | express
    report_period: date
    report_name: str = ""
    notice_date: date | None = None
    metrics: list[EarningsGuidanceMetricOut] = []
    revenue: float | None = None
    revenue_yoy: float | None = None
    parent_net_profit: float | None = None
    parent_net_profit_yoy: float | None = None
    roe: float | None = None
    pe_ttm: float | None = None
    pe_static: float | None = None
    valuation_date: date | None = None


class FinancialHighlightsOut(BaseModel):
    code: str
    name: str = ""
    source: str = "eastmoney"
    years: int = 5
    note: str = ""
    points: list[FinancialHighlightPointOut] = []
    guidance: list[EarningsGuidanceOut] = []


# 兼容旧名
ParentProfitPointOut = FinancialHighlightPointOut
ParentProfitSeriesOut = FinancialHighlightsOut
