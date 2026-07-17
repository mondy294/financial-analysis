"""16 Market Representation P0 单测。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from quant_system.representation.catalog.protocol import DataPanel, DataSeriesDef
from quant_system.representation.context import TransformContext
from quant_system.representation.extract.ols_selected import OlsSelectedExtractor
from quant_system.representation.pipeline.recipe import (
    PipelineRecipe,
    TransformNodeSpec,
    assert_linear_chain,
)
from quant_system.representation.pipeline.runner import SeriesPipeline
from quant_system.representation.pipeline.transforms import DEFAULT_REGISTRY
from quant_system.representation.recipes import (
    RECIPE_RETURN_CFR_AUTO,
    RECIPE_RETURN_RAW,
    get_recipe,
)
from quant_system.representation.types import SeriesPanel
from quant_system.similarity.protocol import enrich_pearson_pair


class FakeCatalog:
    catalog_id = "fake"
    version = "0.0.1"

    def __init__(self, panel: DataPanel, defs: list[DataSeriesDef] | None = None) -> None:
        self._panel = panel
        self._defs = defs or [
            DataSeriesDef(data_id=i, name=i, family="BROAD_INDEX", source="fake")
            for i in panel.data_ids
        ]

    def list(self, *, families=None):
        if families is None:
            return list(self._defs)
        fam = {f.upper() for f in families}
        return [d for d in self._defs if d.family.upper() in fam]

    def load(self, data_ids, *, start, end):
        cols = [c for c in data_ids if c in self._panel.values.columns]
        v = self._panel.values[cols]
        return DataPanel(data_ids=cols, dates=list(v.index), values=v)


def _dates(n: int, start: date = date(2026, 1, 2)) -> list[date]:
    out = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_recipe_linear_ok() -> None:
    r = get_recipe(RECIPE_RETURN_CFR_AUTO)
    assert_linear_chain(r)


def test_recipe_fork_rejected() -> None:
    bad = PipelineRecipe(
        recipe_id="bad",
        nodes=(
            TransformNodeSpec("a", "missing", inputs=()),
            TransformNodeSpec("b", "missing", inputs=("a",)),
            TransformNodeSpec("c", "missing", inputs=("a",)),
        ),
        outputs=("b",),
    )
    with pytest.raises(ValueError, match="分叉"):
        assert_linear_chain(bad)


def test_ols_selected_does_not_regress_all_factors() -> None:
    """伪造 8 个因子，每票只能入选 k=2 → 证明未全量回归。"""
    dates = _dates(80)
    rng = np.random.default_rng(0)
    # 公共因子
    f1 = rng.normal(0, 0.01, size=len(dates))
    f2 = rng.normal(0, 0.01, size=len(dates))
    noise_factors = {
        f"F{i}": rng.normal(0, 0.01, size=len(dates)) for i in range(3, 9)
    }
    # 股票只由 F1/F2 驱动
    stock = 1.2 * f1 + 0.8 * f2 + rng.normal(0, 0.002, size=len(dates))

    factor_df = pd.DataFrame(
        {"F1": f1, "F2": f2, **noise_factors},
        index=dates,
    )
    catalog = FakeCatalog(
        DataPanel(data_ids=list(factor_df.columns), dates=dates, values=factor_df)
    )
    y = SeriesPanel.from_dataframe(
        pd.DataFrame({"AAA": stock}, index=dates),
        series_kind="RETURN",
    )
    ctx = TransformContext(asof=dates[-1], catalog=catalog, params={"recipe_id": "t"})
    result = OlsSelectedExtractor().extract(
        y,
        catalog=catalog,
        ctx=ctx,
        params={"k": 2, "redundancy_corr": 0.95, "min_obs": 40, "candidate_families": ["BROAD_INDEX"]},
    )
    selected = result.representation.meta["selected"]["AAA"]
    assert len(selected) == 2
    assert set(selected) == {"F1", "F2"}
    # 残差方差应明显小于原始
    raw_std = float(np.nanstd(stock))
    res_std = float(np.nanstd(result.residual.values["AAA"]))
    assert res_std < raw_std * 0.5
    # features 含 beta，且有扩展槽位类型（RepresentationBundle）
    assert result.representation.embeddings is None
    assert "beta::F1" in (result.representation.features or {}).get("AAA", {})


def test_pipeline_auto_uses_policy_not_hardcoded_indices() -> None:
    dates = _dates(60)
    rng = np.random.default_rng(1)
    mkt = rng.normal(0, 0.01, size=len(dates))
    a = mkt + rng.normal(0, 0.001, size=len(dates))
    b = mkt + rng.normal(0, 0.001, size=len(dates))
    factor_df = pd.DataFrame({"MKT": mkt, "NOISE": rng.normal(0, 0.01, len(dates))}, index=dates)
    catalog = FakeCatalog(
        DataPanel(data_ids=["MKT", "NOISE"], dates=dates, values=factor_df)
    )
    panel = SeriesPanel.from_dataframe(
        pd.DataFrame({"A": a, "B": b}, index=dates),
        series_kind="RETURN",
    )
    recipe = get_recipe(RECIPE_RETURN_CFR_AUTO)
    ctx = TransformContext(
        asof=dates[-1],
        catalog=catalog,
        params={"recipe_id": recipe.recipe_id},
    )
    # 覆盖 candidate 为假因子名（证明不是写死 HS300）
    nodes = []
    for n in recipe.nodes:
        if n.transform_id == "common_structure":
            params = {**n.params, "candidate_families": ["BROAD_INDEX"], "selector_k": 1}
            nodes.append(TransformNodeSpec(n.node_id, n.transform_id, params, n.inputs))
        else:
            nodes.append(n)
    recipe = PipelineRecipe(recipe.recipe_id, tuple(nodes), recipe.outputs)
    out = SeriesPipeline(DEFAULT_REGISTRY).run(panel, recipe=recipe, ctx=ctx)
    # 去掉市场后 A/B 相关应下降
    raw_corr = float(pd.Series(a).corr(pd.Series(b)))
    res = out.panel.to_dataframe()
    res_corr = float(res["A"].corr(res["B"]))
    assert raw_corr > 0.85
    assert res_corr < raw_corr - 0.3
    assert out.exposures is not None


def test_enrich_pearson_carries_pipeline_meta() -> None:
    r = enrich_pearson_pair(
        0.5, 50, "W60", extra_meta={"pipeline": {"recipe_id": RECIPE_RETURN_CFR_AUTO}}
    )
    assert r.meta["pipeline"]["recipe_id"] == RECIPE_RETURN_CFR_AUTO


def test_raw_recipe_has_no_cfr_node() -> None:
    r = get_recipe(RECIPE_RETURN_RAW)
    assert all(n.transform_id != "common_structure" for n in r.nodes)
