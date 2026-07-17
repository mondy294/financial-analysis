"""从 RelationRepository / ORM 加载 SimilarityEdge。"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select

from quant_system.database.models import StockRelationship
from quant_system.similarity.protocol import SimilarityEdge


class RelationEdgeLoader:
    """适配现有 SQLARelationRepository.session。"""

    def __init__(self, session: Any) -> None:
        self._session = session

    def list_edges(
        self,
        *,
        similarity_type: str,
        window: str,
        as_of: date | None = None,
    ) -> list[SimilarityEdge]:
        stmt = (
            select(StockRelationship)
            .where(StockRelationship.relation_type == similarity_type)
            .where(StockRelationship.window == window)
        )
        if as_of is not None:
            stmt = stmt.where(StockRelationship.calc_date == as_of)
        else:
            # 最新 calc_date
            sub = (
                select(StockRelationship.calc_date)
                .where(StockRelationship.relation_type == similarity_type)
                .where(StockRelationship.window == window)
                .order_by(StockRelationship.calc_date.desc())
                .limit(1)
            )
            latest = self._session.scalars(sub).first()
            if latest is None:
                return []
            stmt = stmt.where(StockRelationship.calc_date == latest)

        out: list[SimilarityEdge] = []
        for row in self._session.scalars(stmt).all():
            score = float(row.relation_value)
            conf = float(row.confidence) if row.confidence is not None else 1.0
            bd = dict(row.breakdown_json) if row.breakdown_json else {"price": score}
            meta = dict(row.meta_json) if row.meta_json else {}
            out.append(
                SimilarityEdge(
                    code_a=row.stock_code_a,
                    code_b=row.stock_code_b,
                    similarity_type=row.relation_type,
                    window=row.window,
                    calc_date=row.calc_date,
                    score=score,
                    confidence=conf,
                    sample_size=int(row.sample_size),
                    direction=int(row.direction or 0),
                    breakdown=bd,
                    meta=meta,
                    is_same_industry=bool(row.is_same_industry),
                )
            )
        return out
