from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from itertools import product
from typing import Any

import pandas as pd

from quant_system.patterns.aggregator import aggregate_stages, aggregate_weighted
from quant_system.patterns.definition import CONTEXT_STAGE, HardConstraints, PatternDefinition
from quant_system.patterns.evaluator import LinearToleranceEvaluator
from quant_system.patterns.features.extractor import FeatureExtractor
from quant_system.patterns.result import FeatureSimilarity, FeatureValue, PatternMatchResult


@dataclass
class GenericPatternMatcher:
    extractor: FeatureExtractor = field(default_factory=FeatureExtractor)
    evaluator: LinearToleranceEvaluator = field(default_factory=LinearToleranceEvaluator)

    def match(
        self,
        code: str,
        trade_date: date,
        series: pd.DataFrame,
        definition: PatternDefinition,
        *,
        meta: dict[str, Any] | None = None,
        last_amount: float | None = None,
    ) -> PatternMatchResult:
        meta = meta or {}
        failed = self._hard_constraint_fail(
            definition.constraints, meta=meta, last_amount=last_amount, trade_date=trade_date,
        )
        if failed:
            return PatternMatchResult(
                pattern_id=definition.id,
                code=code,
                trade_date=trade_date,
                matched=False,
                similarity=0.0,
                reasons=[failed],
            )

        bars = self._prepare_series(series, trade_date)
        if len(bars) < definition.min_window:
            return PatternMatchResult(
                pattern_id=definition.id,
                code=code,
                trade_date=trade_date,
                matched=False,
                similarity=0.0,
                reasons=["insufficient_history"],
            )

        # 股票级特征只算一次，不参与窗口枚举
        context_pack = self._score_context(definition, bars)
        if context_pack["hard_failed"]:
            return PatternMatchResult(
                pattern_id=definition.id,
                code=code,
                trade_date=trade_date,
                matched=False,
                similarity=0.0,
                stage_similarity={CONTEXT_STAGE: context_pack["stage_score"]},
                feature_similarity={
                    f"{CONTEXT_STAGE}.{k}": s.similarity
                    for k, s in context_pack["sim_by_key"].items()
                },
                metrics={
                    "values": {
                        f"{CONTEXT_STAGE}.{k}": context_pack["values"][k].value
                        for k in context_pack["values"]
                    },
                },
                reasons=[f"hard_fail:{CONTEXT_STAGE}.{n}" for n in context_pack["hard_failed"]],
                hard_failed=[f"{CONTEXT_STAGE}.{n}" for n in context_pack["hard_failed"]],
            )

        best: PatternMatchResult | None = None
        best_key: tuple[int, float, int, float] | None = None

        for lengths in self._iter_length_combos(definition):
            total = sum(lengths)
            if total > len(bars):
                continue
            candidate = self._score_candidate(
                code, trade_date, bars, definition, lengths, context_pack=context_pack,
            )
            key = self._rank_key(candidate, definition, lengths)
            if best is None or best_key is None or key > best_key:
                best = candidate
                best_key = key

        if best is None:
            return PatternMatchResult(
                pattern_id=definition.id,
                code=code,
                trade_date=trade_date,
                matched=False,
                similarity=0.0,
                reasons=["insufficient_history"],
            )
        best.matched = (
            best.similarity >= definition.threshold
            and not best.hard_failed
        )
        if best.hard_failed:
            best.reasons = [f"hard_fail:{name}" for name in best.hard_failed] + best.reasons
        return best

    def _score_context(
        self,
        definition: PatternDefinition,
        bars: pd.DataFrame,
    ) -> dict[str, Any]:
        values = self.extractor.extract_context_features(definition.context_features, bars)
        sims: list[FeatureSimilarity] = []
        sim_by_key: dict[str, FeatureSimilarity] = {}
        hard_failed: list[str] = []
        for ctx in definition.context_features:
            fv = values[ctx.result_key]
            sim = self.evaluator.evaluate(fv, ctx.target)
            sim = FeatureSimilarity(
                name=ctx.result_key,
                similarity=sim.similarity,
                distance=sim.distance,
                actual=sim.actual,
                ideal=sim.ideal,
                weight=sim.weight,
            )
            sims.append(sim)
            sim_by_key[ctx.result_key] = sim
            if ctx.target.hard_failed(fv.value, sim.similarity):
                hard_failed.append(ctx.result_key)
        return {
            "values": values,
            "sims": sims,
            "sim_by_key": sim_by_key,
            "hard_failed": hard_failed,
            "stage_score": aggregate_weighted(sims) if sims else 0.0,
        }

    def _score_candidate(
        self,
        code: str,
        trade_date: date,
        bars: pd.DataFrame,
        definition: PatternDefinition,
        lengths: tuple[int, ...],
        *,
        context_pack: dict[str, Any],
    ) -> PatternMatchResult:
        total = sum(lengths)
        window = bars.iloc[-total:].reset_index(drop=True)
        slices, atoms = self._slice_by_lengths(
            window, definition, lengths, bars=bars.reset_index(drop=True),
        )

        feature_sims: list[FeatureSimilarity] = []
        feature_sim_map: dict[str, float] = {}
        hard_failed: list[str] = []
        metrics: dict[str, Any] = {"values": {}, "atoms": atoms}
        stage_feature_sims: dict[str, list[FeatureSimilarity]] = {
            stage.name: [] for stage in definition.timeline
        }

        for stage, stage_bars in zip(definition.timeline, slices, strict=True):
            values = self.extractor.extract_stage_features(stage, stage_bars)
            for name, fv in values.items():
                key = f"{stage.name}.{name}"
                target = stage.targets[name]
                metrics["values"][key] = fv.value
                sim = self.evaluator.evaluate(fv, target)
                feature_sims.append(sim)
                feature_sim_map[key] = sim.similarity
                stage_feature_sims[stage.name].append(sim)
                if target.hard_failed(fv.value, sim.similarity):
                    hard_failed.append(key)

        frames_by_stage = {
            stage.name: stage_bars
            for stage, stage_bars in zip(definition.timeline, slices, strict=True)
        }
        for rel in definition.relations:
            fv = self.extractor.extract_relation(rel, atoms, frames_by_stage)
            key = f"{rel.attach_to_stage}.{rel.name}"
            metrics["values"][key] = fv.value
            sim = self.evaluator.evaluate(fv, rel.target)
            sim = FeatureSimilarity(
                name=rel.name,
                similarity=sim.similarity,
                distance=sim.distance,
                actual=sim.actual,
                ideal=sim.ideal,
                weight=sim.weight,
            )
            feature_sims.append(sim)
            feature_sim_map[key] = sim.similarity
            stage_feature_sims[rel.attach_to_stage].append(sim)
            if rel.target.hard_failed(fv.value, sim.similarity):
                hard_failed.append(key)

        # 合并股票级 context（所有候选窗口共享同一份）
        context_values: dict[str, FeatureValue] = context_pack["values"]
        for key, fv in context_values.items():
            full_key = f"{CONTEXT_STAGE}.{key}"
            metrics["values"][full_key] = fv.value
            sim = context_pack["sim_by_key"][key]
            feature_sims.append(sim)
            feature_sim_map[full_key] = sim.similarity
        if context_pack["sims"]:
            stage_feature_sims[CONTEXT_STAGE] = list(context_pack["sims"])

        stage_scores = {
            name: aggregate_weighted(items) for name, items in stage_feature_sims.items()
        }
        overall = aggregate_stages(stage_scores, definition.stage_weights)
        avg_dist = 0.0
        if feature_sims:
            avg_dist = sum(s.distance * s.weight for s in feature_sims) / max(
                sum(s.weight for s in feature_sims), 1e-12,
            )

        chosen = {
            stage.name: length
            for stage, length in zip(definition.timeline, lengths, strict=True)
        }
        window_ranges = self._window_ranges(definition, slices)
        metrics["hard_failed"] = hard_failed
        metrics["chosen_window_ranges"] = window_ranges
        reasons = self._build_reasons(
            chosen, stage_scores, feature_sim_map, metrics["values"], window_ranges,
        )
        return PatternMatchResult(
            pattern_id=definition.id,
            code=code,
            trade_date=trade_date,
            matched=False,
            similarity=overall,
            stage_similarity=stage_scores,
            feature_similarity=feature_sim_map,
            chosen_windows=chosen,
            metrics=metrics,
            reasons=reasons,
            distance=round(avg_dist, 6),
            hard_failed=hard_failed,
        )

    def _slice_by_lengths(
        self,
        window: pd.DataFrame,
        definition: PatternDefinition,
        lengths: tuple[int, ...],
        *,
        bars: pd.DataFrame | None = None,
    ) -> tuple[list[pd.DataFrame], dict[str, dict[str, float | None]]]:
        slices: list[pd.DataFrame] = []
        atoms: dict[str, dict[str, float | None]] = {}
        cursor = 0
        total = sum(lengths)
        # 窗口起点在全序列中的位置（用于第一段取 prior_close）
        win_start = max(0, len(bars) - total) if bars is not None else 0
        for stage, length in zip(definition.timeline, lengths, strict=True):
            part = window.iloc[cursor: cursor + length].copy()
            prior_close: float | None = None
            if cursor > 0:
                prior_close = float(window.iloc[cursor - 1]["close"])
            elif bars is not None and win_start > 0:
                prior_close = float(bars.iloc[win_start - 1]["close"])
            if prior_close is not None:
                part.attrs["prior_close"] = prior_close
            cursor += length
            slices.append(part)
            atoms[stage.name] = self.extractor.extract_atoms(part)
        return slices, atoms

    @staticmethod
    def _iter_length_combos(definition: PatternDefinition):
        ranges = [
            range(stage.window.min_length, stage.window.max_length + 1)
            for stage in definition.timeline
        ]
        return product(*ranges)

    @staticmethod
    def _rank_key(
        result: PatternMatchResult,
        definition: PatternDefinition,
        lengths: tuple[int, ...],
    ) -> tuple[int, float, int, float]:
        # 先保证硬约束通过，再比 similarity；总窗口更短更好；更靠近中位更好
        total = sum(lengths)
        mid_pen = 0.0
        for stage, length in zip(definition.timeline, lengths, strict=True):
            mid_pen += abs(length - stage.window.midpoint)
        hard_ok = 0 if result.hard_failed else 1
        return (hard_ok, result.similarity, -total, -mid_pen)

    @staticmethod
    def _prepare_series(series: pd.DataFrame, trade_date: date) -> pd.DataFrame:
        if series is None or series.empty:
            return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume"])
        df = series.copy()
        if "trade_date" not in df.columns:
            raise ValueError("series must contain trade_date")
        df = df[df["trade_date"] <= trade_date].sort_values("trade_date")
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                raise ValueError(f"series missing column: {col}")
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.reset_index(drop=True)

    @staticmethod
    def _hard_constraint_fail(
        constraints: HardConstraints | None,
        *,
        meta: dict[str, Any],
        last_amount: float | None,
        trade_date: date,
    ) -> str | None:
        if constraints is None:
            return None
        if constraints.exclude_st and meta.get("is_st"):
            return "excluded_st"
        if constraints.min_amount is not None:
            amount = float(last_amount or 0.0)
            if amount < constraints.min_amount:
                return "amount_too_low"
        if constraints.min_list_days is not None and meta.get("list_date") is not None:
            age = (trade_date - meta["list_date"]).days
            if age < constraints.min_list_days:
                return "too_new"
        return None

    @staticmethod
    def _window_ranges(
        definition: PatternDefinition,
        slices: list[pd.DataFrame],
    ) -> dict[str, dict[str, Any]]:
        """各 Stage 实际交易日区间（枚举选中的那一组）。"""
        out: dict[str, dict[str, Any]] = {}
        for stage, stage_bars in zip(definition.timeline, slices, strict=True):
            if stage_bars is None or stage_bars.empty or "trade_date" not in stage_bars.columns:
                continue
            start = stage_bars["trade_date"].iloc[0]
            end = stage_bars["trade_date"].iloc[-1]
            out[stage.name] = {
                "length": int(len(stage_bars)),
                "start": start.isoformat() if hasattr(start, "isoformat") else str(start),
                "end": end.isoformat() if hasattr(end, "isoformat") else str(end),
            }
        return out

    @staticmethod
    def _build_reasons(
        chosen: dict[str, int],
        stage_scores: dict[str, float],
        feature_sim_map: dict[str, float],
        values: dict[str, Any],
        window_ranges: dict[str, dict[str, Any]] | None = None,
    ) -> list[str]:
        if window_ranges:
            win_parts = []
            for name, length in chosen.items():
                rng = window_ranges.get(name) or {}
                if rng.get("start") and rng.get("end"):
                    win_parts.append(f"{name}={length}d({rng['start']}~{rng['end']})")
                else:
                    win_parts.append(f"{name}={length}d")
            parts = [f"窗口 {', '.join(win_parts)}"]
        else:
            parts = [f"窗口 {', '.join(f'{k}={v}d' for k, v in chosen.items())}"]
        for stage, score in stage_scores.items():
            parts.append(f"{stage} sim={score:.0f}")
        top_feats = sorted(feature_sim_map.items(), key=lambda x: x[1], reverse=True)[:3]
        for name, score in top_feats:
            val = values.get(name)
            if isinstance(val, (int, float)):
                parts.append(f"{name}={val:.4f} sim={score:.0f}")
            else:
                parts.append(f"{name} sim={score:.0f}")
        return parts[:6]
