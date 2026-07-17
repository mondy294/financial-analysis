from __future__ import annotations

from fastapi import APIRouter

from quant_system.api.schemas.common import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok", version="0.1.0")
