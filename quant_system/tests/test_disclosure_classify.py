from quant_system.data.disclosure_provider import (
    CATEGORY_ANNUAL,
    CATEGORY_EXPRESS,
    CATEGORY_FORECAST,
    CATEGORY_INTERIM,
    classify_notice,
)


def test_classify_forecast_express_interim() -> None:
    assert classify_notice("业绩预告", "xx半年度业绩预告") == CATEGORY_FORECAST
    assert classify_notice("业绩快报", "xx业绩快报公告") == CATEGORY_EXPRESS
    assert classify_notice("半年度报告全文", "2026年半年度报告") == CATEGORY_INTERIM
    assert classify_notice("年度报告全文", "2025年年度报告") == CATEGORY_ANNUAL
