from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def compute_code_hash() -> str:
    """事件统计引擎实现指纹（核心模块文件内容）。"""
    root = Path(__file__).resolve().parent
    parts: list[str] = []
    for name in (
        "constants.py",
        "observe.py",
        "discovery.py",
        "aggregate.py",
        "explain.py",
        "runner.py",
    ):
        path = root / name
        if path.is_file():
            parts.append(f"{name}:{path.read_bytes().hex()[:64]}")
            parts.append(path.read_text(encoding="utf-8"))
    return sha256_hex("\n".join(parts))


def compute_engine_config_hash(
    *,
    definition_body: dict[str, Any],
    entry_version: str,
    horizon_bars: int,
    return_horizons: list[int],
    calendar: str,
    anchor_mode: str,
    price_adj: str,
    dedup_policy: str,
    providers: list[str],
) -> str:
    payload = {
        "entry_version": entry_version,
        "definition": definition_body,
        "horizon_bars": horizon_bars,
        "return_horizons": list(return_horizons),
        "calendar": calendar,
        "anchor_mode": anchor_mode,
        "price_adj": price_adj,
        "dedup_policy": dedup_policy,
        "providers": list(providers),
        "mae_convention": "1 - min_low/anchor",
        "return_anchor": "signal_close",
    }
    return sha256_hex(_canonical(payload))
