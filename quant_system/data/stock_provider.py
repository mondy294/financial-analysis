"""股票行情 & 基础信息 Provider。

设计原则：
- 所有 akshare 调用统一通过 infra.cache.cached_call，Provider 内不写自己的缓存；
- 使用 tenacity 重试 + 限流；
- 输出列名标准化，业务层不感知 akshare 原生列名。
"""
from __future__ import annotations

import functools
import os
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

import pandas as pd
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from quant_system.config.settings import get_settings
from quant_system.infra.cache import CachePolicy, cached_call


# ============================================================================
# 屏蔽 akshare 内部 tqdm 输出（避免冲掉我们自己的 rich 进度条）
# ============================================================================

# tqdm 支持通过环境变量或猴子补丁禁用
os.environ.setdefault("TQDM_DISABLE", "1")

try:
    import tqdm  # noqa: E402

    _original_tqdm_init = tqdm.tqdm.__init__

    @functools.wraps(_original_tqdm_init)
    def _silent_tqdm_init(self, *args, **kwargs):
        kwargs["disable"] = True
        return _original_tqdm_init(self, *args, **kwargs)

    tqdm.tqdm.__init__ = _silent_tqdm_init  # type: ignore[method-assign]
except Exception:
    pass


# ============================================================================
# 协议
# ============================================================================

@runtime_checkable
class StockProvider(Protocol):
    name: str

    def fetch_stock_basic(self, force_refresh: bool = False) -> pd.DataFrame:
        """columns=[code, name, exchange, industry_name, list_date, is_st,
                    total_share, float_share, market_cap]"""
        ...

    def fetch_daily_kline(
        self,
        code: str,
        start: date,
        end: date,
        adjust: str = "none",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """columns=[code, trade_date, open, high, low, close, pre_close,
                    volume, amount, turnover_rate, pct_change, adj_factor]"""
        ...

    def fetch_pool_members(
        self, pool_code: str, force_refresh: bool = False
    ) -> pd.DataFrame:
        """columns=[code, weight]"""
        ...


# ============================================================================
# akshare 实现
# ============================================================================

import threading  # noqa: E402

# 全局节流状态（跨线程共享；throttle_global=True 时使用）
_last_call_at: float = 0.0
_throttle_lock = threading.Lock()

# 每线程独立节流状态（throttle_global=False 时使用，达到真并发）
_thread_local = threading.local()


def _throttle() -> None:
    """akshare 调用节流。

    两种模式（通过 QS_DATA__THROTTLE_GLOBAL 切换）：

    - **True（全局节流，保守）**：所有线程共享一个 `_last_call_at`，跨线程串行等待。
      QPS 上限 = 1000 / interval_ms。并发数再高也不会加速。适合脆弱数据源（东财）。

    - **False（每线程节流，激进）**：每个 worker 线程独立计时，互不干扰。
      QPS 上限 = concurrency × (1000 / interval_ms)。适合稳定数据源（腾讯）。
      **注意**：可能触发数据源风控（腾讯目前未验证到极限）。

    默认 False（真并发），因为项目已切腾讯数据源。
    """
    cfg = get_settings().data
    interval = cfg.akshare_request_interval_ms / 1000.0

    if cfg.throttle_global:
        # 全局节流：跨线程串行
        global _last_call_at
        with _throttle_lock:
            now = time.time()
            wait = interval - (now - _last_call_at)
            if wait > 0:
                time.sleep(wait)
            _last_call_at = time.time()
    else:
        # 每线程独立节流：真并发
        last = getattr(_thread_local, "last_call_at", 0.0)
        now = time.time()
        wait = interval - (now - last)
        if wait > 0:
            time.sleep(wait)
        _thread_local.last_call_at = time.time()


def _retry():
    cfg = get_settings().data
    return retry(
        stop=stop_after_attempt(cfg.akshare_retry_times),
        wait=wait_exponential(multiplier=cfg.akshare_retry_backoff, min=1, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )


def _normalize_code(raw: str) -> str:
    """把 akshare 返回的 6 位代码转成 `600000.SH` / `000001.SZ` / `430000.BJ`。"""
    raw = str(raw).strip().zfill(6)
    if raw.startswith(("60", "68", "51", "56", "58", "5")):
        return f"{raw}.SH"
    if raw.startswith(("00", "30", "20", "15", "16", "18")):
        return f"{raw}.SZ"
    if raw.startswith(("8", "4", "9")):
        return f"{raw}.BJ"
    return f"{raw}.SH"


def _to_pure_code(code: str) -> str:
    """把 `600000.SH` 转回 6 位纯代码给 akshare 用。"""
    return code.split(".")[0]


def _to_tx_symbol(code: str) -> str:
    """把 `600000.SH` 转成腾讯接口需要的 `sh600000` 格式。"""
    pure, market = code.split(".")
    return f"{market.lower()}{pure}"


class AkshareStockProvider:
    name = "akshare"

    # -------------------- 基础信息 --------------------

    def fetch_stock_basic(self, force_refresh: bool = False) -> pd.DataFrame:
        """全量拉取股票基础信息（每日更新一次）。"""
        return cached_call(
            key_parts=("akshare.stock_basic", "multi_source"),
            fn=self._fetch_stock_basic_raw,
            policy=CachePolicy.recent(),  # 每日更新，1 小时缓存即可
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_stock_basic_raw(self) -> pd.DataFrame:
        # 多源容错：东财 → 新浪 → 交易所直连，第一个成功的即采用。
        # 单一源易受 IP 封禁 / 服务端 TLS 故障影响（如深交所 www.szse.cn 握手失败），
        # 故按可靠性降级尝试。
        df, source = self._fetch_name_list_with_fallback()

        result = pd.DataFrame()
        result["code"] = df["code"].values
        result["name"] = df["name"].values
        result["exchange"] = result["code"].str.split(".").str[1]
        result["is_st"] = df["is_st"].values

        # 市值：东财源自带；其余源单独向东财补，失败留空（不阻塞主表）
        if "market_cap" in df.columns:
            result["market_cap"] = df["market_cap"].values
        else:
            result["market_cap"] = self._enrich_market_cap(result["code"])

        # 以下字段暂留空，后续可 individual_info 补
        result["industry_name"] = None
        result["list_date"] = None
        result["total_share"] = None
        result["float_share"] = None

        logger.info("拉取 stock_basic: {} 只（来源: {}）", len(result), source)
        return result

    # -------------------- stock_basic 多源实现 --------------------

    def _fetch_name_list_with_fallback(self) -> tuple[pd.DataFrame, str]:
        """按可靠性依次尝试各数据源，返回 (标准化名单 df, 来源标签)。

        每个源产出至少 [code, name, is_st]，东财额外带 market_cap。
        全部失败才抛异常。
        """
        sources = [
            ("东财 spot", self._name_list_from_em),
            ("新浪 spot", self._name_list_from_sina),
            ("交易所直连", self._name_list_from_exchange),
        ]
        errors: list[str] = []
        for label, fn in sources:
            try:
                df = fn()
                if df is not None and not df.empty:
                    return df, label
                errors.append(f"{label}: 返回空")
            except Exception as e:
                errors.append(f"{label}: {type(e).__name__} {str(e)[:80]}")
                logger.warning("stock_basic 源[{}]不可用，尝试下一个: {}", label, e)
        raise RuntimeError("所有 stock_basic 数据源均失败 → " + " | ".join(errors))

    def _name_list_from_em(self) -> pd.DataFrame:
        """东财实时快照：一次拿到 代码 + 名称 + 总市值（最优）。"""
        import akshare as ak

        _throttle()
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            raise RuntimeError("stock_zh_a_spot_em 返回空")
        out = pd.DataFrame()
        out["code"] = df["代码"].astype(str).apply(_normalize_code)
        out["name"] = df["名称"].astype(str)
        out["is_st"] = out["name"].str.contains("ST", na=False)
        out["market_cap"] = pd.to_numeric(df["总市值"], errors="coerce")
        return out

    def _name_list_from_sina(self) -> pd.DataFrame:
        """新浪实时快照：全 A 股 代码 + 名称（无市值）。代码带 sh/sz/bj 前缀。"""
        import akshare as ak

        _throttle()
        df = ak.stock_zh_a_spot()
        if df is None or df.empty:
            raise RuntimeError("stock_zh_a_spot 返回空")
        out = pd.DataFrame()
        # 代码形如 sh600000 / sz000001 / bj920000 → 去掉 2 位前缀再标准化
        out["code"] = df["代码"].astype(str).str[2:].apply(_normalize_code)
        out["name"] = df["名称"].astype(str)
        out["is_st"] = out["name"].str.contains("ST", na=False)
        return out

    def _name_list_from_exchange(self) -> pd.DataFrame:
        """交易所直连兜底：沪市（主板+科创板，必成）+ 深市（尽力，失败仅告警）。"""
        import akshare as ak

        frames: list[pd.DataFrame] = []

        # 沪市：主板 + 科创板
        sh_parts: list[pd.DataFrame] = []
        for sym in ("主板A股", "科创板"):
            _throttle()
            d = ak.stock_info_sh_name_code(symbol=sym)
            if d is not None and not d.empty:
                o = pd.DataFrame()
                o["code"] = d["证券代码"].astype(str).apply(_normalize_code)
                o["name"] = d["证券简称"].astype(str)
                sh_parts.append(o)
        if not sh_parts:
            raise RuntimeError("上交所名单获取失败")
        frames.extend(sh_parts)

        # 深市：尽力而为，失败不阻塞（www.szse.cn 常有 TLS 故障）
        try:
            _throttle()
            d = ak.stock_info_sz_name_code(symbol="A股列表")
            if d is not None and not d.empty:
                code_col = "A股代码" if "A股代码" in d.columns else d.columns[0]
                name_col = "A股简称" if "A股简称" in d.columns else d.columns[1]
                o = pd.DataFrame()
                o["code"] = d[code_col].astype(str).apply(_normalize_code)
                o["name"] = d[name_col].astype(str)
                frames.append(o)
            else:
                logger.warning("深交所名单返回空，深市股票将缺失")
        except Exception as e:
            logger.warning("深交所名单获取失败，深市股票将缺失: {}", e)

        out = pd.concat(frames, ignore_index=True)
        out = out.drop_duplicates(subset="code").reset_index(drop=True)
        out["is_st"] = out["name"].str.contains("ST", na=False)
        return out

    def _enrich_market_cap(self, codes: pd.Series) -> pd.Series:
        """非东财源时，单独向东财 spot 补市值；失败则整列留空。"""
        import akshare as ak

        empty = pd.Series([None] * len(codes), index=codes.index, dtype="object")
        try:
            _throttle()
            df_spot = ak.stock_zh_a_spot_em()
            if df_spot is None or df_spot.empty:
                return empty
            cap_map = {
                _normalize_code(str(row.get("代码", ""))): pd.to_numeric(
                    row.get("总市值"), errors="coerce"
                )
                for _, row in df_spot.iterrows()
            }
            return codes.map(lambda c: cap_map.get(c))
        except Exception as e:
            logger.warning("市值补充失败（东财 spot 不可用），market_cap 留空: {}", e)
            return empty

    # -------------------- K 线 --------------------

    def fetch_daily_kline(
        self,
        code: str,
        start: date,
        end: date,
        adjust: str = "none",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """拉取单只股票的日线（原始价 + adj_factor）。

        akshare 的 adjust 参数：'' 不复权 / 'qfq' 前复权 / 'hfq' 后复权。
        我们统一拉两次：不复权 + 后复权，用 hfq_close / raw_close 反推 adj_factor。
        """
        # kline 按结束日选择缓存策略
        policy = CachePolicy.for_kline_range(end)
        return cached_call(
            key_parts=("akshare.kline", code, start.isoformat(), end.isoformat()),
            fn=lambda: self._fetch_daily_kline_raw(code, start, end),
            policy=policy,
            force_refresh=force_refresh,
        )

    # 数据源不支持的板块（腾讯 hist_tx 对北交所 JSON 结构异常，会抛 KeyError）
    # 命中这些板块的股票直接返回空 df，不发起网络请求
    _UNSUPPORTED_MARKETS: tuple[str, ...] = ("BJ",)

    def _empty_kline_df(self) -> pd.DataFrame:
        return pd.DataFrame(columns=[
            "code", "trade_date", "open", "high", "low", "close",
            "pre_close", "volume", "amount", "turnover_rate",
            "pct_change", "adj_factor",
        ])

    @_retry()
    def _fetch_daily_kline_raw(self, code: str, start: date, end: date) -> pd.DataFrame:
        """使用腾讯行情接口拉日线（东财 push2his 常被限流/封 IP）。

        腾讯 stock_zh_a_hist_tx 支持 adjust='' / 'qfq' / 'hfq'，
        返回列 [date, open, close, high, low, amount]（其中 amount 实际是"成交量/股"）。
        换手率、涨跌幅腾讯不返回，本地计算/留空。

        北交所（.BJ）腾讯不支持，直接返回空 df，避免每只都跑 3 次重试浪费时间。
        """
        # 早退：腾讯不支持的板块（北交所）
        market = code.split(".")[-1].upper() if "." in code else ""
        if market in self._UNSUPPORTED_MARKETS:
            return self._empty_kline_df()

        import akshare as ak

        tx_symbol = _to_tx_symbol(code)
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")

        _throttle()
        try:
            df_raw = ak.stock_zh_a_hist_tx(
                symbol=tx_symbol,
                start_date=start_str, end_date=end_str, adjust="",
            )
        except KeyError as e:
            # 腾讯 JSON 里 day/hfqday/qfqday 都没有 → akshare 抛 KeyError
            # 说明该股票在腾讯数据源就是空，不再重试，直接返回空 df
            logger.debug("腾讯 hist_tx {} 无数据(KeyError: {})，返回空 df", code, e)
            return self._empty_kline_df()

        if df_raw is None or df_raw.empty:
            return self._empty_kline_df()

        _throttle()
        try:
            df_hfq = ak.stock_zh_a_hist_tx(
                symbol=tx_symbol,
                start_date=start_str, end_date=end_str, adjust="hfq",
            )
        except KeyError as e:
            # 后复权失败：raw 有数据 hfq 没有 → adj_factor 默认 1.0 也可用
            logger.debug("腾讯 hist_tx hfq {} 失败(KeyError: {})，adj_factor 用 1.0", code, e)
            df_hfq = None

        return self._transform_kline_tx(code, df_raw, df_hfq)

    @staticmethod
    def _transform_kline_tx(code: str, df_raw: pd.DataFrame, df_hfq: pd.DataFrame) -> pd.DataFrame:
        """把腾讯两份 DataFrame 转成标准列。

        腾讯字段: date, open, close, high, low, amount（此处 amount 实为成交量，单位=股）
        目标字段: code, trade_date, open, high, low, close, pre_close,
                  volume, amount, turnover_rate, pct_change, adj_factor
        """
        df_raw = df_raw.rename(columns={"date": "trade_date"}).copy()
        df_raw["trade_date"] = pd.to_datetime(df_raw["trade_date"]).dt.date

        # 通过 hfq 收盘 / raw 收盘 反推 adj_factor
        if df_hfq is not None and not df_hfq.empty:
            df_hfq2 = df_hfq.rename(columns={"date": "trade_date"}).copy()
            df_hfq2["trade_date"] = pd.to_datetime(df_hfq2["trade_date"]).dt.date
            merged = df_raw[["trade_date", "close"]].merge(
                df_hfq2[["trade_date", "close"]],
                on="trade_date", suffixes=("_raw", "_hfq"),
            )
            merged["adj_factor"] = (merged["close_hfq"] / merged["close_raw"]).round(6)
            df_raw = df_raw.merge(
                merged[["trade_date", "adj_factor"]], on="trade_date", how="left",
            )
        else:
            df_raw["adj_factor"] = 1.0

        # 腾讯的 amount 列实际存的是"成交量（股）"，我们把它映射到 volume；
        # 真实成交额（元）腾讯不提供 → 用 volume × 均价 近似
        df_raw["volume"] = pd.to_numeric(df_raw["amount"], errors="coerce")
        df_raw["amount"] = (df_raw["volume"] * (df_raw["open"] + df_raw["close"]) / 2).round(2)

        df_raw["code"] = code
        df_raw = df_raw.sort_values("trade_date").reset_index(drop=True)

        # pre_close = 前一日 close
        df_raw["pre_close"] = df_raw["close"].shift(1)
        first_idx = df_raw.index[0]
        if pd.isna(df_raw.at[first_idx, "pre_close"]):
            # 首行没前值，只能置成自己（回测/指标会 dropna 掉）
            df_raw.at[first_idx, "pre_close"] = df_raw.at[first_idx, "close"]

        # pct_change 本地计算
        df_raw["pct_change"] = (
            (df_raw["close"] - df_raw["pre_close"]) / df_raw["pre_close"] * 100
        ).round(4)

        # 换手率腾讯没有，留空（DB 字段允许 NULL；DQ 会记 WARN）
        df_raw["turnover_rate"] = None

        cols = [
            "code", "trade_date", "open", "high", "low", "close", "pre_close",
            "volume", "amount", "turnover_rate", "pct_change", "adj_factor",
        ]
        return df_raw[cols]

    # -------------------- 股票池成分 --------------------

    def fetch_pool_members(self, pool_code: str, force_refresh: bool = False) -> pd.DataFrame:
        """拉取指数成分股。

        pool_code：
        - HS300 → 000300
        - ZZ500 → 000905
        """
        return cached_call(
            key_parts=("akshare.pool_member", pool_code),
            fn=lambda: self._fetch_pool_members_raw(pool_code),
            policy=CachePolicy.recent(),  # 成分变更不频繁，1h 缓存
            force_refresh=force_refresh,
        )

    @_retry()
    def _fetch_pool_members_raw(self, pool_code: str) -> pd.DataFrame:
        import akshare as ak

        symbol_map = {"HS300": "000300", "ZZ500": "000905"}
        if pool_code not in symbol_map:
            raise ValueError(f"不支持的池代码: {pool_code}")

        _throttle()
        df = ak.index_stock_cons_sina(symbol=symbol_map[pool_code])
        if df is None or df.empty:
            raise RuntimeError(f"pool_member 返回空: {pool_code}")

        # sina 返回列: code / name（列名可能是 code 或 品种代码）
        code_col = "code" if "code" in df.columns else df.columns[0]
        result = pd.DataFrame()
        result["code"] = df[code_col].astype(str).apply(_normalize_code)
        result["weight"] = None
        logger.info("拉取 {} 成分股: {} 只", pool_code, len(result))
        return result[["code", "weight"]]
