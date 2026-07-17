from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from quant_system.api.errors import raise_not_found

router = APIRouter(prefix="/reports", tags=["reports"])

_REPORT_DIR = Path(__file__).resolve().parents[3] / "reports"


@router.get("")
def list_reports() -> list[dict]:
    if not _REPORT_DIR.exists():
        return []
    items = []
    for p in sorted(_REPORT_DIR.glob("*.html"), reverse=True):
        stem = p.stem
        try:
            date.fromisoformat(stem)
        except ValueError:
            continue
        items.append({"trade_date": stem, "html": True, "md": (_REPORT_DIR / f"{stem}.md").exists()})
    return items


@router.get("/{trade_date}", response_model=None)
def get_report(trade_date: date) -> FileResponse:
    path = _REPORT_DIR / f"{trade_date.isoformat()}.html"
    if not path.exists():
        raise_not_found(f"日报不存在: {trade_date}")
    return FileResponse(path, media_type="text/html")
