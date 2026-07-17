from quant_system.patterns.definitions import build_range_breakout_definition
from quant_system.patterns.serde import bump_version, definition_from_dict, definition_to_dict


def test_definition_roundtrip() -> None:
    original = build_range_breakout_definition()
    restored = definition_from_dict(definition_to_dict(original))
    assert restored.id == original.id
    assert restored.version == original.version
    assert restored.threshold == original.threshold
    assert len(restored.timeline) == len(original.timeline)
    assert restored.timeline[0].name == original.timeline[0].name
    assert set(restored.timeline[0].targets) == set(original.timeline[0].targets)


def test_bump_version() -> None:
    assert bump_version("tl-v2.5") == "tl-v2.6"
    assert bump_version("v9") == "v10"
    assert bump_version("alpha") == "alpha-1"
