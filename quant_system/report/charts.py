"""日报图表生成（plotly，用于 HTML 内嵌）。"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from quant_system.data.repository import Repositories


def kline_mini_html(
    code: str,
    trade_date: date,
    repos: Repositories,
    lookback_days: int = 60,
) -> str:
    """生成单只股票近 60 日 K 线的 plotly HTML 片段（含 MA20）。

    返回一段可直接嵌入 HTML 的 <div>...</div>；plotly.js 通过 CDN 加载。
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        return f"<div>(plotly 未安装，无法生成 {code} 图表)</div>"

    start = trade_date - timedelta(days=lookback_days * 2)  # 冗余
    df = repos.kline.read_kline(code, start, trade_date, adj="qfq")
    if df.empty:
        return f"<div>(无 {code} K 线数据)</div>"

    df = df.tail(lookback_days)
    df["ma20"] = df["close"].rolling(20, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["trade_date"],
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name=code,
        increasing_line_color="red",   # A 股习惯：红涨
        decreasing_line_color="green",
        increasing_fillcolor="red",
        decreasing_fillcolor="green",
    ))
    fig.add_trace(go.Scatter(
        x=df["trade_date"], y=df["ma20"],
        mode="lines", name="MA20",
        line={"color": "#0080ff", "width": 1.5},
    ))
    fig.update_layout(
        title=None,
        xaxis={"rangeslider": {"visible": False}, "type": "category"},
        yaxis={"side": "right"},
        margin={"l": 30, "r": 30, "t": 20, "b": 20},
        height=280,
        showlegend=False,
        template="plotly_white",
    )
    # 只导出 div，plotly.js 由页面头部 CDN 引入
    return fig.to_html(include_plotlyjs=False, full_html=False, div_id=f"chart-{code}")
