"""Provider 工厂：composition root。

业务代码只调用工厂拿实例，永远不 import 具体 Provider 类。
未来接 QMT / tushare 只需在这里加分支。
"""
from __future__ import annotations

import os

from loguru import logger

from quant_system.data.financial_provider import (
    AkshareFinancialProvider,
    FinancialProvider,
)
from quant_system.data.stock_provider import AkshareStockProvider, StockProvider
from quant_system.market.index_provider import AkshareIndexProvider, IndexProvider
from quant_system.market.sentiment import AkshareSentimentProvider, SentimentProvider


def get_stock_provider() -> StockProvider:
    name = os.getenv("QS_STOCK_PROVIDER", "akshare").lower()
    if name == "akshare":
        return AkshareStockProvider()
    logger.warning("未知 stock provider: {}，回退到 akshare", name)
    return AkshareStockProvider()


def get_financial_provider() -> FinancialProvider:
    name = os.getenv("QS_FINANCIAL_PROVIDER", "akshare").lower()
    if name == "akshare":
        return AkshareFinancialProvider()
    logger.warning("未知 financial provider: {}，回退到 akshare", name)
    return AkshareFinancialProvider()


def get_index_provider() -> IndexProvider:
    name = os.getenv("QS_INDEX_PROVIDER", "akshare").lower()
    if name == "akshare":
        return AkshareIndexProvider()
    return AkshareIndexProvider()


def get_sentiment_provider() -> SentimentProvider:
    name = os.getenv("QS_SENTIMENT_PROVIDER", "akshare").lower()
    if name == "akshare":
        return AkshareSentimentProvider()
    return AkshareSentimentProvider()
