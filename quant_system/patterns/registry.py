from __future__ import annotations

from quant_system.patterns.definition import PatternDefinition
from quant_system.patterns.definitions import build_range_breakout_definition


PATTERN_REGISTRY: dict[str, PatternDefinition] = {
    "RANGE_BREAKOUT": build_range_breakout_definition(),
}


def get_definitions(pattern_ids: list[str] | None = None) -> list[PatternDefinition]:
    if not pattern_ids:
        return list(PATTERN_REGISTRY.values())
    out: list[PatternDefinition] = []
    for pid in pattern_ids:
        definition = PATTERN_REGISTRY.get(pid.upper())
        if definition is not None:
            out.append(definition)
    return out


# 兼容旧 CLI 期望的名字
def get_pattern_specs(pattern_ids: list[str] | None = None) -> list[PatternDefinition]:
    return get_definitions(pattern_ids)
