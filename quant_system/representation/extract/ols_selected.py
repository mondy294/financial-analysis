"""ols_selected：每票 Selection(corr_topk+冗余剔除) → OLS(含截距) → 残差 + features(β)。"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from quant_system.representation.catalog.protocol import DataCatalog
from quant_system.representation.context import TransformContext
from quant_system.representation.extract.protocol import ExtractionResult
from quant_system.representation.types import RepresentationBundle, SeriesPanel


class OlsSelectedExtractor:
    method_id = "ols_selected"
    version = "1.0.0"

    def extract(
        self,
        target: SeriesPanel,
        *,
        catalog: DataCatalog,
        ctx: TransformContext,
        params: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        p = dict(params or {})
        k = int(p.get("k", 5))
        redundancy = float(p.get("redundancy_corr", 0.9))
        min_obs = int(p.get("min_obs", 40))
        families = list(p.get("candidate_families") or ["BROAD_INDEX"])

        defs = catalog.list(families=families)
        if not defs:
            raise RuntimeError(
                f"DataCatalog 候选宇宙为空 families={families} catalog={catalog.catalog_id}"
            )
        data_ids = [d.data_id for d in defs]
        start = target.dates[0] if target.dates else ctx.asof
        end = target.dates[-1] if target.dates else ctx.asof
        factor_panel = catalog.load(data_ids, start=start, end=end)
        if factor_panel.values.empty or factor_panel.values.notna().sum().sum() == 0:
            raise RuntimeError(
                "DataCatalog.load 无有效因子收益：请先 qs update market / 更新指数日线"
            )

        y = target.to_dataframe()
        f = factor_panel.values.reindex(index=y.index)
        # 丢掉全 NaN 因子列
        f = f.dropna(axis=1, how="all")
        if f.shape[1] < 1:
            raise RuntimeError("对齐后无可用因子列")

        residual = pd.DataFrame(index=y.index, columns=y.columns, dtype="float64")
        features: dict[str, dict[str, float]] = {}
        selected_map: dict[str, list[str]] = {}
        skipped = 0

        for code in y.columns:
            series = y[code]
            chosen = _select_factors(series, f, k=k, redundancy=redundancy, min_obs=min_obs)
            if not chosen:
                skipped += 1
                residual[code] = np.nan
                continue
            eps, betas, r2 = _ols_residual(series, f[chosen], min_obs=min_obs)
            residual[code] = eps
            feat = {f"beta::{fid}": float(b) for fid, b in betas.items()}
            if r2 is not None:
                feat["r_squared"] = float(r2)
            features[str(code)] = feat
            selected_map[str(code)] = list(chosen)

        logger.info(
            "ols_selected: codes={} factors_universe={} skipped_low_obs={}",
            len(y.columns),
            list(f.columns),
            skipped,
        )

        bundle = RepresentationBundle(
            asof=ctx.asof,
            recipe_id=str(ctx.params.get("recipe_id") or ""),
            codes=[str(c) for c in y.columns],
            features=features,
            embeddings=None,
            tags=None,
            risk=None,
            style=None,
            meta={
                "method_id": self.method_id,
                "method_version": self.version,
                "catalog_id": catalog.catalog_id,
                "catalog_version": catalog.version,
                "selected": selected_map,
                "k": k,
                "min_obs": min_obs,
            },
        )
        out = SeriesPanel.from_dataframe(
            residual,
            series_kind=target.series_kind,
            meta={
                **target.meta,
                "common_structure": self.method_id,
                "catalog_id": catalog.catalog_id,
            },
        )
        return ExtractionResult(
            residual=out,
            representation=bundle,
            method_id=self.method_id,
            method_version=self.version,
            meta={"skipped": skipped, "factor_universe": list(f.columns)},
        )


def _select_factors(
    y: pd.Series,
    factors: pd.DataFrame,
    *,
    k: int,
    redundancy: float,
    min_obs: int,
) -> list[str]:
    scores: list[tuple[str, float]] = []
    for fid in factors.columns:
        pair = pd.concat([y, factors[fid]], axis=1, join="inner").dropna()
        if len(pair) < min_obs:
            continue
        corr = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
        if np.isnan(corr):
            continue
        scores.append((str(fid), abs(corr)))
    scores.sort(key=lambda x: x[1], reverse=True)

    chosen: list[str] = []
    for fid, _ in scores:
        if len(chosen) >= k:
            break
        if not chosen:
            chosen.append(fid)
            continue
        # 与已选因子冗余过高则跳过
        redundant = False
        for c in chosen:
            pair = pd.concat([factors[fid], factors[c]], axis=1, join="inner").dropna()
            if len(pair) < min_obs:
                continue
            r = float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
            if not np.isnan(r) and abs(r) >= redundancy:
                redundant = True
                break
        if not redundant:
            chosen.append(fid)
    return chosen


def _ols_residual(
    y: pd.Series,
    x: pd.DataFrame,
    *,
    min_obs: int,
) -> tuple[pd.Series, dict[str, float], float | None]:
    df = pd.concat([y.rename("y"), x], axis=1, join="inner").dropna()
    if len(df) < min_obs or x.shape[1] == 0:
        return y * np.nan, {}, None

    yv = df["y"].to_numpy(dtype=float)
    xv = df.drop(columns=["y"]).to_numpy(dtype=float)
    # 含截距
    ones = np.ones((len(df), 1), dtype=float)
    A = np.hstack([ones, xv])
    coef, _, _, _ = np.linalg.lstsq(A, yv, rcond=None)
    fitted = A @ coef
    resid_aligned = yv - fitted
    ss_res = float(np.sum(resid_aligned**2))
    ss_tot = float(np.sum((yv - yv.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else None

    betas = {
        str(col): float(coef[i + 1])
        for i, col in enumerate(df.drop(columns=["y"]).columns)
    }
    out = pd.Series(np.nan, index=y.index, dtype="float64")
    out.loc[df.index] = resid_aligned
    return out, betas, r2


def get_extractor(method_id: str) -> OlsSelectedExtractor:
    if method_id == "ols_selected":
        return OlsSelectedExtractor()
    raise KeyError(f"未知 Extractor: {method_id}")
