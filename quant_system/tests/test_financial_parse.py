from __future__ import annotations

from quant_system.data.financial_provider import _parse_cn_amount, _parse_pct


def test_parse_cn_amount_units() -> None:
    assert _parse_cn_amount("4302.00万") == 4302.0 * 1e4
    assert abs(_parse_cn_amount("1.13亿") - 1.13e8) < 1e-6
    assert _parse_cn_amount(12.5) == 12.5
    assert _parse_cn_amount("False") is None
    assert _parse_cn_amount(None) is None


def test_parse_pct() -> None:
    assert _parse_pct("64.75%") == 64.75
    assert _parse_pct(-4.21) == -4.21
    assert _parse_pct(False) is None
