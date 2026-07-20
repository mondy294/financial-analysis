from __future__ import annotations

from quant_system.patterns.definition import PatternDefinition
from quant_system.patterns.definitions import (
    build_arc_high_retest_definition,
    build_range_breakout_definition,
)

# 进程内 published 缓存；publish / seed 后 invalidate
_CACHE: dict[str, PatternDefinition] | None = None

# 纯 Python 出厂种子（DB 不可用时的回退）
_SEED_REGISTRY: dict[str, PatternDefinition] = {
    "RANGE_BREAKOUT": build_range_breakout_definition(),
    "ARC_HIGH_RETEST": build_arc_high_retest_definition(),
}


def invalidate_definition_cache() -> None:
    global _CACHE
    _CACHE = None


def get_registry(*, force: bool = False) -> dict[str, PatternDefinition]:
    """published Definition 字典（DB 优先，失败回退 seed）。"""
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    try:
        from quant_system.database.migrations import ensure_schema_columns
        from quant_system.infra.db import session_scope
        from quant_system.patterns.store import ensure_seeded, load_all_published

        ensure_schema_columns()
        with session_scope() as session:
            ensure_seeded(session)
            defs = load_all_published(session)
        if defs:
            _CACHE = {d.id: d for d in defs}
        else:
            _CACHE = dict(_SEED_REGISTRY)
    except Exception:
        _CACHE = dict(_SEED_REGISTRY)
    return _CACHE


# 兼容旧代码：模块加载时可用；运行时请优先 get_registry() / get_definitions()
PATTERN_REGISTRY = _SEED_REGISTRY


def get_definitions(pattern_ids: list[str] | None = None) -> list[PatternDefinition]:
    reg = get_registry()
    if not pattern_ids:
        return list(reg.values())
    out: list[PatternDefinition] = []
    for pid in pattern_ids:
        definition = reg.get(pid.upper())
        if definition is not None:
            out.append(definition)
    return out


# 兼容旧 CLI 期望的名字
def get_pattern_specs(pattern_ids: list[str] | None = None) -> list[PatternDefinition]:
    return get_definitions(pattern_ids)
