"""板块过滤工具。

约定：
- 数据层（stock_provider / kline / financial）**不使用** 这个模块，保证数据完整；
- 只在 selector / backtest / feature reader 层使用；
- 通过 QS_BOARD_FILTER 环境变量配置生效。

板块定义：
    MAIN  沪市主板 600/601/603/605 + 深市主板 000/001/002/003（含原中小板）
    STAR  科创板 688/689
    GEM   创业板 300/301
    BSE   北交所 8/4/9 开头
    B     B 股 200/900

配置示例：
    QS_BOARD_FILTER=MAIN                # 只主板
    QS_BOARD_FILTER=MAIN,GEM            # 主板 + 创业板
    QS_BOARD_FILTER=MAIN,STAR           # 主板 + 科创板
    QS_BOARD_FILTER=MAIN,GEM,STAR       # 主板 + 创业板 + 科创板（不含北交所）
    QS_BOARD_FILTER=ALL                 # 不过滤
"""
from __future__ import annotations

from enum import Enum

from quant_system.config.settings import get_settings


class Board(str, Enum):
    MAIN = "MAIN"
    STAR = "STAR"
    GEM = "GEM"
    BSE = "BSE"
    B = "B"
    UNKNOWN = "UNKNOWN"


# 前缀 -> 板块
_PREFIX_MAP: dict[str, Board] = {
    # 主板
    "600": Board.MAIN, "601": Board.MAIN, "603": Board.MAIN, "605": Board.MAIN,
    "000": Board.MAIN, "001": Board.MAIN, "002": Board.MAIN, "003": Board.MAIN,
    # 科创板
    "688": Board.STAR, "689": Board.STAR,
    # 创业板
    "300": Board.GEM, "301": Board.GEM,
    # 北交所
    "8": Board.BSE, "4": Board.BSE, "9": Board.BSE,
    # B 股
    "200": Board.B, "900": Board.B,
}


def classify(code: str) -> Board:
    """根据股票代码判断板块。code 支持 `600000.SH` / `000001.SZ` / `688008.SH` 等格式。"""
    if not code:
        return Board.UNKNOWN
    pure = code.split(".")[0].strip()
    # 先尝试 3 位前缀，再退化到 1 位（北交所 8/4/9 只看首位）
    if len(pure) >= 3 and pure[:3] in _PREFIX_MAP:
        return _PREFIX_MAP[pure[:3]]
    if len(pure) >= 1 and pure[:1] in _PREFIX_MAP:
        return _PREFIX_MAP[pure[:1]]
    return Board.UNKNOWN


def parse_board_filter(raw: str | None = None) -> set[Board]:
    """解析板块过滤配置字符串。ALL 或 None 返回空集（表示不过滤）。"""
    if raw is None:
        raw = get_settings().board_filter
    parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
    if not parts or "ALL" in parts:
        return set()  # 空集 = 不过滤
    allowed: set[Board] = set()
    for p in parts:
        try:
            allowed.add(Board(p))
        except ValueError:
            continue
    return allowed


def is_allowed(code: str, filter_str: str | None = None) -> bool:
    """判断某只股票是否在当前板块白名单里。"""
    allowed = parse_board_filter(filter_str)
    if not allowed:
        return True  # 空集 = 不过滤
    return classify(code) in allowed


def filter_codes(codes: list[str], filter_str: str | None = None) -> list[str]:
    """过滤一批股票代码，返回保留下来的。保持原顺序。"""
    allowed = parse_board_filter(filter_str)
    if not allowed:
        return list(codes)
    return [c for c in codes if classify(c) in allowed]
