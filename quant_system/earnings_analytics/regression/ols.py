"""OLS Regression Backend。"""
from __future__ import annotations

from typing import Any

import numpy as np

from quant_system.earnings_analytics.constants import MIN_SAMPLES_GLOBAL
from quant_system.earnings_analytics.regression.protocol import FittedModel


def _winsorize(a: np.ndarray, lo: float = 0.01, hi: float = 0.99) -> np.ndarray:
    if a.size < 10:
        return a
    ql, qh = np.quantile(a, [lo, hi])
    return np.clip(a, ql, qh)


class OlsBackend:
    id = "ols"

    def fit(
        self,
        rows: list[dict[str, Any]],
        feature_cols: list[str],
        target_col: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> FittedModel:
        p = dict(params or {})
        use_cluster_fe = bool(p.get("cluster_fixed_effect", False))
        min_n = int(p.get("min_n", MIN_SAMPLES_GLOBAL))
        winsor = bool(p.get("winsorize", True))

        clean: list[dict[str, Any]] = []
        for r in rows:
            y = r.get(target_col)
            if y is None:
                continue
            ok = True
            for c in feature_cols:
                if r.get(c) is None:
                    ok = False
                    break
            if not ok:
                continue
            if use_cluster_fe and r.get("cluster_id") is None:
                continue
            # 亏损/非正年化利润样本不进主回归
            ann = r.get("annualized_parent_np")
            if ann is not None and float(ann) <= 0:
                continue
            clean.append(r)

        k = len(feature_cols)
        if len(clean) < max(min_n, k + 2):
            raise ValueError(
                f"样本不足: n={len(clean)} need>={max(min_n, k + 2)} target={target_col}"
            )

        y = np.array([float(r[target_col]) * 100.0 for r in clean], dtype=float)  # 百分点
        x = np.array([[float(r[c]) for c in feature_cols] for r in clean], dtype=float)
        if winsor:
            y = _winsorize(y)
            for j in range(x.shape[1]):
                x[:, j] = _winsorize(x[:, j])

        cluster_ids: list[int] = []
        if use_cluster_fe:
            cluster_ids = sorted({int(r["cluster_id"]) for r in clean})
            # 以最大簇为基准，其余加哑变量
            base = cluster_ids[0]
            dummies = []
            for r in clean:
                cid = int(r["cluster_id"])
                dummies.append([1.0 if cid == c and c != base else 0.0 for c in cluster_ids[1:]])
            x = np.hstack([x, np.array(dummies, dtype=float)])

        means = x[:, :k].mean(axis=0)
        stds = x[:, :k].std(axis=0, ddof=0)
        stds_safe = np.where(stds < 1e-12, 1.0, stds)
        x_z = (x[:, :k] - means) / stds_safe

        ones = np.ones((len(clean), 1))
        a = np.hstack([ones, x])
        coef, _, _, _ = np.linalg.lstsq(a, y, rcond=None)
        y_hat = a @ coef
        ss_res = float(np.sum((y - y_hat) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        a_z = np.hstack([ones, x_z])
        if use_cluster_fe and x.shape[1] > k:
            a_z = np.hstack([a_z, x[:, k:]])
        coef_z, _, _, _ = np.linalg.lstsq(a_z, y, rcond=None)

        coefs = {feature_cols[i]: float(coef[i + 1]) for i in range(k)}
        std_coefs = {feature_cols[i]: float(coef_z[i + 1]) for i in range(k)}
        cluster_intercepts: dict[str, float] = {}
        if use_cluster_fe and cluster_ids:
            base = cluster_ids[0]
            cluster_intercepts[str(base)] = 0.0
            for i, cid in enumerate(cluster_ids[1:]):
                cluster_intercepts[str(cid)] = float(coef[1 + k + i])

        return FittedModel(
            backend_id=self.id,
            feature_cols=list(feature_cols),
            target_col=target_col,
            intercept=float(coef[0]),
            coefs=coefs,
            means={feature_cols[i]: float(means[i]) for i in range(k)},
            stds={feature_cols[i]: float(stds[i]) for i in range(k)},
            std_coefs=std_coefs,
            metrics={"r_squared": r2, "n": len(clean)},
            n=len(clean),
            cluster_intercepts=cluster_intercepts,
        )

    def predict(self, fitted: FittedModel, X_rows: list[dict[str, Any]]) -> np.ndarray:
        from quant_system.earnings_analytics.regression.protocol import predict_row

        return np.array([predict_row(fitted, r) for r in X_rows], dtype=float)


def get_backend(backend_id: str = "ols") -> OlsBackend:
    if backend_id != "ols":
        raise ValueError(f"未知 Regression Backend: {backend_id}（V1 仅 ols）")
    return OlsBackend()
