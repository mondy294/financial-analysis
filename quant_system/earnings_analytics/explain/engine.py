"""Explain Engine。"""
from __future__ import annotations

from typing import Any

from quant_system.earnings_analytics.regression.protocol import FittedModel


def run_explain(
    row: dict[str, Any],
    prediction: dict[str, Any],
    score: dict[str, Any],
    *,
    regression_by_horizon: dict[str, FittedModel],
    horizon: int = 20,
) -> dict[str, Any]:
    key = f"ret_{horizon}d"
    fitted = regression_by_horizon.get(key)
    contribs: list[dict[str, Any]] = []
    if fitted is not None:
        for col in fitted.feature_cols:
            x = row.get(col)
            mean = fitted.means.get(col, 0.0)
            coef = fitted.coefs.get(col, 0.0)
            if x is None:
                continue
            contrib = coef * (float(x) - float(mean))
            contribs.append(
                {
                    "key": col,
                    "value": float(x),
                    "mean": float(mean),
                    "coef": float(coef),
                    "contrib": float(contrib),
                }
            )
        cid = row.get("cluster_id")
        if cid is not None and fitted.cluster_intercepts:
            ce = fitted.cluster_intercepts.get(str(int(cid)), 0.0)
            contribs.append(
                {
                    "key": "cluster_effect",
                    "value": int(cid),
                    "mean": 0.0,
                    "coef": 1.0,
                    "contrib": float(ce),
                }
            )
        contribs.sort(key=lambda c: abs(c["contrib"]), reverse=True)
        for i, c in enumerate(contribs):
            c["rank"] = i + 1

    ranking = [c["key"] for c in contribs]
    # 简单自然语言模板（V1）
    parts = []
    if prediction.get("premium_pct") is not None:
        p = float(prediction["premium_pct"])
        parts.append(
            f"相对公允盈利收益率，市值约{'高估' if p > 0 else '低估'} {abs(p)*100:.1f}%。"
        )
    e20 = prediction.get("expected_return_20d")
    if e20 is not None:
        parts.append(f"模型预期未来20日约 {float(e20):+.2f} 个百分点。")
    if contribs:
        top = contribs[0]
        direction = "抬升" if top["contrib"] > 0 else "压制"
        parts.append(f"对预期贡献最大的因素是 {top['key']}（{direction}）。")

    return {
        "feature_contributions": contribs,
        "contribution_ranking": ranking,
        "natural_language": " ".join(parts) if parts else None,
        "horizon": horizon,
        "score_snapshot": {
            "mispricing_score": score.get("mispricing_score"),
            "percentile": score.get("percentile"),
        },
    }
