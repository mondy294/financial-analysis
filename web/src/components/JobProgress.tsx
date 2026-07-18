import type { Job } from "@/api/client";

type Props = {
  jobId: string | null;
  job?: Job | null;
  title?: string;
};

/** 扫描/任务进度条：依赖外部对 job 的轮询（progress + message）。 */
export function JobProgress({ jobId, job, title = "任务进度" }: Props) {
  if (!jobId) return null;
  const status = job?.status || "…";
  const pct = Math.round(Math.max(0, Math.min(1, job?.progress ?? 0)) * 100);
  const running = status === "PENDING" || status === "RUNNING";
  const badge =
    status === "SUCCESS" ? "ok" : status === "FAILED" ? "fail" : "warn";

  return (
    <div className="job-progress panel" style={{ marginBottom: "1rem" }}>
      <div className="panel-head" style={{ justifyContent: "space-between" }}>
        <span>
          {title}{" "}
          <span className="mono muted" style={{ fontWeight: 400 }}>
            {jobId}
          </span>
        </span>
        <span className={`badge ${badge}`}>{status}</span>
      </div>
      <div style={{ padding: "0.75rem 1rem" }}>
        <div className="job-progress-track">
          <div
            className={`job-progress-fill${running ? " is-running" : ""}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div
          className="muted"
          style={{
            marginTop: "0.45rem",
            display: "flex",
            justifyContent: "space-between",
            gap: "0.75rem",
            fontSize: "0.86rem",
          }}
        >
          <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
            {job?.message || (running ? "排队/启动中…" : "—")}
          </span>
          <span className="mono" style={{ flexShrink: 0 }}>
            {pct}%
          </span>
        </div>
        {job?.error ? <div className="error-box" style={{ marginTop: "0.6rem" }}>{job.error}</div> : null}
        {status === "SUCCESS" && job?.result && typeof job.result === "object" ? (
          <p className="muted" style={{ margin: "0.5rem 0 0", fontSize: "0.82rem" }}>
            {summarizeResult(job.result as Record<string, unknown>)}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function summarizeResult(result: Record<string, unknown>): string {
  const parts: string[] = [];
  if (result.skipped) parts.push("已跳过（当日已有成功扫描）");
  if (typeof result.universe_size === "number") {
    parts.push(`宇宙 ${result.universe_size}`);
  }
  const per = result.per_pattern;
  if (Array.isArray(per) && per.length) {
    for (const p of per) {
      const row = p as { pattern_id?: string; matched_count?: number; written?: number };
      parts.push(
        `${row.pattern_id || "?"} 命中 ${row.matched_count ?? "—"} / 写入 ${row.written ?? "—"}`,
      );
    }
  }
  if (typeof result.matched_count === "number") {
    parts.push(`命中 ${result.matched_count}`);
  }
  if (typeof result.duration_ms === "number") {
    parts.push(`${(result.duration_ms / 1000).toFixed(1)}s`);
  }
  return parts.join(" · ") || "完成";
}
