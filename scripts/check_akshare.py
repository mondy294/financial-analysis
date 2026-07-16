"""快速检查 akshare 数据源可用性。

跑 5 个关键接口，只关心两件事：
1. 通不通
2. 拉一小段真实数据

用法：
    python scripts/check_akshare.py
"""
from __future__ import annotations

import time
import warnings

warnings.filterwarnings("ignore")


def check(name: str, fn) -> None:
    t0 = time.time()
    try:
        result = fn()
        cost = time.time() - t0
        print(f"  ✓ {name:32s} {cost:>5.2f}s  {result}")
    except Exception as e:
        cost = time.time() - t0
        msg = str(e).split("\n")[0][:80]
        print(f"  ✗ {name:32s} {cost:>5.2f}s  {msg}")


def main() -> None:
    print("=" * 70)
    print("akshare 接口健康检查")
    print("=" * 70)

    import akshare as ak

    # 1. 股票代码列表（最基础）
    check(
        "stock_info_a_code_name",
        lambda: f"{len(ak.stock_info_a_code_name())} 只股票",
    )

    # 2. 实时行情快照（东财，容易掉）
    check(
        "stock_zh_a_spot_em",
        lambda: f"{len(ak.stock_zh_a_spot_em())} 条快照",
    )

    # 3. 日线（最重要！你要的历史行情）
    check(
        "stock_zh_a_hist(600000,近1月)",
        lambda: f"{len(ak.stock_zh_a_hist(symbol='600000', period='daily', start_date='20260601', end_date='20260714', adjust=''))} 条",
    )

    # 4. HS300 成分
    check(
        "index_stock_cons_sina(HS300)",
        lambda: f"{len(ak.index_stock_cons_sina(symbol='000300'))} 只成分",
    )

    # 5. 财务
    check(
        "stock_financial_abstract_ths",
        lambda: f"{len(ak.stock_financial_abstract_ths(symbol='600000', indicator='按报告期'))} 期",
    )

    # 6. 指数日线
    check(
        "stock_zh_index_daily(上证)",
        lambda: f"{len(ak.stock_zh_index_daily(symbol='sh000001'))} 条",
    )

    # 7. 交易日历
    check(
        "tool_trade_date_hist_sina",
        lambda: f"{len(ak.tool_trade_date_hist_sina())} 个交易日",
    )

    print("=" * 70)
    print("规则：")
    print("  - 全 ✓ 就可以 `qs update all` 拉真实数据")
    print("  - stock_zh_a_hist 是主力接口，它 ✓ 就能拉 K 线")
    print("  - stock_zh_a_spot_em ✗ 不影响主流程（只影响市值字段）")


if __name__ == "__main__":
    main()
