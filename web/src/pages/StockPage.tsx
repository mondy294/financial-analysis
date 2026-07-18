import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type PatternEval, type WindowRange } from "@/api/client";
import { EvalMetricsTable } from "@/components/EvalMetricsTable";
import { KlineChart } from "@/components/KlineChart";
import { RelationList, RelationMiniList } from "@/components/RelationList";

/** 特征得分配色：>=80 达标绿 / 40~80 及格黄 / <40 偏差红 */
function simColor(sim: number | undefined): string {
  if (sim == null || Number.isNaN(sim)) return "var(--text-muted, #94a3b8)";
  if (sim >= 80) return "#0f766e";
  if (sim >= 40) return "#ca8a04";
  return "#b42318";
}

/** 仅允许站内相对路径，防止 open redirect */
function safeReturnPath(raw: string | null): string | null {
  if (!raw) return null;
  let path = raw;
  try {
    path = decodeURIComponent(raw);
  } catch {
    return null;
  }
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("://")) return null;
  return path;
}

export function StockPage() {
  const { code = "" } = useParams();
  const [params] = useSearchParams();
  const returnTo = safeReturnPath(params.get("return"));
  const [date, setDate] = useState(params.get("date") || "");
  const [tab, setTab] = useState<"features" | "eval" | "hits" | "relations">("features");
  const [relWindow, setRelWindow] = useState("W60");
  const [evalResult, setEvalResult] = useState<PatternEval | null>(null);

  const detail = useQuery({
    queryKey: ["stock", code],
    queryFn: () => api.stockDetail(code),
    enabled: !!code,
  });
  const kline = useQuery({
    queryKey: ["kline", code],
    queryFn: () => api.kline(code, 1000),
    enabled: !!code,
  });
  const features = useQuery({
    queryKey: ["features", code],
    queryFn: () => api.features(code, 1000),
    enabled: !!code,
  });
  const snapshot = useQuery({
    queryKey: ["snapshot", code, date],
    queryFn: () => api.snapshot(code, date || undefined),
    enabled: !!code,
  });
  const hits = useQuery({
    queryKey: ["hits", code, date],
    queryFn: () => api.patternHits(code, date || undefined),
    enabled: !!code,
  });
  const relations = useQuery({
    queryKey: ["relationships", code, date, relWindow],
    queryFn: () =>
      api.relationships(code, {
        tradeDate: date || undefined,
        window: relWindow,
        limit: 50,
      }),
    enabled: !!code,
  });
  const clusterProfile = relWindow === "W250" ? "pearson_w250" : "pearson_w60";
  const clusterQ = useQuery({
    queryKey: ["stock-cluster", code, clusterProfile],
    queryFn: () => api.stockCluster(code, clusterProfile, 24),
    enabled: !!code,
  });
  const catalog = useQuery({ queryKey: ["feature-catalog"], queryFn: api.featureCatalog });
  const clusterHref =
    clusterQ.data?.cluster_id != null
      ? `/clusters?profile=${clusterProfile}&cluster=${clusterQ.data.cluster_id}`
      : `/clusters?profile=${clusterProfile}`;

  useEffect(() => {
    if (!date && snapshot.data?.trade_date) setDate(snapshot.data.trade_date);
  }, [snapshot.data, date]);

  useEffect(() => {
    if (params.get("tab") === "relations") setTab("relations");
  }, [params]);

  const evalMut = useMutation({
    mutationFn: () =>
      api.evalPattern({
        code,
        trade_date: date || undefined,
        pattern_id: "RANGE_BREAKOUT",
      }),
    onSuccess: (r) => {
      setEvalResult(r);
      setTab("eval");
    },
  });

  useEffect(() => {
    if (params.get("eval") === "1" && code) {
      evalMut.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  const ranges: Record<string, WindowRange> | null = useMemo(() => {
    if (evalResult?.chosen_window_ranges) return evalResult.chosen_window_ranges;
    const hit = hits.data?.[0];
    return hit?.chosen_window_ranges || null;
  }, [evalResult, hits.data]);

  const latestFeat = features.data?.[features.data.length - 1];

  return (
    <>
      <div className="page-head">
        <div>
          {returnTo ? (
            <p style={{ margin: "0 0 0.35rem" }}>
              <Link to={returnTo} className="muted">
                ← 返回榜单
              </Link>
            </p>
          ) : null}
          <h1>
            <span className="mono">{code}</span> {detail.data?.name || ""}
          </h1>
          <p className="muted">
            {detail.data?.industry_name || "—"}
            {detail.data?.is_st ? " · ST" : ""}
            {detail.data?.list_date ? ` · 上市 ${detail.data.list_date}` : ""}
            {clusterQ.data?.cluster_id != null ? (
              <>
                {" · "}
                <Link className="cluster-badge" to={clusterHref} title="查看所属相关簇">
                  簇 {clusterQ.data.label}
                  <span className="mono muted">
                    #{clusterQ.data.rank_in_cluster}/{clusterQ.data.size}
                  </span>
                </Link>
              </>
            ) : null}
          </p>
        </div>
        <div className="toolbar">
          <label>
            评估日
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <button
            className="btn primary"
            type="button"
            disabled={evalMut.isPending}
            onClick={() => evalMut.mutate()}
          >
            {evalMut.isPending ? "评估中…" : "RANGE_BREAKOUT 评估"}
          </button>
          <Link className="btn" to={`/patterns/eval?code=${code}&date=${date}`}>
            评估页
          </Link>
        </div>
      </div>

      {(detail.error || evalMut.error) && (
        <div className="error-box">
          {(detail.error as Error)?.message || (evalMut.error as Error)?.message}
        </div>
      )}

      <div className="stock-layout">
        <div>
          {kline.data && (
            <KlineChart bars={kline.data} features={features.data || []} ranges={ranges} />
          )}
          <div className="panel" style={{ marginTop: "0.85rem" }}>
            <div className="tabs">
              <button
                type="button"
                className={tab === "features" ? "active" : ""}
                onClick={() => setTab("features")}
              >
                特征
              </button>
              <button
                type="button"
                className={tab === "eval" ? "active" : ""}
                onClick={() => setTab("eval")}
              >
                Pattern 评估
              </button>
              <button
                type="button"
                className={tab === "hits" ? "active" : ""}
                onClick={() => setTab("hits")}
              >
                近期命中
              </button>
              <button
                type="button"
                className={tab === "relations" ? "active" : ""}
                onClick={() => setTab("relations")}
              >
                关联股票
              </button>
            </div>
            <div style={{ padding: "0 1rem 1rem" }}>
              {tab === "features" && (
                <dl className="kv">
                  {latestFeat &&
                    Object.entries(latestFeat)
                      .filter(([k]) => k !== "trade_date")
                      .map(([k, v]) => (
                        <Fragment key={k}>
                          <dt>{k}</dt>
                          <dd className="mono">
                            {v === null || v === undefined
                              ? "—"
                              : typeof v === "number"
                                ? v.toFixed(4)
                                : String(v)}
                          </dd>
                        </Fragment>
                      ))}
                  {!latestFeat && <span className="muted">无特征数据</span>}
                </dl>
              )}
              {tab === "eval" && (
                <>
                  {!evalResult && <p className="muted">点击上方按钮进行现场评估</p>}
                  {evalResult && (
                    <>
                      <p style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
                        <span className={`badge ${evalResult.matched ? "ok" : "fail"}`}>
                          {evalResult.matched ? "MATCHED" : "MISS"}
                        </span>
                        <span className="mono">
                          相似度 {evalResult.similarity.toFixed(2)} / 阈值 {evalResult.threshold}
                        </span>
                        <span className="muted mono">距离 {evalResult.distance.toFixed(4)}</span>
                        <span className="muted mono">{evalResult.version}</span>
                      </p>

                      <div className="eval-chips">
                        {Object.entries(evalResult.stage_similarity || {}).map(([stage, sim]) => (
                          <span className="eval-chip" key={stage}>
                            {stage}
                            <b style={{ color: simColor(sim) }}>{sim.toFixed(1)}</b>
                          </span>
                        ))}
                      </div>

                      {evalResult.hard_failed.length > 0 && (
                        <p className="eval-hardfail">
                          硬约束失败：{evalResult.hard_failed.join("、")}
                        </p>
                      )}

                      {Object.keys(evalResult.chosen_window_ranges || {}).length > 0 && (
                        <p className="muted mono" style={{ fontSize: "0.78rem", margin: "0 0 0.5rem" }}>
                          {Object.entries(evalResult.chosen_window_ranges).map(([k, r]) => (
                            <span key={k} style={{ marginRight: "0.85rem" }}>
                              {k}={evalResult.chosen_windows?.[k] ?? "?"}d {r.start}~{r.end}
                            </span>
                          ))}
                        </p>
                      )}

                      <EvalMetricsTable result={evalResult} catalog={catalog.data} />

                      {evalResult.reasons.length > 0 && (
                        <details className="eval-reasons">
                          <summary className="muted">评估说明 ({evalResult.reasons.length})</summary>
                          <ul>
                            {evalResult.reasons.map((r, i) => (
                              <li key={i} className="mono">{r}</li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </>
                  )}
                </>
              )}
              {tab === "hits" && (
                <table className="data">
                  <thead>
                    <tr>
                      <th>日期</th>
                      <th>Pattern</th>
                      <th>分</th>
                      <th>排名</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(hits.data || []).map((h) => (
                      <tr key={`${h.trade_date}-${h.pattern_id}`}>
                        <td className="mono">{h.trade_date}</td>
                        <td>{h.pattern_id}</td>
                        <td className="mono">{h.pattern_score.toFixed(1)}</td>
                        <td className="mono">{h.pattern_rank}</td>
                      </tr>
                    ))}
                    {!hits.data?.length && (
                      <tr>
                        <td colSpan={4} className="muted">
                          无入库命中
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
              {tab === "relations" && (
                <>
                  <div className="rel-toolbar">
                    <label className="pager-size" style={{ flexDirection: "row" }}>
                      窗口
                      <select
                        value={relWindow}
                        onChange={(e) => setRelWindow(e.target.value)}
                      >
                        <option value="W60">W60（短）</option>
                        <option value="W250">W250（长）</option>
                      </select>
                    </label>
                    <span className="muted mono">
                      快照日 {relations.data?.calc_date || "—"}
                      {relations.isFetching ? " · 加载中…" : ""}
                    </span>
                    {!relations.data?.calc_date && !relations.isFetching && (
                      <span className="muted">
                        暂无关系快照，请先跑{" "}
                        <code>qs relationship build --date …</code>
                      </span>
                    )}
                  </div>
                  <div className="rel-columns">
                    <div>
                      <h3 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem" }}>
                        正相关{" "}
                        <span className="muted">
                          ({relations.data?.positive.length ?? 0})
                        </span>
                      </h3>
                      <RelationList
                        rows={relations.data?.positive || []}
                        emptyText="无正相关邻居"
                        dateQuery={date || undefined}
                      />
                    </div>
                    <div>
                      <h3 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem" }}>
                        负相关{" "}
                        <span className="muted">
                          ({relations.data?.negative.length ?? 0})
                        </span>
                      </h3>
                      <RelationList
                        rows={relations.data?.negative || []}
                        emptyText="无负相关邻居（A 股强负相关通常很少）"
                        dateQuery={date || undefined}
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="side-stack">
          <div className="panel">
            <div className="panel-head">报价摘要</div>
            <div style={{ padding: "0.75rem 1rem" }}>
              <dl className="kv">
                <dt>日期</dt>
                <dd>{snapshot.data?.trade_date || "—"}</dd>
                <dt>收盘</dt>
                <dd>{snapshot.data?.close?.toFixed(2) ?? "—"}</dd>
                <dt>涨跌</dt>
                <dd>
                  {snapshot.data?.pct_change != null
                    ? `${snapshot.data.pct_change.toFixed(2)}%`
                    : "—"}
                </dd>
                <dt>成交额</dt>
                <dd>
                  {snapshot.data?.amount != null
                    ? (snapshot.data.amount / 1e8).toFixed(2) + " 亿"
                    : "—"}
                </dd>
                <dt>量</dt>
                <dd>
                  {snapshot.data?.volume != null
                    ? (snapshot.data.volume / 1e4).toFixed(0) + " 万"
                    : "—"}
                </dd>
              </dl>
            </div>
          </div>
          <div className="panel">
            <div className="panel-head">
              所属相关簇 · {relWindow}
              {clusterQ.data?.cluster_id != null ? (
                <Link className="btn" to={clusterHref} style={{ marginLeft: "auto", fontSize: "0.78rem" }}>
                  打开簇
                </Link>
              ) : null}
            </div>
            <div style={{ padding: "0.4rem 0.75rem 0.75rem" }}>
              {clusterQ.isLoading && <span className="muted">加载中…</span>}
              {!clusterQ.isLoading && clusterQ.data?.cluster_id == null && (
                <span className="muted">暂无簇归属，请先跑 similarity.refresh</span>
              )}
              {clusterQ.data?.cluster_id != null && (
                <>
                  <p style={{ margin: "0 0 0.45rem", fontSize: "0.9rem" }}>
                    <Link to={clusterHref}>{clusterQ.data.label}</Link>
                    <span className="muted">
                      {" "}
                      · 排名 #{clusterQ.data.rank_in_cluster} / {clusterQ.data.size}
                    </span>
                  </p>
                  <div className="rel-mini-row is-self">
                    <span>
                      <span className="mono">{code}</span>
                      <span className="muted"> {detail.data?.name || "当前"}</span>
                    </span>
                    <span className="mono muted">
                      {clusterQ.data.centrality != null
                        ? clusterQ.data.centrality.toFixed(2)
                        : "—"}
                    </span>
                  </div>
                  {clusterQ.data.peers.map((p) => {
                    const href = date
                      ? `/stocks/${p.code}?date=${date}`
                      : `/stocks/${p.code}`;
                    return (
                      <div key={p.code} className="rel-mini-row">
                        <Link to={href}>
                          <span className="mono">{p.code}</span>
                          <span className="muted"> {p.name}</span>
                        </Link>
                        <span className="mono muted">{p.centrality.toFixed(2)}</span>
                      </div>
                    );
                  })}
                  {clusterQ.data.size > clusterQ.data.peers.length + 1 ? (
                    <p className="muted" style={{ margin: "0.5rem 0 0", fontSize: "0.8rem" }}>
                      <Link to={clusterHref}>
                        查看全部 {clusterQ.data.size} 只成员 →
                      </Link>
                    </p>
                  ) : null}
                </>
              )}
            </div>
          </div>
          <RelationMiniList
            title={`正相关 Top · ${relWindow}`}
            rows={relations.data?.positive || []}
            dateQuery={date || undefined}
          />
          <RelationMiniList
            title={`负相关 Top · ${relWindow}`}
            rows={relations.data?.negative || []}
            dateQuery={date || undefined}
          />
          {(relations.data?.positive.length || relations.data?.negative.length) ? (
            <button
              type="button"
              className="btn"
              style={{ width: "100%" }}
              onClick={() => setTab("relations")}
            >
              查看全部关联
            </button>
          ) : null}
          <div className="panel">
            <div className="panel-head">窗口高亮</div>
            <div style={{ padding: "0.75rem 1rem" }}>
              {ranges ? (
                <pre className="mono" style={{ margin: 0, fontSize: 12 }}>
                  {JSON.stringify(ranges, null, 2)}
                </pre>
              ) : (
                <span className="muted">评估后显示 platform / breakout 区间</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
