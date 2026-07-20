from __future__ import annotations

from typing import Any


def board_tag(code: str) -> str | None:
    """由代码规则推导市场板块标签。"""
    c = (code or "").upper()
    if c.endswith(".BJ") or c.startswith(("8", "4")) and ".BJ" in c:
        return "北交所"
    num = c.split(".")[0]
    if not num.isdigit():
        return None
    if c.endswith(".SH"):
        if num.startswith("688"):
            return "科创板"
        if num.startswith(("60", "68")):
            return "沪市主板"
        return "沪市"
    if c.endswith(".SZ"):
        if num.startswith(("300", "301")):
            return "创业板"
        if num.startswith(("000", "001", "002", "003")):
            return "深市主板"
        return "深市"
    return None


def enrich_tags(code: str, meta: dict[str, Any] | None = None) -> list[str]:
    """P0 最小标签：板块 + 行业名。"""
    tags: list[str] = []
    board = board_tag(code)
    if board:
        tags.append(board)
    meta = meta or {}
    industry = meta.get("industry_name") or meta.get("industry")
    if industry and str(industry) not in tags:
        tags.append(str(industry))
    return tags
