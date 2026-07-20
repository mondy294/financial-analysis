import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type PatternEval } from "@/api/client";
import { EvalMetricsTable } from "@/components/EvalMetricsTable";
import { StockPicker } from "@/components/StockPicker";

export function EvalPage() {
  const [params] = useSearchParams();
  const patterns = useQuery({ queryKey: ["patterns-meta"], queryFn: api.patternsMeta });
  const meta = useQuery({ queryKey: ["trading-day"], queryFn: api.tradingDay });
  const catalog = useQuery({ queryKey: ["feature-catalog"], queryFn: api.featureCatalog });
  const [code, setCode] = useState(params.get("code") || "");
  const [date, setDate] = useState(params.get("date") || "");
  const [patternId, setPatternId] = useState(params.get("pattern") || "RANGE_BREAKOUT");
  const [result, setResult] = useState<PatternEval | null>(null);

  useEffect(() => {
    if (!date && meta.data?.latest_trading_day) setDate(meta.data.latest_trading_day);
  }, [meta.data, date]);

  const evalMut = useMutation({
    mutationFn: () =>
      api.evalPattern({
        code: code.trim(),
        trade_date: date || undefined,
        pattern_id: patternId,
      }),
    onSuccess: setResult,
  });

  useEffect(() => {
    if (params.get("code") && params.get("auto") === "1") {
      evalMut.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>单票 Pattern 评估</h1>
          <p className="muted">现场 match 当前 Definition，不落库</p>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: "1rem", padding: "1rem" }}>
        <div className="toolbar">
          <label>
            股票
            <StockPicker mode="single" value={code} onChange={setCode} />
          </label>
          <label>
            交易日
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label>
            Pattern
            <select value={patternId} onChange={(e) => setPatternId(e.target.value)}>
              {(patterns.data || []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name_en
                    ? `${p.display_name} / ${p.display_name_en}`
                    : p.display_name || p.id}{" "}
                  ({p.id})
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn primary"
            type="button"
            disabled={!code.trim() || evalMut.isPending}
            onClick={() => evalMut.mutate()}
          >
            {evalMut.isPending ? "评估中…" : "评估"}
          </button>
        </div>
      </div>

      {evalMut.error && <div className="error-box">{(evalMut.error as Error).message}</div>}

      {result && (
        <>
          <div className="cards">
            <div className="card">
              <div className="label">结果</div>
              <div className="value">
                <span className={`badge ${result.matched ? "ok" : "fail"}`}>
                  {result.matched ? "MATCHED" : "MISS"}
                </span>
              </div>
            </div>
            <div className="card">
              <div className="label">最终评分 / 阈值</div>
              <div className="value mono">
                {result.similarity.toFixed(2)} / {result.threshold}
              </div>
            </div>
            <div className="card">
              <div className="label">版本</div>
              <div className="value mono">{result.version}</div>
            </div>
            <div className="card">
              <div className="label">K 线</div>
              <div className="value" style={{ fontSize: "1rem" }}>
                <Link to={`/stocks/${result.code}?date=${result.trade_date}&eval=1`}>
                  查看 {result.code}
                </Link>
              </div>
            </div>
          </div>

          <div className="panel" style={{ marginBottom: "0.85rem" }}>
            <div className="panel-head">特征明细</div>
            <div style={{ padding: "0.75rem 1rem" }}>
              {Object.keys(result.chosen_window_ranges || {}).length > 0 && (
                <p className="muted mono" style={{ fontSize: "0.78rem", margin: "0 0 0.65rem" }}>
                  {Object.entries(result.chosen_window_ranges || {}).map(([k, r]) => (
                    <span key={k} style={{ marginRight: "0.85rem" }}>
                      {k}={result.chosen_windows?.[k] ?? "?"}d {r.start}~{r.end}
                    </span>
                  ))}
                </p>
              )}
              {result.hard_failed.length > 0 && (
                <p className="eval-hardfail" style={{ marginTop: 0 }}>
                  硬约束失败：{result.hard_failed.join("、")}
                </p>
              )}
              {Object.keys(result.stage_similarity || {}).length > 0 && (
                <div className="eval-chips" style={{ marginBottom: "0.65rem" }}>
                  {Object.entries(result.stage_similarity || {}).map(([stage, sim]) => (
                    <span className="eval-chip" key={stage}>
                      {stage}
                      <b>{Number(sim).toFixed(1)}</b>
                    </span>
                  ))}
                </div>
              )}
              <EvalMetricsTable result={result} catalog={catalog.data} />
            </div>
          </div>

          {result.reasons.length > 0 && (
            <div className="panel">
              <div className="panel-head">Reasons</div>
              <ul className="reason-list" style={{ padding: "0.75rem 1.5rem" }}>
                {result.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </>
  );
}
