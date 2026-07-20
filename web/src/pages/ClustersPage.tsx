import { useEffect, useMemo, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

const PROFILES = [
  { id: "pearson_w60", label: "收益相关 · W60" },
  { id: "pearson_w250", label: "收益相关 · W250" },
];

export function ClustersPage() {
  const [params, setParams] = useSearchParams();
  const profileId = params.get("profile") || "pearson_w60";
  const selectedRaw = params.get("cluster");
  const selected = selectedRaw ? Number(selectedRaw) : null;

  const listQ = useQuery({
    queryKey: ["clusters", profileId],
    queryFn: () => api.clustersList(profileId),
  });
  const detailQ = useQuery({
    queryKey: ["cluster-detail", profileId, selected],
    queryFn: () => api.clusterDetail(selected!, profileId, 200),
    enabled: selected != null && Number.isFinite(selected),
  });

  const run = listQ.data?.run;
  const clusters = listQ.data?.clusters || [];

  const selectedRowRef = useRef<HTMLTableRowElement | null>(null);
  const universe = run?.universe_size || 0;
  const maxSize = useMemo(
    () => (clusters.length ? Math.max(...clusters.map((c) => c.size)) : 0),
    [clusters],
  );
  const maxFrac = universe > 0 ? maxSize / universe : 0;

  useEffect(() => {
    if (selected == null || !clusters.length) return;
    if (!clusters.some((c) => c.cluster_id === selected)) {
      const next = new URLSearchParams(params);
      next.delete("cluster");
      setParams(next, { replace: true });
    }
  }, [clusters, selected, params, setParams]);

  useEffect(() => {
    selectedRowRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected, clusters.length]);

  function setProfile(id: string) {
    const next = new URLSearchParams(params);
    next.set("profile", id);
    next.delete("cluster");
    setParams(next);
  }

  function selectCluster(id: number) {
    const next = new URLSearchParams(params);
    next.set("profile", profileId);
    next.set("cluster", String(id));
    setParams(next);
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>相关簇</h1>
          <p className="muted">
            基于 Similarity Graph 的社区划分（非官方行业）。默认用系统任务「刷新相似度+聚类」。
          </p>
        </div>
        <div className="toolbar">
          <select value={profileId} onChange={(e) => setProfile(e.target.value)}>
            {PROFILES.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {run ? (
        <p className="muted" style={{ marginBottom: "0.75rem" }}>
          快照 {run.calc_date} · {run.n_clusters} 簇 · 边 {run.edge_used} · 模块度{" "}
          {run.modularity?.toFixed(3) ?? "—"} · resolution {run.resolution?.toFixed(2) ?? "—"}
          {maxFrac > 0.25 ? (
            <span className="warn-text"> · 最大簇占比 {(maxFrac * 100).toFixed(0)}%（偏糊）</span>
          ) : null}
        </p>
      ) : (
        <p className="muted">
          暂无簇快照。请在系统页运行 <code>similarity.refresh</code> 或{" "}
          <code>cluster.build</code>。
        </p>
      )}

      <div className="cluster-layout">
        <section className="panel cluster-list-panel">
          <div className="panel-head">簇列表</div>
          <div className="cluster-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>标签</th>
                  <th>规模</th>
                  <th>均相似</th>
                  <th>密度</th>
                </tr>
              </thead>
              <tbody>
                {clusters.map((c) => (
                  <tr
                    key={c.cluster_id}
                    ref={selected === c.cluster_id ? selectedRowRef : undefined}
                    className={selected === c.cluster_id ? "row-active" : undefined}
                    onClick={() => selectCluster(c.cluster_id)}
                  >
                    <td>
                      <div className="cluster-label">{c.label}</div>
                      {c.top_members?.length ? (
                        <div className="cluster-top-members">
                          {c.top_members.slice(0, 4).map((m) => (
                            <Link
                              key={m.code}
                              to={`/stocks/${m.code}`}
                              className="cluster-chip"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {m.name}
                            </Link>
                          ))}
                        </div>
                      ) : null}
                    </td>
                    <td className="mono">{c.size}</td>
                    <td className="mono">
                      {c.avg_internal_similarity != null
                        ? c.avg_internal_similarity.toFixed(3)
                        : "—"}
                    </td>
                    <td className="mono">{c.density != null ? c.density.toFixed(3) : "—"}</td>
                  </tr>
                ))}
                {!clusters.length && (
                  <tr>
                    <td colSpan={4} className="muted">
                      无数据
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel cluster-detail-panel">
          <div className="panel-head">簇详情</div>
          <div className="cluster-scroll">
            {selected == null && <p className="muted">点左侧一行查看成员</p>}
            {selected != null && detailQ.isFetching && !detailQ.data && (
              <p className="muted">加载中…</p>
            )}
            {detailQ.data && (
              <>
                <div className="cluster-detail-head">
                  <h3>{detailQ.data.cluster.label}</h3>
                  <p className="muted">
                    {detailQ.data.cluster.size} 只 · 均相似{" "}
                    {detailQ.data.cluster.avg_internal_similarity?.toFixed(3) ?? "—"} · 代表股{" "}
                    {detailQ.data.cluster.representative_code ? (
                      <Link
                        className="mono"
                        to={`/stocks/${detailQ.data.cluster.representative_code}`}
                      >
                        {detailQ.data.cluster.representative_code}
                      </Link>
                    ) : (
                      "—"
                    )}
                    {" · "}
                    <Link
                      to={`/event-stats?profile=${profileId}&cluster=${detailQ.data.cluster.cluster_id}`}
                    >
                      用此簇做事件统计
                    </Link>
                  </p>
                </div>
                <table className="data">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>股票</th>
                      <th>中心度</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detailQ.data.members.map((m) => (
                      <tr key={m.code}>
                        <td className="mono muted">{m.rank_in_cluster}</td>
                        <td>
                          <Link to={`/stocks/${m.code}`}>
                            <span className="mono">{m.code}</span> {m.name}
                          </Link>
                        </td>
                        <td className="mono">{m.centrality.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
