"""薄 DataCatalog：挂载已有 index_daily 宽基指数（宇宙，不决定入模）。"""
from __future__ import annotations

from datetime import date
from typing import Sequence

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from quant_system.database.models import IndexDaily
from quant_system.market.index_provider import DEFAULT_INDICES
from quant_system.representation.catalog.protocol import DataCatalog, DataPanel, DataSeriesDef

# 展示名（data_id 仍用交易所代码，禁止业务逻辑写死「只用这四个」）
_NAMES: dict[str, str] = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
    "899050.BJ": "北证50",
    "000016.SH": "上证50",
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
}


class IndexDataCatalog:
    """P0：从 DB index_daily 提供 BROAD_INDEX 宇宙。"""

    catalog_id = "index_datacatalog_v1"
    version = "1.0.0"

    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self, *, families: Sequence[str] | None = None) -> list[DataSeriesDef]:
        defs = [
            DataSeriesDef(
                data_id=code,
                name=_NAMES.get(code, code),
                family="BROAD_INDEX",
                source="index_daily",
                meta={"akshare_symbol": sym},
            )
            for code, sym in DEFAULT_INDICES.items()
        ]
        if families is None:
            return defs
        fam = {f.upper() for f in families}
        return [d for d in defs if d.family.upper() in fam]

    def load(
        self,
        data_ids: Sequence[str],
        *,
        start: date,
        end: date,
    ) -> DataPanel:
        ids = list(dict.fromkeys(data_ids))
        if not ids:
            return DataPanel(data_ids=[], dates=[], values=pd.DataFrame())

        rows = self._session.execute(
            select(
                IndexDaily.index_code,
                IndexDaily.trade_date,
                IndexDaily.close,
                IndexDaily.pct_change,
            )
            .where(IndexDaily.index_code.in_(ids))
            .where(IndexDaily.trade_date >= start)
            .where(IndexDaily.trade_date <= end)
            .order_by(IndexDaily.trade_date)
        ).all()

        if not rows:
            return DataPanel(data_ids=ids, dates=[], values=pd.DataFrame(columns=ids))

        long = pd.DataFrame(
            rows, columns=["index_code", "trade_date", "close", "pct_change"]
        )
        # 优先用库内 pct_change；缺失则用 close 算
        long["ret"] = pd.to_numeric(long["pct_change"], errors="coerce")
        # 库内多为百分数（如 1.23 表示 1.23%），统一成小数收益
        # 若 |ret| 多数 > 0.2 且 close 可用，则按百分数 /100
        sample = long["ret"].dropna()
        if len(sample) > 10 and float(sample.abs().median()) > 0.2:
            long["ret"] = long["ret"] / 100.0

        need_from_close = long["ret"].isna() & long["close"].notna()
        if need_from_close.any():
            close_wide = long.pivot(index="trade_date", columns="index_code", values="close")
            close_wide = close_wide.astype("float64").sort_index()
            ret_from_close = close_wide.pct_change()
            for code in ids:
                if code not in ret_from_close.columns:
                    continue
                mask = (long["index_code"] == code) & long["ret"].isna()
                if not mask.any():
                    continue
                mapped = long.loc[mask, "trade_date"].map(ret_from_close[code])
                long.loc[mask, "ret"] = mapped.values

        wide = long.pivot(index="trade_date", columns="index_code", values="ret")
        wide = wide.reindex(columns=ids).sort_index()
        dates = [d.date() if hasattr(d, "date") else d for d in wide.index]
        wide.index = dates
        return DataPanel(
            data_ids=ids,
            dates=list(wide.index),
            values=wide.astype("float64"),
            meta={"catalog_id": self.catalog_id, "version": self.version},
        )


def build_default_catalog(session: Session) -> DataCatalog:
    return IndexDataCatalog(session)
