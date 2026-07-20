import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { fmtPct } from "@/lib/eventStatsLabels";

function todayISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

function fmtYi(yuan: number | null | undefined): string {
  if (yuan == null || Number.isNaN(yuan)) return "—";
  const yi = yuan / 1e8;
  const abs = Math.abs(yi);
  if (abs >= 100) return `${yi.toFixed(1)} 亿`;
  if (abs >= 1) return `${yi.toFixed(2)} 亿`;
  if (abs >= 0.01) return `${yi.toFixed(3)} 亿`;
  return `${(yuan / 1e4).toFixed(0)} 万`;
}

function retColor(v: number | null | undefined): string | undefined {
  if (v == null || Number.isNaN(v)) return undefined;
  if (v > 0) return "#c23b22";
  if (v < 0) return "#0b6e4f";
  return undefined;
}

const DIFF_LABELS: Record<string, string> = {
  pe_ttm: "PE(TTM)",
  market_cap: "市值(亿)",
  parent_np_yoy_pct: "归母同比%",
  forecast_pe: "预告PE",
  forecast_ey_pct: "预告盈利收益率%",
};

export function DisclosureFactorPage() {
  const [sp, setSp] = useSearchParams();
  const start = sp.get("start_date") || sp.get("start") || "2026-07-15";
  const end = sp.get("end_date") || sp.get("end") || start;
  const mainOnly = sp.get("main") !== "0";
  const [enabled, setEnabled] = useState(true);

  const patch = (next: Record<string, string | null>) => {
    const n = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(next)) {
      if (v == null || v === "") n.delete(k);
      else n.set(k, v);
    }
    setSp(n, { replace: true });
  };

  const q = useQuery({
    queryKey: ["disclosure-factor-analysis", start, end, mainOnly],
    queryFn: () =>
      api.disclosuresFactorAnalysis({
        startDate: start,
        endDate: end,
        mainOnly,
      }),
    enabled: enabled && !!start && !!end,
    staleTime: 60_000,
  });

  const data = q.data;
  const maxAbsStd = useMemo(() => {
    const coefs = data?.coefficients || [];
    if (!coefs.length) return 1;
    return Math.max(...coefs.map((c) => Math.abs(c.std_coef)), 0.01);
  }, [data?.coefficients]);

  const sortedRows = useMemo(() => {
    const rows = [...(data?.rows || [])];
    rows.sort((a, b) => a.return_pct - b.return_pct);
    return rows;
  }, [data?.rows]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>中报预告因子分析</h1>
          <p className="muted">
            半年归母×2 年化后算预告盈利收益率；OLS 拟合公告后至今涨跌幅（百分点）。
            标准化系数负号表示该因素越高越偏跌。
          </p>
        </div>
        <div className="toolbar">
          <Link
            className="btn"
            to={`/disclosures?start=${start}&end=${end}${mainOnly ? "&main=1" : ""}`}
          >
            返回披露
          </Link>
          <label>
            开始
            <input
              type="date"
              value={start}
              onChange={(e) => {
                const v = e.target.value || todayISO();
                if (v > end) patch({ start_date: v, end_date: v, start: null, end: null });
                else patch({ start_date: v, start: null });
              }}
            />
          </label>
          <label>
            结束
            <input
              type="date"
              value={end}
              onChange={(e) => {
                const v = e.target.value || todayISO();
                if (v < start) patch({ start_date: v, end_date: v, start: null, end: null });
                else patch({ end_date: v, end: null });
              }}
            />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <input
              type="checkbox"
              checked={mainOnly}
              onChange={(e) => patch({ main: e.target.checked ? null : "0" })}
            />
            只看主板
          </label>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setEnabled(true);
              void q.refetch();
            }}
          >
            {q.isFetching ? "分析中…" : "运行分析"}
          </button>
        </div>
      </div>

      {q.isError && (
        <p className="muted" style={{ color: "#c23b22" }}>
          {(q.error as Error)?.message || "分析失败"}
        </p>
      )}

      {data && (
        <>
          <div className="cards" style={{ marginBottom: "0.75rem" }}>
            <div className="card">
              <div className="label">有效样本</div>
              <div className="value mono">{data.n}</div>
            </div>
            <div className="card">
              <div className="label">候选 / 剔除</div>
              <div className="value mono">
                {data.candidates} / {data.dropped_n}
              </div>
            </div>
            <div className="card">
              <div className="label">上涨占比</div>
              <div className="value mono">
                {data.groups ? fmtPct(data.groups.up_rate) : "—"}
              </div>
            </div>
            <div className="card">
              <div className="label">R²</div>
              <div className="value mono">
                {data.r_squared == null ? "—" : data.r_squared.toFixed(3)}
              </div>
            </div>
          </div>

          {data.drop_hint && (
            <p className="muted" style={{ marginBottom: "0.75rem" }}>
              {data.drop_hint}
            </p>
          )}
          {!data.ok && data.message && (
            <p className="muted" style={{ color: "#c23b22" }}>
              {data.message}
            </p>
          )}

          {data.formula && (
            <section
              className="card"
              style={{ marginBottom: "1rem", padding: "1rem 1.25rem" }}
            >
              <div className="label" style={{ marginBottom: "0.5rem" }}>
                套用公式（原始尺度）
              </div>
              <pre
                className="mono"
                style={{
                  margin: 0,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  fontSize: "0.95rem",
                  lineHeight: 1.5,
                }}
              >
                {data.formula.text}
              </pre>
              <p className="muted" style={{ marginTop: "0.6rem", marginBottom: 0 }}>
                {data.formula.note}
              </p>
              <button
                type="button"
                className="btn"
                style={{ marginTop: "0.6rem" }}
                onClick={() => void navigator.clipboard?.writeText(data.formula!.text)}
              >
                复制公式
              </button>
            </section>
          )}

          {!!data.coefficients.length && (
            <section style={{ marginBottom: "1.25rem" }}>
              <h2 style={{ fontSize: "1.05rem", marginBottom: "0.5rem" }}>
                标准化系数（可比；负=促跌）
              </h2>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>因素</th>
                      <th>原始系数</th>
                      <th>标准化 β</th>
                      <th>影响方向</th>
                      <th style={{ minWidth: 160 }}>|β|</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...data.coefficients]
                      .sort((a, b) => Math.abs(b.std_coef) - Math.abs(a.std_coef))
                      .map((c) => {
                        const w = (Math.abs(c.std_coef) / maxAbsStd) * 100;
                        const down = c.std_coef < 0;
                        return (
                          <tr key={c.key}>
                            <td>
                              {c.label}
                              <div className="muted mono" style={{ fontSize: "0.75rem" }}>
                                {c.key}
                              </div>
                            </td>
                            <td className="mono">{fmtNum(c.coef, 5)}</td>
                            <td
                              className="mono"
                              style={{ color: retColor(c.std_coef) }}
                            >
                              {fmtNum(c.std_coef, 3)}
                            </td>
                            <td style={{ color: retColor(c.std_coef) }}>
                              {down ? "越高越偏跌" : c.std_coef > 0 ? "越高越偏涨" : "近零"}
                            </td>
                            <td>
                              <div
                                style={{
                                  height: 10,
                                  width: `${w}%`,
                                  background: down ? "#0b6e4f" : "#c23b22",
                                  borderRadius: 2,
                                  minWidth: c.std_coef === 0 ? 0 : 4,
                                }}
                              />
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {data.groups && (
            <section style={{ marginBottom: "1.25rem" }}>
              <h2 style={{ fontSize: "1.05rem", marginBottom: "0.5rem" }}>
                下跌 vs 上涨：均值差（下跌均值 − 上涨均值）
              </h2>
              <p className="muted" style={{ marginTop: 0 }}>
                下跌 {data.groups.down_n} 只 / 上涨 {data.groups.up_n} 只
                {data.groups.flat_n ? ` / 平盘 ${data.groups.flat_n}` : ""}。
                正差表示下跌组该指标更高。
              </p>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>指标</th>
                      <th>下跌组均值</th>
                      <th>上涨组均值</th>
                      <th>差（跌−涨）</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.keys(DIFF_LABELS).map((k) => (
                      <tr key={k}>
                        <td>{DIFF_LABELS[k]}</td>
                        <td className="mono">
                          {fmtNum(data.groups!.down_means[k], 2)}
                        </td>
                        <td className="mono">
                          {fmtNum(data.groups!.up_means[k], 2)}
                        </td>
                        <td
                          className="mono"
                          style={{
                            color: retColor(data.groups!.diff_down_minus_up[k]),
                          }}
                        >
                          {fmtNum(data.groups!.diff_down_minus_up[k], 2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {!!sortedRows.length && (
            <section>
              <h2 style={{ fontSize: "1.05rem", marginBottom: "0.5rem" }}>
                样本明细（按公告后涨幅升序）
              </h2>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>代码</th>
                      <th>名称</th>
                      <th>公告日</th>
                      <th>PE(TTM)</th>
                      <th>市值(亿)</th>
                      <th>半年归母</th>
                      <th>年化归母</th>
                      <th>预告PE</th>
                      <th>同比%</th>
                      <th>盈利收益率%</th>
                      <th>公告后涨幅</th>
                      <th>拟合涨幅</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRows.map((r) => (
                      <tr key={`${r.code}-${r.notice_date}`}>
                        <td className="mono">
                          <Link to={`/stocks/${r.code}?date=${r.notice_date}`}>
                            {r.code}
                          </Link>
                        </td>
                        <td>{r.name}</td>
                        <td className="mono">{r.notice_date}</td>
                        <td className="mono">{fmtNum(r.pe_ttm, 1)}</td>
                        <td className="mono">{fmtNum(r.market_cap, 1)}</td>
                        <td className="mono">{fmtYi(r.parent_np_h1)}</td>
                        <td className="mono">{fmtYi(r.parent_np_annualized)}</td>
                        <td className="mono">{fmtNum(r.forecast_pe, 1)}</td>
                        <td
                          className="mono"
                          style={{ color: retColor(r.parent_np_yoy) }}
                        >
                          {fmtPct(r.parent_np_yoy)}
                        </td>
                        <td className="mono">{fmtNum(r.forecast_ey_pct, 2)}</td>
                        <td
                          className="mono"
                          style={{ color: retColor(r.return_pct) }}
                        >
                          {fmtPct(r.return_since_notice)}
                        </td>
                        <td
                          className="mono"
                          style={{ color: retColor(r.fitted_return_pct) }}
                        >
                          {r.fitted_return_pct == null
                            ? "—"
                            : `${r.fitted_return_pct.toFixed(2)}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}

      {!data && !q.isFetching && !q.isError && (
        <p className="muted">选择日期后点击「运行分析」。</p>
      )}
    </>
  );
}
