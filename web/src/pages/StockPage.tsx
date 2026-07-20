import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type PatternEval, type WindowRange } from "@/api/client";
import { EvalMetricsTable } from "@/components/EvalMetricsTable";
import { KlineChart } from "@/components/KlineChart";
import { ParentProfitChart } from "@/components/ParentProfitChart";
import { RelationList, RelationMiniList } from "@/components/RelationList";
import { isWatched, subscribeWatchlist, toggleWatch } from "@/lib/watchlist";
import {
  clearStockNote,
  getStockNote,
  setStockNote,
  subscribeStockNotes,
} from "@/lib/stockNotes";

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
  const patternId = (params.get("pattern") || "RANGE_BREAKOUT").toUpperCase();
  const [tab, setTab] = useState<"features" | "eval" | "hits" | "relations">("features");
  const [relWindow, setRelWindow] = useState("W60");
  const [evalResult, setEvalResult] = useState<PatternEval | null>(null);
  /** 用户主动点评估后，才用现场结果覆盖榜单窗口；自动 eval=1 仍以落库命中为准 */
  const [preferEvalRanges, setPreferEvalRanges] = useState(false);
  const [showFairPrice, setShowFairPrice] = useState(false);
  const [watched, setWatched] = useState(() => isWatched(code));
  const [noteText, setNoteText] = useState(() => getStockNote(code)?.text || "");
  const [noteDraft, setNoteDraft] = useState(() => getStockNote(code)?.text || "");
  const [noteEditing, setNoteEditing] = useState(false);
  const [noteUpdatedAt, setNoteUpdatedAt] = useState(
    () => getStockNote(code)?.updated_at || "",
  );

  useEffect(() => {
    setWatched(isWatched(code));
    return subscribeWatchlist(() => setWatched(isWatched(code)));
  }, [code]);

  useEffect(() => {
    const sync = () => {
      const n = getStockNote(code);
      setNoteText(n?.text || "");
      setNoteUpdatedAt(n?.updated_at || "");
      if (!noteEditing) setNoteDraft(n?.text || "");
    };
    sync();
    return subscribeStockNotes(sync);
  }, [code, noteEditing]);

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
  const financials = useQuery({
    // v6：近五年年报/中报/季报 + 中报预告 + 公告日PE
    queryKey: ["stock-financials", code, 5, "with-pe"],
    queryFn: () => api.financials(code, 5),
    enabled: !!code,
    staleTime: 30 * 60 * 1000,
  });
  /** 与披露页同源的财务公告；带上 URL date 以覆盖跳转日那条 */
  const stockNotices = useQuery({
    queryKey: ["stock-disclosures", code, date || ""],
    queryFn: () => api.stockDisclosures(code, date || undefined, 21),
    enabled: !!code,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const fairAnchor = useQuery({
    queryKey: ["earnings-fair-anchor", code],
    queryFn: () => api.earningsFairAnchor(code, 5),
    enabled: !!code,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const catalog = useQuery({ queryKey: ["feature-catalog"], queryFn: api.featureCatalog });

  useEffect(() => {
    setShowFairPrice(false);
  }, [code]);
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
        pattern_id: patternId,
      }),
    onSuccess: (r) => {
      setEvalResult(r);
      setTab("eval");
    },
  });

  useEffect(() => {
    setPreferEvalRanges(false);
    setEvalResult(null);
  }, [code, date, patternId]);

  useEffect(() => {
    if (params.get("eval") === "1" && code) {
      evalMut.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, patternId, date]);

  const patternHit = useMemo(() => {
    const list = hits.data || [];
    return list.find((h) => h.pattern_id === patternId) || list[0] || null;
  }, [hits.data, patternId]);

  const ranges: Record<string, WindowRange> | null = useMemo(() => {
    // 榜单落库窗口优先，保证与列表页一致；仅手动评估后才切到现场窗口
    if (
      preferEvalRanges &&
      evalResult?.pattern_id === patternId &&
      evalResult.chosen_window_ranges &&
      Object.keys(evalResult.chosen_window_ranges).length
    ) {
      return evalResult.chosen_window_ranges;
    }
    return patternHit?.chosen_window_ranges || null;
  }, [preferEvalRanges, evalResult, patternId, patternHit]);

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
            {detail.data?.market_cap != null
              ? ` · 市值 ${detail.data.market_cap.toFixed(1)} 亿`
              : ""}
            {detail.data?.pe_ttm != null
              ? ` · PE(TTM) ${detail.data.pe_ttm.toFixed(2)}`
              : ""}
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
          <button
            type="button"
            className={watched ? "btn primary" : "btn"}
            title={watched ? "从自选移除" : "加入自选"}
            onClick={() => {
              const next = toggleWatch(code, detail.data?.name);
              setWatched(next);
            }}
          >
            {watched ? "已自选" : "加自选"}
          </button>
          <label>
            评估日
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <button
            className="btn primary"
            type="button"
            disabled={evalMut.isPending}
            onClick={() => {
              setPreferEvalRanges(true);
              evalMut.mutate();
            }}
          >
            {evalMut.isPending ? "评估中…" : `${patternId} 评估`}
          </button>
          <Link
            className="btn"
            to={`/patterns/eval?code=${code}&date=${date}&pattern=${patternId}`}
          >
            评估页
          </Link>
          {fairAnchor.data?.available && fairAnchor.data.fair_price != null ? (
            <button
              type="button"
              className="btn"
              title={
                fairAnchor.data.event?.event_date
                  ? `${fairAnchor.data.event.event_date} 业绩 · 溢价 ${
                      fairAnchor.data.premium_pct != null
                        ? `${(fairAnchor.data.premium_pct * 100).toFixed(1)}%`
                        : "—"
                    }`
                  : "相对历史公允盈利收益率的隐含价格"
              }
              onClick={() => setShowFairPrice((v) => !v)}
              style={
                showFairPrice
                  ? { outline: "1px solid #b45309", color: "#b45309" }
                  : undefined
              }
            >
              {showFairPrice ? "隐藏合理价" : "图表合理价"}
            </button>
          ) : null}
        </div>
      </div>

      <div
        className="panel"
        style={{
          marginTop: 0,
          marginBottom: "0.85rem",
          borderColor: noteText
            ? "color-mix(in srgb, #2563eb 35%, var(--border))"
            : undefined,
          background: noteText
            ? "color-mix(in srgb, #2563eb 6%, transparent)"
            : undefined,
        }}
      >
        <div className="panel-head" style={{ alignItems: "center" }}>
          <span>备注</span>
          <span style={{ marginLeft: "auto", display: "flex", gap: "0.4rem" }}>
            {noteEditing ? (
              <>
                <button
                  type="button"
                  className="btn primary"
                  style={{ padding: "0.15rem 0.55rem" }}
                  onClick={() => {
                    const saved = setStockNote(code, noteDraft);
                    setNoteText(saved?.text || "");
                    setNoteUpdatedAt(saved?.updated_at || "");
                    setNoteDraft(saved?.text || "");
                    setNoteEditing(false);
                  }}
                >
                  保存
                </button>
                <button
                  type="button"
                  className="btn"
                  style={{ padding: "0.15rem 0.55rem" }}
                  onClick={() => {
                    setNoteDraft(noteText);
                    setNoteEditing(false);
                  }}
                >
                  取消
                </button>
                {noteText ? (
                  <button
                    type="button"
                    className="btn danger"
                    style={{ padding: "0.15rem 0.55rem" }}
                    onClick={() => {
                      clearStockNote(code);
                      setNoteText("");
                      setNoteDraft("");
                      setNoteUpdatedAt("");
                      setNoteEditing(false);
                    }}
                  >
                    清除
                  </button>
                ) : null}
              </>
            ) : (
              <button
                type="button"
                className="btn"
                style={{ padding: "0.15rem 0.55rem" }}
                onClick={() => {
                  setNoteDraft(noteText);
                  setNoteEditing(true);
                }}
              >
                {noteText ? "编辑" : "写备注"}
              </button>
            )}
          </span>
        </div>
        <div style={{ padding: "0.65rem 1rem 0.85rem" }}>
          {noteEditing ? (
            <textarea
              value={noteDraft}
              onChange={(e) => setNoteDraft(e.target.value)}
              rows={3}
              placeholder="记录对该股的看法、关注点、买卖计划等（仅保存在本机浏览器）"
              style={{
                width: "100%",
                resize: "vertical",
                minHeight: "4.5rem",
                padding: "0.55rem 0.65rem",
                border: "1px solid var(--border)",
                borderRadius: 6,
                background: "var(--bg, #fff)",
                color: "inherit",
                font: "inherit",
                lineHeight: 1.5,
              }}
            />
          ) : noteText ? (
            <p
              style={{
                margin: 0,
                whiteSpace: "pre-wrap",
                lineHeight: 1.55,
                fontSize: "0.95rem",
              }}
            >
              {noteText}
            </p>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              暂无备注。可点右上角「写备注」，内容保存在本机浏览器。
            </p>
          )}
          {!noteEditing && noteUpdatedAt ? (
            <p className="muted" style={{ margin: "0.4rem 0 0", fontSize: "0.78rem" }}>
              更新于 {noteUpdatedAt.slice(0, 19).replace("T", " ")}
            </p>
          ) : null}
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
            <KlineChart
              bars={kline.data}
              features={features.data || []}
              ranges={ranges}
              fairPrice={fairAnchor.data?.fair_price}
              fairPriceVisible={showFairPrice}
              fairPriceTitle={
                fairAnchor.data?.fair_price != null
                  ? `公允 ${fairAnchor.data.fair_price.toFixed(2)}`
                  : "公允价"
              }
            />
          )}
          {showFairPrice && fairAnchor.data?.available && (
            <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.85rem" }}>
              近{fairAnchor.data.lookback_days}日业绩
              {fairAnchor.data.event?.event_date
                ? `（${fairAnchor.data.event.event_date}·${fairAnchor.data.event.event_kind}）`
                : ""}
              ：相对公允盈利收益率，市值约
              {fairAnchor.data.premium_pct != null
                ? `${fairAnchor.data.premium_pct > 0 ? "高估" : "低估"} ${Math.abs(
                    fairAnchor.data.premium_pct * 100,
                  ).toFixed(1)}%`
                : "—"}
              ，隐含合理价{" "}
              <span className="mono">
                {fairAnchor.data.fair_price?.toFixed(2) ?? "—"}
              </span>
              （现价 {fairAnchor.data.ref_close?.toFixed(2) ?? "—"}
              {fairAnchor.data.expected_return_20d != null
                ? ` · 模型20日预期价 ${fairAnchor.data.price_at_expected_20d?.toFixed(2) ?? "—"}`
                : ""}
              ）。口径来自业绩事件分析 Median EY，非投资建议。
            </p>
          )}
          <div className="panel" style={{ marginTop: "0.85rem" }}>
            <div className="panel-head">
              近期财务公告
              {stockNotices.data?.total ? (
                <span className="muted" style={{ fontWeight: 400, marginLeft: "0.4rem" }}>
                  {stockNotices.data.start_date} → {stockNotices.data.end_date} ·{" "}
                  {stockNotices.data.total} 条
                </span>
              ) : null}
            </div>
            <div style={{ padding: "0.65rem 1rem 1rem" }}>
              {stockNotices.isLoading ? (
                <p className="muted" style={{ margin: 0 }}>
                  加载公告…
                </p>
              ) : stockNotices.error ? (
                <p className="muted" style={{ margin: 0 }}>
                  {(stockNotices.error as Error).message || "公告加载失败"}
                </p>
              ) : !(stockNotices.data?.items || []).length ? (
                <p className="muted" style={{ margin: 0 }}>
                  近窗口内暂无财务类公告（与披露页同源；下方财务区另有结构化预告/快报）。
                </p>
              ) : (
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>公告日</th>
                        <th>类别</th>
                        <th>标题</th>
                        <th>链接</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(stockNotices.data?.items || []).map((n) => {
                        const highlight = !!date && n.notice_date === date;
                        return (
                          <tr
                            key={`${n.notice_date}-${n.category}-${n.title}`}
                            style={
                              highlight
                                ? {
                                    background:
                                      "color-mix(in srgb, #f59e0b 14%, transparent)",
                                  }
                                : undefined
                            }
                          >
                            <td className="mono">{n.notice_date}</td>
                            <td>
                              <span className="badge" style={{ fontSize: "0.75rem" }}>
                                {n.category_label}
                              </span>
                            </td>
                            <td>{n.title}</td>
                            <td>
                              {n.url ? (
                                <a href={n.url} target="_blank" rel="noreferrer">
                                  原文
                                </a>
                              ) : (
                                "—"
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
          <div className="panel" style={{ marginTop: "0.85rem" }}>
            <div className="panel-head">近五年主要财务指标</div>
            <div style={{ padding: "0.65rem 1rem 1rem" }}>
              {financials.error ? (
                <p className="muted" style={{ margin: 0 }}>
                  {(financials.error as Error).message || "加载失败"}
                </p>
              ) : (
                <ParentProfitChart
                  points={financials.data?.points || []}
                  loading={financials.isLoading}
                  note={financials.data?.note}
                  guidance={financials.data?.guidance || []}
                />
              )}
            </div>
          </div>
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
                          最终评分 {evalResult.similarity.toFixed(2)} / 阈值 {evalResult.threshold}
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
            <div className="panel-head">报价与估值</div>
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
                <dt>总市值</dt>
                <dd className="mono">
                  {snapshot.data?.market_cap != null
                    ? `${snapshot.data.market_cap.toFixed(2)} 亿`
                    : "—"}
                </dd>
                <dt>流通市值</dt>
                <dd className="mono">
                  {snapshot.data?.float_market_cap != null
                    ? `${snapshot.data.float_market_cap.toFixed(2)} 亿`
                    : "—"}
                </dd>
                <dt>PE(TTM)</dt>
                <dd className="mono">
                  {snapshot.data?.pe_ttm != null ? snapshot.data.pe_ttm.toFixed(2) : "—"}
                </dd>
                <dt>PE(静)</dt>
                <dd className="mono">
                  {snapshot.data?.pe_static != null
                    ? snapshot.data.pe_static.toFixed(2)
                    : "—"}
                </dd>
                <dt>PB</dt>
                <dd className="mono">
                  {snapshot.data?.pb != null ? snapshot.data.pb.toFixed(2) : "—"}
                </dd>
                <dt>PS(TTM)</dt>
                <dd className="mono">
                  {snapshot.data?.ps_ttm != null ? snapshot.data.ps_ttm.toFixed(2) : "—"}
                </dd>
              </dl>
              {snapshot.data?.valuation_date ? (
                <p className="muted" style={{ margin: "0.45rem 0 0", fontSize: "0.75rem" }}>
                  估值数据日 {snapshot.data.valuation_date}
                  {snapshot.data.valuation_date !== snapshot.data.trade_date
                    ? "（按评估日及之前最近一期）"
                    : ""}
                </p>
              ) : (
                <p className="muted" style={{ margin: "0.45rem 0 0", fontSize: "0.75rem" }}>
                  暂无估值；请先跑日频估值更新任务
                </p>
              )}
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
            <div className="panel-head">窗口高亮 · {patternId}</div>
            <div style={{ padding: "0.75rem 1rem" }}>
              {ranges ? (
                <>
                  <p className="muted" style={{ margin: "0 0 0.4rem", fontSize: "0.78rem" }}>
                    {preferEvalRanges && evalResult?.pattern_id === patternId
                      ? "来源：现场评估"
                      : patternHit?.pattern_id === patternId
                        ? "来源：榜单落库命中（与列表一致）"
                        : `来源：命中 ${patternHit?.pattern_id || "—"}`}
                    {patternHit?.chosen_windows
                      ? ` · 长度 ${Object.entries(patternHit.chosen_windows)
                          .map(([k, v]) => `${k}=${v}d`)
                          .join(", ")}`
                      : null}
                  </p>
                  <pre className="mono" style={{ margin: 0, fontSize: 12 }}>
                    {JSON.stringify(ranges, null, 2)}
                  </pre>
                </>
              ) : (
                <span className="muted">暂无窗口；从榜单带 pattern 进入或点评估</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
