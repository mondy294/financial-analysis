import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Job } from "@/api/client";
import { JobProgress } from "@/components/JobProgress";

function fmt(v: number | null | undefined, d = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(d);
}

function pct(v: number | null | undefined, d = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(d)}%`;
}

function retColor(v: number | null | undefined): string | undefined {
  if (v == null || Number.isNaN(v)) return undefined;
  if (v > 0) return "#c23b22";
  if (v < 0) return "#0b6e4f";
  return undefined;
}

const SCOPES = [
  { id: "all", label: "综合" },
  { id: "interim", label: "仅中报" },
  { id: "annual", label: "仅年报" },
] as const;

export function EarningsEventsPage() {
  const qc = useQueryClient();
  const [scope, setScope] = useState<string>("all");
  const [useCluster, setUseCluster] = useState(false);
  const [code, setCode] = useState("");
  const [eventKind, setEventKind] = useState("interim");
  const [parentNpYi, setParentNpYi] = useState("");
  const [yoyPct, setYoyPct] = useState("");
  const [asOf, setAsOf] = useState("");
  const [buildStart, setBuildStart] = useState("2026-07-01");
  const [buildEnd, setBuildEnd] = useState("2026-07-15");
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobTitle, setJobTitle] = useState("任务进度");

  const modelsQ = useQuery({
    queryKey: ["eea-models"],
    queryFn: () => api.eeaModels(),
  });
  const summaryQ = useQuery({
    queryKey: ["eea-panel-summary"],
    queryFn: () => api.eeaPanelSummary(),
  });
  const clusterQ = useQuery({
    queryKey: ["eea-panel-cluster"],
    queryFn: () => api.eeaPanelByCluster(),
  });

  const jobQ = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      if (s === "SUCCESS" || s === "FAILED" || s === "CANCELLED") return false;
      return 800;
    },
  });

  useEffect(() => {
    const j = jobQ.data;
    if (!j) return;
    if (j.status === "SUCCESS") {
      void qc.invalidateQueries({ queryKey: ["eea-models"] });
      void qc.invalidateQueries({ queryKey: ["eea-panel-summary"] });
      void qc.invalidateQueries({ queryKey: ["eea-panel-cluster"] });
    }
  }, [jobQ.data?.status, jobQ.data?.job_id, qc]);

  const buildMut = useMutation({
    mutationFn: () =>
      api.runSystemTask("eea.build_panel", {
        start_date: buildStart,
        end_date: buildEnd,
        build_events: true,
        main_only: true,
        panel_tag: "default",
      }),
    onSuccess: (job) => {
      setJobTitle("构建事件 + Panel");
      setJobId(job.job_id);
    },
  });
  const fitMut = useMutation({
    mutationFn: () =>
      api.runSystemTask("eea.fit", {
        panel_tag: "default",
        scopes: "all,interim,annual",
        cluster_modes: "none,fixed_effect,per_cluster",
      }),
    onSuccess: (job) => {
      setJobTitle("拟合模型");
      setJobId(job.job_id);
    },
  });
  const scoreMut = useMutation({
    mutationFn: () => {
      const yi = Number(parentNpYi);
      if (!code.trim() || !Number.isFinite(yi)) {
        throw new Error("请填写代码与归母净利润（亿元）");
      }
      const yoy = yoyPct.trim() === "" ? null : Number(yoyPct) / 100;
      return api.eeaScore({
        code: code.trim(),
        event_kind: eventKind,
        parent_np: yi * 1e8,
        parent_np_yoy: yoy,
        as_of: asOf || null,
        model_scope: scope,
        use_cluster: useCluster,
      });
    },
  });

  const scopeModels = useMemo(() => {
    const rows = modelsQ.data || [];
    return rows.filter((m) => m.model_scope === scope && m.cluster_mode === "none");
  }, [modelsQ.data, scope]);

  const result = scoreMut.data;
  const job: Job | null = jobQ.data || null;
  const jobBusy =
    buildMut.isPending ||
    fitMut.isPending ||
    (!!job && (job.status === "PENDING" || job.status === "RUNNING"));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>业绩事件分析</h1>
          <p className="muted">
            Earnings Event Analytics：综合 / 中报 / 年报模型；可选分簇；输出 5/10/20
            日预期与高估低估幅度。
          </p>
        </div>
        <div className="toolbar">
          <Link className="btn" to="/disclosures">
            披露日历
          </Link>
          <Link className="btn" to="/disclosures/analyze">
            短窗因子
          </Link>
        </div>
      </div>

      <JobProgress
        jobId={jobId}
        job={job}
        title={jobTitle}
        pending={buildMut.isPending || fitMut.isPending}
        cancellable
        configSummary={
          job?.params
            ? Object.entries(job.params)
                .map(([k, v]) => `${k}=${String(v)}`)
                .join(" · ")
            : undefined
        }
      />

      <section className="card" style={{ padding: "1rem", marginBottom: "1rem" }}>
        <div className="label" style={{ marginBottom: "0.5rem" }}>
          数据管道（后台任务，带进度）
        </div>
        <div className="toolbar" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
          <label>
            开始
            <input
              type="date"
              value={buildStart}
              onChange={(e) => setBuildStart(e.target.value)}
            />
          </label>
          <label>
            结束
            <input type="date" value={buildEnd} onChange={(e) => setBuildEnd(e.target.value)} />
          </label>
          <button
            type="button"
            className="btn"
            disabled={jobBusy}
            onClick={() => buildMut.mutate()}
          >
            {buildMut.isPending ? "提交中…" : "构建事件+Panel"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={jobBusy}
            onClick={() => fitMut.mutate()}
          >
            {fitMut.isPending ? "提交中…" : "拟合模型"}
          </button>
        </div>
        {(buildMut.isError || fitMut.isError) && (
          <p className="muted" style={{ color: "#c23b22" }}>
            {((buildMut.error || fitMut.error) as Error).message}
          </p>
        )}
        {summaryQ.data && (
          <p className="muted" style={{ marginBottom: 0 }}>
            Panel 行数 {summaryQ.data.n_rows}；含 20 日收益 {summaryQ.data.n_with_ret_20d}；含
            EY {summaryQ.data.n_with_ey}
          </p>
        )}
      </section>

      <div className="cards" style={{ marginBottom: "1rem" }}>
        {SCOPES.map((s) => {
          const m = (modelsQ.data || []).find(
            (x) => x.model_scope === s.id && x.cluster_mode === "none",
          );
          return (
            <button
              key={s.id}
              type="button"
              className="card"
              onClick={() => setScope(s.id)}
              style={{
                textAlign: "left",
                cursor: "pointer",
                outline: scope === s.id ? "1px solid var(--accent, #0b6e4f)" : undefined,
              }}
            >
              <div className="label">{s.label}</div>
              <div className="value mono" style={{ fontSize: "0.95rem" }}>
                {m ? `n=${m.n_samples}` : "未拟合"}
              </div>
              <div className="muted mono" style={{ fontSize: "0.75rem" }}>
                R²₂₀ {m?.metrics?.r2_20d != null ? Number(m.metrics.r2_20d).toFixed(3) : "—"}
              </div>
            </button>
          );
        })}
      </div>

      <section className="card" style={{ padding: "1rem", marginBottom: "1rem" }}>
        <div className="label" style={{ marginBottom: "0.5rem" }}>
          单票打分（当前 scope：{SCOPES.find((s) => s.id === scope)?.label}）
        </div>
        <div className="toolbar" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
          <label>
            代码
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="600000" />
          </label>
          <label>
            类型
            <select value={eventKind} onChange={(e) => setEventKind(e.target.value)}>
              <option value="interim">中报</option>
              <option value="annual">年报</option>
              <option value="forecast">预告</option>
              <option value="express">快报</option>
              <option value="q1">一季报</option>
              <option value="q3">三季报</option>
            </select>
          </label>
          <label>
            归母净利润（亿）
            <input
              value={parentNpYi}
              onChange={(e) => setParentNpYi(e.target.value)}
              placeholder="12.5"
            />
          </label>
          <label>
            同比%
            <input value={yoyPct} onChange={(e) => setYoyPct(e.target.value)} placeholder="15" />
          </label>
          <label>
            as_of
            <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <input
              type="checkbox"
              checked={useCluster}
              onChange={(e) => setUseCluster(e.target.checked)}
            />
            考虑所在簇
          </label>
          <button
            type="button"
            className="btn"
            disabled={scoreMut.isPending || jobBusy}
            onClick={() => scoreMut.mutate()}
          >
            {scoreMut.isPending ? "计算中…" : "打分"}
          </button>
        </div>
        {!scopeModels.length && (
          <p className="muted">当前 scope 尚无模型，请先构建 Panel 并拟合。</p>
        )}
        {scoreMut.isError && (
          <p className="muted" style={{ color: "#c23b22" }}>
            {(scoreMut.error as Error).message}
          </p>
        )}
        {result && !result.ok && (
          <p className="muted" style={{ color: "#c23b22" }}>
            无法打分：{result.unavailable_reason}
          </p>
        )}
        {result?.ok && result.prediction && (
          <div style={{ marginTop: "0.75rem" }}>
            <div className="cards">
              <div className="card">
                <div className="label">预期 5 日</div>
                <div
                  className="value mono"
                  style={{ color: retColor(result.prediction.expected_return_5d) }}
                >
                  {fmt(result.prediction.expected_return_5d)} ppt
                </div>
              </div>
              <div className="card">
                <div className="label">预期 10 日</div>
                <div
                  className="value mono"
                  style={{ color: retColor(result.prediction.expected_return_10d) }}
                >
                  {fmt(result.prediction.expected_return_10d)} ppt
                </div>
              </div>
              <div className="card">
                <div className="label">预期 20 日</div>
                <div
                  className="value mono"
                  style={{ color: retColor(result.prediction.expected_return_20d) }}
                >
                  {fmt(result.prediction.expected_return_20d)} ppt
                </div>
              </div>
              <div className="card">
                <div className="label">溢价 premium</div>
                <div
                  className="value mono"
                  style={{ color: retColor(result.prediction.premium_pct) }}
                >
                  {pct(result.prediction.premium_pct)}
                </div>
              </div>
              <div className="card">
                <div className="label">mispricing</div>
                <div className="value mono">{fmt(result.score?.mispricing_score, 3)}</div>
              </div>
            </div>
            {result.explain?.natural_language && (
              <p style={{ marginTop: "0.75rem" }}>{result.explain.natural_language}</p>
            )}
            <p className="muted mono" style={{ fontSize: "0.8rem" }}>
              model={String(result.model?.model_id || "")} resolve=
              {String(result.model?.resolve_reason || "")} cluster=
              {String(result.features?.cluster_id ?? "—")}
            </p>
            {!!result.explain?.feature_contributions?.length && (
              <div className="table-wrap" style={{ marginTop: "0.5rem" }}>
                <table className="data">
                  <thead>
                    <tr>
                      <th>因素</th>
                      <th>值</th>
                      <th>系数</th>
                      <th>贡献</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.explain.feature_contributions.map((c) => (
                      <tr key={c.key}>
                        <td>{c.key}</td>
                        <td className="mono">{fmt(c.value, 3)}</td>
                        <td className="mono">{fmt(c.coef, 4)}</td>
                        <td className="mono" style={{ color: retColor(c.contrib) }}>
                          {fmt(c.contrib, 3)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>

      <section style={{ marginBottom: "1.25rem" }}>
        <h2 style={{ fontSize: "1.05rem" }}>簇间业绩反应差异</h2>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>簇</th>
                <th>事件数</th>
                <th>20日上涨占比</th>
                <th>均收益5/10/20</th>
                <th>相对全局超额(20d)</th>
              </tr>
            </thead>
            <tbody>
              {(clusterQ.data?.clusters || []).map((c) => (
                <tr key={c.cluster_id}>
                  <td className="mono">{c.cluster_id}</td>
                  <td className="mono">{c.n}</td>
                  <td className="mono">{pct(c.up_rate_20d)}</td>
                  <td className="mono">
                    {pct(c.mean_ret_5d)} / {pct(c.mean_ret_10d)} / {pct(c.mean_ret_20d)}
                  </td>
                  <td className="mono" style={{ color: retColor(c.excess_ret_20d) }}>
                    {pct(c.excess_ret_20d)}
                  </td>
                </tr>
              ))}
              {!clusterQ.data?.clusters?.length && (
                <tr>
                  <td colSpan={5} className="muted">
                    暂无簇数据（需先构建 Panel 且存在聚类 run）
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
