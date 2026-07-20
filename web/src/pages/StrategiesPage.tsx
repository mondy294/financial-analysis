import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type DefinitionListItem } from "@/api/client";

export function StrategiesPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const defs = useQuery({
    queryKey: ["definitions"],
    queryFn: api.listDefinitions,
    refetchOnMount: "always",
  });
  const [cloneSrc, setCloneSrc] = useState<DefinitionListItem | null>(null);
  const [newId, setNewId] = useState("");
  const [newName, setNewName] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const refreshList = () => {
    qc.invalidateQueries({ queryKey: ["definitions"] });
    qc.invalidateQueries({ queryKey: ["patterns-meta"] });
  };

  const cloneMut = useMutation({
    mutationFn: () =>
      api.cloneDefinition(cloneSrc!.id, {
        new_id: newId.trim() || undefined,
        display_name: newName.trim() || undefined,
      }),
    onSuccess: (data) => {
      setCloneSrc(null);
      setErr(null);
      refreshList();
      navigate(`/strategies/${data.id}`);
    },
    onError: (e: Error) => setErr(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteDefinition(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ["definitions"] });
      const prev = qc.getQueryData<DefinitionListItem[]>(["definitions"]);
      qc.setQueryData<DefinitionListItem[]>(["definitions"], (old) =>
        (old || []).filter((x) => x.id !== id),
      );
      return { prev };
    },
    onSuccess: () => {
      setErr(null);
      refreshList();
    },
    onError: (e: Error, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(["definitions"], ctx.prev);
      setErr(e.message);
      refreshList();
    },
  });

  const openClone = (d: DefinitionListItem) => {
    setCloneSrc(d);
    setNewId(`${d.id}_COPY`);
    setNewName(`${d.display_name} (副本)`);
    setErr(null);
  };

  const onDelete = (d: DefinitionListItem) => {
    if (!window.confirm(`确认删除策略 ${d.id}（${d.display_name}）？此操作不可恢复。`)) {
      return;
    }
    deleteMut.mutate(d.id);
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>策略管理</h1>
          <p className="muted">编辑 Pattern Definition 草稿，发布后正式扫描才生效</p>
        </div>
      </div>

      {defs.isLoading && <div className="muted">加载中…</div>}
      {defs.error && <div className="error-box">{(defs.error as Error).message}</div>}
      {err && !cloneSrc && <div className="error-box">{err}</div>}

      <div className="strategy-cards">
        {(defs.data || []).map((d) => (
          <article key={d.id} className="panel strategy-card">
            <div className="strategy-card-top">
              <h2>
                {d.display_name}
                {d.display_name_en ? (
                  <span className="muted" style={{ fontWeight: 400, fontSize: "0.85em" }}>
                    {" "}
                    / {d.display_name_en}
                  </span>
                ) : null}
              </h2>
              <span className={`pill ${d.status === "published" ? "ok" : ""}`}>{d.status}</span>
            </div>
            <p className="mono muted">{d.id}</p>
            <p className="muted strategy-card-desc">{d.description || "—"}</p>
            <dl className="meta-grid">
              <div>
                <dt>published</dt>
                <dd className="mono">{d.published_version || "—"}</dd>
              </div>
              <div>
                <dt>更新</dt>
                <dd>{d.updated_at ? d.updated_at.slice(0, 19).replace("T", " ") : "—"}</dd>
              </div>
            </dl>
            <div className="toolbar strategy-card-actions">
              <Link className="btn primary" to={`/strategies/${d.id}`}>
                编辑
              </Link>
              <button type="button" className="btn" onClick={() => openClone(d)}>
                复制
              </button>
              {d.published_version ? (
                <Link className="btn" to={`/patterns?pattern=${d.id}`}>
                  去扫描
                </Link>
              ) : (
                <span className="muted" style={{ fontSize: "0.82rem" }}>
                  未发布
                </span>
              )}
              {d.deletable !== false ? (
                <button
                  type="button"
                  className="btn danger"
                  disabled={deleteMut.isPending}
                  onClick={() => onDelete(d)}
                >
                  删除
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>

      {cloneSrc && (
        <div className="modal-backdrop" onClick={() => setCloneSrc(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>复制策略</h3>
            <p className="muted">
              从 <span className="mono">{cloneSrc.id}</span> 复制结构为新草稿；发布前不会参与正式扫描。
            </p>
            <label className="field">
              新策略 ID
              <input
                className="mono"
                value={newId}
                onChange={(e) => setNewId(e.target.value.toUpperCase())}
                placeholder="RANGE_BREAKOUT_COPY"
              />
            </label>
            <label className="field">
              显示名
              <input value={newName} onChange={(e) => setNewName(e.target.value)} />
            </label>
            {err && <div className="error-box">{err}</div>}
            <div className="toolbar">
              <button type="button" className="btn" onClick={() => setCloneSrc(null)}>
                取消
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={cloneMut.isPending}
                onClick={() => cloneMut.mutate()}
              >
                {cloneMut.isPending ? "复制中…" : "复制并编辑"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
