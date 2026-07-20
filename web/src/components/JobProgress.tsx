import { useMutation } from "@tanstack/react-query";
import { api, type Job } from "@/api/client";

type Props = {
  jobId: string | null;
  job?: Job | null;
  title?: string;
  /** 尚无 jobId（提交中）也展示进度条 */
  pending?: boolean;
  /** 显示取消按钮（协作式取消） */
  cancellable?: boolean;
  onCancelled?: () => void;
  /** 任务配置摘要（离开页面后仍可见） */
  configSummary?: string;
  /** 自定义取消（如按 run_id 取消孤儿任务） */
  onCancelRequest?: () => Promise<unknown>;
  /** 额外提示（如服务重启后进度冻结） */
  hint?: string;
};

/** 扫描/任务进度条：依赖外部对 job 的轮询（progress + message）。 */
export function JobProgress({
  jobId,
  job,
  title = "任务进度",
  pending = false,
  cancellable = false,
  onCancelled,
  configSummary,
  onCancelRequest,
  hint,
}: Props) {
  if (!jobId && !pending) return null;
  const status = job?.status || (pending ? "PENDING" : "…");
  const ratio = Math.max(0, Math.min(1, job?.progress ?? (pending ? 0.02 : 0)));
  const pct = ratio * 100;
  const pctLabel = pct.toFixed(3);
  const running = status === "PENDING" || status === "RUNNING" || pending;
  const badge =
    status === "SUCCESS"
      ? "ok"
      : status === "FAILED" || status === "CANCELLED"
        ? "fail"
        : "warn";

  const cancelMut = useMutation({
    mutationFn: () =>
      onCancelRequest ? onCancelRequest() : api.cancelJob(jobId!),
    onSuccess: () => onCancelled?.(),
  });

  const canCancel =
    cancellable &&
    !!jobId &&
    (status === "PENDING" || status === "RUNNING") &&
    !job?.cancel_requested &&
    !cancelMut.isPending;

  return (
    <div className="job-progress panel" style={{ marginBottom: "1rem" }}>
      <div className="panel-head" style={{ justifyContent: "space-between" }}>
        <span>
          {title}{" "}
          <span className="mono muted" style={{ fontWeight: 400 }}>
            {jobId || "提交中…"}
          </span>
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {canCancel ? (
            <button
              type="button"
              className="btn"
              onClick={() => cancelMut.mutate()}
            >
              取消任务
            </button>
          ) : null}
          {job?.cancel_requested && running ? (
            <span className="muted" style={{ fontSize: "0.82rem" }}>
              取消中…
            </span>
          ) : null}
          <span className={`badge ${badge}`}>
            {status === "CANCELLED" ? "已取消" : status}
          </span>
        </span>
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
            {job?.message || (pending && !jobId ? "提交任务…" : running ? "排队/启动中…" : "—")}
          </span>
          <span className="mono" style={{ flexShrink: 0 }}>
            {pctLabel}%
          </span>
        </div>
        {configSummary ? (
          <p className="muted" style={{ margin: "0.4rem 0 0", fontSize: "0.82rem" }}>
            {configSummary}
          </p>
        ) : null}
        {hint ? (
          <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.82rem", color: "var(--warn, #b45309)" }}>
            {hint}
          </p>
        ) : null}
        {job?.error ? <div className="error-box" style={{ marginTop: "0.6rem" }}>{job.error}</div> : null}
        {cancelMut.error ? (
          <div className="error-box" style={{ marginTop: "0.6rem" }}>
            {(cancelMut.error as Error).message}
          </div>
        ) : null}
        {status === "SUCCESS" && job?.result && typeof job.result === "object" ? (
          <p className="muted" style={{ margin: "0.5rem 0 0", fontSize: "0.82rem" }}>
            {summarizeResult(job.result as Record<string, unknown>)}
          </p>
        ) : null}
        {status === "CANCELLED" ? (
          <p className="muted" style={{ margin: "0.5rem 0 0", fontSize: "0.82rem" }}>
            任务已在检查点停止（进行中的当日匹配可能仍会跑完再退出）
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
  if (typeof result.event_count === "number") {
    parts.push(`事件 ${result.event_count}`);
  }
  if (typeof result.duration_ms === "number") {
    parts.push(`${(result.duration_ms / 1000).toFixed(1)}s`);
  }
  return parts.join(" · ") || "完成";
}
