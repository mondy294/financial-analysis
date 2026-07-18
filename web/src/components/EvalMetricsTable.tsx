import { useMemo } from "react";
import type { FeatureCatalogItem, PatternEval } from "@/api/client";

/** 特征得分配色：>=80 达标绿 / 40~80 一般黄 / <40 偏差红 */
function simColor(sim: number | undefined): string {
  if (sim == null || Number.isNaN(sim)) return "var(--text-muted, #94a3b8)";
  if (sim >= 80) return "#0f766e";
  if (sim >= 40) return "#ca8a04";
  return "#b42318";
}

function fmtEvalValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "—";
    return Number.isInteger(v) ? String(v) : v.toFixed(4);
  }
  if (typeof v === "boolean") return v ? "是" : "否";
  return String(v);
}

/** `platform.slope` / `context.price_position` → 目录名 `slope` / `price_position` */
export function featureNameFromKey(key: string): { stage: string; name: string } {
  const dot = key.indexOf(".");
  if (dot <= 0) return { stage: "", name: key };
  return { stage: key.slice(0, dot), name: key.slice(dot + 1) };
}

export type EvalFeatureRow = {
  key: string;
  stage: string;
  name: string;
  value: unknown;
  sim: number | undefined;
  hardFailed: boolean;
  description: string;
};

export function buildEvalFeatureRows(
  result: Pick<PatternEval, "feature_similarity" | "metrics_values" | "hard_failed">,
  catalog?: FeatureCatalogItem[] | null,
): EvalFeatureRow[] {
  const byName = new Map<string, FeatureCatalogItem>();
  for (const c of catalog || []) byName.set(c.name, c);

  const sims = result.feature_similarity || {};
  const values = (result.metrics_values || {}) as Record<string, unknown>;
  const hard = new Set(result.hard_failed || []);
  const keys = Array.from(new Set([...Object.keys(sims), ...Object.keys(values)])).sort();

  return keys.map((key) => {
    const { stage, name } = featureNameFromKey(key);
    return {
      key,
      stage,
      name,
      value: values[key],
      sim: sims[key] as number | undefined,
      hardFailed: hard.has(key),
      description: byName.get(name)?.description || "",
    };
  });
}

type Props = {
  result: Pick<PatternEval, "feature_similarity" | "metrics_values" | "hard_failed">;
  catalog?: FeatureCatalogItem[] | null;
  emptyText?: string;
};

/** 评估结果：指标名 + 含义 + 值 + 得分 */
export function EvalMetricsTable({
  result,
  catalog,
  emptyText = "未进入特征评分（硬约束/历史不足等已拦截）",
}: Props) {
  const rows = useMemo(() => buildEvalFeatureRows(result, catalog), [result, catalog]);

  if (!rows.length) {
    return <p className="muted">{emptyText}</p>;
  }

  return (
    <table className="data eval-metrics">
      <thead>
        <tr>
          <th>指标</th>
          <th>含义</th>
          <th style={{ textAlign: "right" }}>值</th>
          <th style={{ textAlign: "right" }}>得分</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className={row.hardFailed ? "is-hardfail" : ""}>
            <td>
              {row.stage ? <span className="eval-stage-tag">{row.stage}</span> : null}
              <span className="mono">{row.name}</span>
              {row.hardFailed ? <span className="eval-hf-badge">硬约束</span> : null}
            </td>
            <td className="eval-feat-desc muted">
              {row.description || "—"}
            </td>
            <td className="mono" style={{ textAlign: "right" }}>
              {fmtEvalValue(row.value)}
            </td>
            <td
              className="mono"
              style={{ textAlign: "right", color: simColor(row.sim), fontWeight: 600 }}
            >
              {row.sim == null ? "—" : row.sim.toFixed(1)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
