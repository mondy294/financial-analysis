import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type DefinitionBody,
  type FeatureCatalogItem,
  type PatternEval,
  type TargetValueJson,
} from "@/api/client";
import { EvalMetricsTable } from "@/components/EvalMetricsTable";
import { JobProgress } from "@/components/JobProgress";
import { StockPicker } from "@/components/StockPicker";
import { featureLabel, featureOptionText } from "@/lib/featureLabels";

type Sel =
  | { kind: "meta" }
  | { kind: "constraints" }
  | { kind: "stage"; index: number }
  | { kind: "target"; stageIndex: number; name: string }
  | { kind: "relation"; index: number }
  | { kind: "context"; index: number };

/** 普通文本数字框：编辑中可输入小数点/负号，失焦再写入数值（避免 type=number 吞小数）。 */
function PlainNum({
  value,
  onChange,
  allowEmpty = false,
  fallback = 0,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  allowEmpty?: boolean;
  fallback?: number;
}) {
  const fmt = (v: number | null | undefined) =>
    v == null || Number.isNaN(Number(v)) ? "" : String(v);
  const [text, setText] = useState(fmt(value));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setText(fmt(value));
  }, [value, focused]);

  const commit = () => {
    setFocused(false);
    const raw = text.trim();
    if (raw === "" || raw === "-" || raw === "." || raw === "-.") {
      if (allowEmpty) {
        onChange(null);
        setText("");
      } else {
        onChange(fallback);
        setText(String(fallback));
      }
      return;
    }
    const n = Number(raw);
    if (Number.isFinite(n)) {
      onChange(n);
      setText(String(n));
    } else {
      setText(fmt(value));
    }
  };

  return (
    <input
      type="text"
      inputMode="decimal"
      autoComplete="off"
      value={text}
      onFocus={() => setFocused(true)}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
    />
  );
}

type StageRole = "range" | "up" | "down";
type EditorMode = "guided" | "advanced";

const DEFAULT_TARGET: TargetValueJson = {
  ideal: 0,
  tolerance: 0.1,
  weight: 0.1,
  mode: "two_sided",
};

const ROLE_LABEL: Record<StageRole, string> = {
  range: "横盘",
  up: "上涨",
  down: "下跌",
};

const ROLE_DEFAULT_WINDOW: Record<StageRole, { min_length: number; max_length: number }> = {
  range: { min_length: 5, max_length: 10 },
  up: { min_length: 1, max_length: 3 },
  down: { min_length: 3, max_length: 8 },
};

const RELATION_TEMPLATES: Array<{
  id: string;
  feature: string;
  label: string;
  hint: string;
}> = [
  {
    id: "break_prev_high",
    feature: "breakout_distance",
    label: "突破前段高点",
    hint: "当前段收盘相对前段最高价距离",
  },
  {
    id: "hold_prev_high",
    feature: "break_hold_ratio",
    label: "站上前高天数比",
    hint: "当前段收盘仍站上前段高点的占比",
  },
  {
    id: "vol_vs_prev",
    feature: "volume_vs_platform",
    label: "相对前段放量",
    hint: "当前段均量 / 前段均量",
  },
  {
    id: "close_vs_prev_mid",
    feature: "close_vs_platform_mid",
    label: "相对前段中轴",
    hint: "当前段收盘相对前段高低中点",
  },
];

function cloneBody(b: DefinitionBody): DefinitionBody {
  return structuredClone(b);
}

function weightSum(targets: Record<string, TargetValueJson>): number {
  return Object.values(targets).reduce((s, t) => s + (t.weight ?? 0), 0);
}

function inferStageRole(name: string): StageRole | null {
  const n = (name || "").trim().toLowerCase();
  if (["platform", "range", "box", "consolidate"].includes(n) || n.startsWith("range") || n.startsWith("platform")) {
    return "range";
  }
  if (["breakout", "up", "rally"].includes(n) || n.startsWith("up") || n.startsWith("break")) {
    return "up";
  }
  if (["down", "drop", "selloff"].includes(n) || n.startsWith("down")) {
    return "down";
  }
  return null;
}

function stageRoleOf(s: { name: string; role?: StageRole | null }): StageRole | null {
  return s.role ?? inferStageRole(s.name);
}

function nextStageName(
  timeline: DefinitionBody["timeline"],
  role: StageRole,
): string {
  let n = 1;
  const used = new Set(timeline.map((s) => s.name));
  while (used.has(`${role}_${n}`)) n += 1;
  return `${role}_${n}`;
}

function featureVisibleForRole(f: FeatureCatalogItem, role: StageRole | null): boolean {
  if (f.kind !== "stage") return false;
  if (!role) return true;
  if (f.tier === "universal" || !f.tier) return true;
  if (!f.roles || f.roles.includes("all")) return true;
  return f.roles.includes(role);
}

function targetFromCatalog(f: FeatureCatalogItem | undefined): TargetValueJson {
  if (!f?.default_target) return { ...DEFAULT_TARGET };
  return {
    ...DEFAULT_TARGET,
    ...f.default_target,
    mode: (f.default_target.mode as TargetValueJson["mode"]) || DEFAULT_TARGET.mode,
  };
}

function relationStageMap(timeline: DefinitionBody["timeline"], currIndex: number): Record<string, string> {
  const prev = timeline[Math.max(0, currIndex - 1)];
  const curr = timeline[currIndex] || timeline[timeline.length - 1];
  if (!prev || !curr) return {};
  // 兼容现有 relation 公式里的 platform/breakout 角色名
  return { platform: prev.name, breakout: curr.name };
}

export function StrategyEditorPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const defQ = useQuery({
    queryKey: ["definition", id],
    queryFn: () => api.getDefinition(id),
    enabled: !!id,
  });
  const catalogQ = useQuery({
    queryKey: ["feature-catalog"],
    queryFn: api.featureCatalog,
  });
  const dayQ = useQuery({ queryKey: ["trading-day"], queryFn: api.tradingDay });

  const [body, setBody] = useState<DefinitionBody | null>(null);
  const [dirty, setDirty] = useState(false);
  const [sel, setSel] = useState<Sel>({ kind: "meta" });
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editorMode, setEditorMode] = useState<EditorMode>("guided");
  const [addRoleMenu, setAddRoleMenu] = useState(false);

  // debug
  const [dbgMode, setDbgMode] = useState<"eval" | "scan">("eval");
  const [dbgCode, setDbgCode] = useState("");
  const [dbgDate, setDbgDate] = useState("");
  const [dbgLimit, setDbgLimit] = useState(50);
  const [evalResult, setEvalResult] = useState<PatternEval | null>(null);
  const [dryJobId, setDryJobId] = useState<string | null>(null);
  const [addFeatureOpen, setAddFeatureOpen] = useState(false);

  useEffect(() => {
    if (defQ.data?.body) {
      const next = cloneBody(defQ.data.body);
      // 缺 role 时按名称推断，便于引导模式编辑（不立刻标 dirty）
      for (const s of next.timeline) {
        if (!s.role) {
          const inferred = inferStageRole(s.name);
          if (inferred) s.role = inferred;
        }
      }
      setBody(next);
      setDirty(false);
      setSel({ kind: "meta" });
    }
  }, [defQ.data]);

  useEffect(() => {
    if (!dbgDate && dayQ.data?.latest_trading_day) {
      setDbgDate(dayQ.data.latest_trading_day);
    }
  }, [dayQ.data, dbgDate]);

  const catalog = catalogQ.data || [];
  const stageFeatures = useMemo(
    () => catalog.filter((c) => c.kind === "stage"),
    [catalog],
  );
  const relationFeatures = useMemo(
    () => catalog.filter((c) => c.kind === "relation"),
    [catalog],
  );
  const contextFeatures = useMemo(
    () => catalog.filter((c) => c.kind === "context"),
    [catalog],
  );

  const patch = (fn: (b: DefinitionBody) => void) => {
    setBody((prev) => {
      if (!prev) return prev;
      const next = cloneBody(prev);
      fn(next);
      return next;
    });
    setDirty(true);
    setMsg(null);
  };

  const saveMut = useMutation({
    mutationFn: () => {
      if (!body) throw new Error("无 body");
      return api.saveDefinition(id, body);
    },
    onSuccess: (data) => {
      setBody(cloneBody(data.body));
      setDirty(false);
      setMsg("草稿已保存（不影响正式扫描）");
      setErr(null);
      qc.invalidateQueries({ queryKey: ["definitions"] });
      qc.invalidateQueries({ queryKey: ["definition", id] });
      qc.invalidateQueries({ queryKey: ["patterns-meta"] });
    },
    onError: (e: Error) => setErr(e.message),
  });

  const pubMut = useMutation({
    mutationFn: async () => {
      if (!body) throw new Error("无 body");
      if (dirty) await api.saveDefinition(id, body);
      return api.publishDefinition(id);
    },
    onSuccess: (data) => {
      setBody(cloneBody(data.body));
      setDirty(false);
      setMsg(`已发布 ${data.published_version}，下次正式 scan 生效`);
      setErr(null);
      qc.invalidateQueries({ queryKey: ["definitions"] });
      qc.invalidateQueries({ queryKey: ["definition", id] });
      qc.invalidateQueries({ queryKey: ["patterns-meta"] });
    },
    onError: (e: Error) => setErr(e.message),
  });

  const evalMut = useMutation({
    mutationFn: () => {
      if (!body) throw new Error("无 body");
      return api.evalPreview(id, {
        code: dbgCode.trim(),
        trade_date: dbgDate || undefined,
        body,
      });
    },
    onSuccess: setEvalResult,
    onError: (e: Error) => setErr(e.message),
  });

  const dryMut = useMutation({
    mutationFn: () => {
      if (!body) throw new Error("无 body");
      return api.dryScan(id, {
        trade_date: dbgDate || undefined,
        limit: dbgLimit,
        body,
      });
    },
    onSuccess: (job) => setDryJobId(job.job_id),
    onError: (e: Error) => setErr(e.message),
  });

  const dryJob = useQuery({
    queryKey: ["dry-job", dryJobId],
    queryFn: () => api.job(dryJobId!),
    enabled: !!dryJobId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "SUCCESS" || s === "FAILED" ? false : 600;
    },
  });

  if (defQ.isLoading || !body) {
    return <div className="muted">加载策略…</div>;
  }
  if (defQ.error) {
    return <div className="error-box">{(defQ.error as Error).message}</div>;
  }

  const catalogHint = (name: string): FeatureCatalogItem | undefined =>
    catalog.find((c) => c.name === name);

  return (
    <div className="editor-page">
      <div className="page-head">
        <div>
          <h1>
            {body.display_name}
            {body.display_name_en ? (
              <span className="muted" style={{ fontWeight: 400, fontSize: "0.85em" }}>
                {" "}
                / {body.display_name_en}
              </span>
            ) : null}
          </h1>
          <p className="muted">
            <span className="mono">{body.id}</span>
            {" · "}
            published {defQ.data?.published_version || "—"}
            {" · "}
            {dirty ? "未保存草稿" : `来源 ${defQ.data?.source}`}
          </p>
        </div>
        <div className="toolbar">
          <div className="mode-toggle">
            <button
              type="button"
              className={editorMode === "guided" ? "btn primary tiny" : "btn tiny"}
              onClick={() => setEditorMode("guided")}
            >
              引导
            </button>
            <button
              type="button"
              className={editorMode === "advanced" ? "btn primary tiny" : "btn tiny"}
              onClick={() => setEditorMode("advanced")}
            >
              高级
            </button>
          </div>
          <Link className="btn" to="/strategies">
            返回列表
          </Link>
          <Link className="btn" to={`/patterns?pattern=${id}`}>
            去 Pattern
          </Link>
          <button
            className="btn"
            type="button"
            disabled={!dirty || saveMut.isPending}
            onClick={() => saveMut.mutate()}
          >
            {saveMut.isPending ? "保存中…" : "保存草稿"}
          </button>
          <button
            className="btn primary"
            type="button"
            disabled={pubMut.isPending}
            onClick={() => {
              if (
                !window.confirm(
                  "发布将自动 bump 版本，正式扫描将使用新版。草稿试扫不会落库。确认发布？",
                )
              ) {
                return;
              }
              pubMut.mutate();
            }}
          >
            {pubMut.isPending ? "发布中…" : "发布"}
          </button>
        </div>
      </div>

      {msg && <div className="ok-box">{msg}</div>}
      {err && <div className="error-box">{err}</div>}
      <p className="muted" style={{ marginBottom: "0.75rem" }}>
        {editorMode === "guided"
          ? "引导模式：按「横盘 / 上涨 / 下跌」拼时间线，指标池按角色过滤；跨段关系可用模板。"
          : "高级模式：自由命名 Stage，可选全量 Catalog。"}{" "}
        保存草稿不影响扫描；发布后下次正式 scan 才用新版。
      </p>

      <div className="editor-grid">
        <aside className="panel editor-tree">
          <button
            type="button"
            className={sel.kind === "meta" ? "active" : ""}
            onClick={() => setSel({ kind: "meta" })}
          >
            基本信息
          </button>
          <button
            type="button"
            className={sel.kind === "constraints" ? "active" : ""}
            onClick={() => setSel({ kind: "constraints" })}
          >
            硬约束
          </button>
          <div className="tree-section">
            <div className="tree-head">
              <span>{editorMode === "guided" ? "时间线" : "Stages"}</span>
              <div className="tree-head-actions">
                {editorMode === "guided" ? (
                  <div className="role-add-wrap">
                    <button
                      type="button"
                      className="btn tiny"
                      disabled={body.timeline.length >= 3}
                      onClick={() => setAddRoleMenu((v) => !v)}
                    >
                      + 阶段
                    </button>
                    {addRoleMenu && body.timeline.length < 3 && (
                      <div className="role-add-menu">
                        {(Object.keys(ROLE_LABEL) as StageRole[]).map((role) => (
                          <button
                            key={role}
                            type="button"
                            className="btn tiny"
                            onClick={() => {
                              const name = nextStageName(body.timeline, role);
                              patch((b) => {
                                b.timeline.push({
                                  name,
                                  role,
                                  window: { ...ROLE_DEFAULT_WINDOW[role] },
                                  targets: {},
                                });
                                b.stage_weights[name] = 0.3;
                              });
                              setSel({ kind: "stage", index: body.timeline.length });
                              setAddRoleMenu(false);
                            }}
                          >
                            {ROLE_LABEL[role]}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <button
                    type="button"
                    className="btn tiny"
                    disabled={body.timeline.length >= 3}
                    onClick={() => {
                      const name = window.prompt("阶段名", `stage${body.timeline.length + 1}`);
                      if (!name?.trim()) return;
                      if (body.timeline.some((s) => s.name === name.trim())) {
                        setErr("阶段名已存在");
                        return;
                      }
                      patch((b) => {
                        b.timeline.push({
                          name: name.trim(),
                          role: null,
                          window: { min_length: 3, max_length: 8 },
                          targets: {},
                        });
                        b.stage_weights[name.trim()] = 0.3;
                      });
                      setSel({ kind: "stage", index: body.timeline.length });
                    }}
                  >
                    +
                  </button>
                )}
              </div>
            </div>
            {body.timeline.map((s, i) => (
              <div key={s.name} className="tree-block">
                <div className="tree-row">
                  <button
                    type="button"
                    className={sel.kind === "stage" && sel.index === i ? "active" : ""}
                    onClick={() => setSel({ kind: "stage", index: i })}
                  >
                    {editorMode === "guided" && stageRoleOf(s)
                      ? `${ROLE_LABEL[stageRoleOf(s)!]} · ${s.name}`
                      : s.name}
                  </button>
                  <button
                    type="button"
                    className="btn tiny"
                    disabled={i === 0}
                    onClick={() =>
                      patch((b) => {
                        const tmp = b.timeline[i - 1];
                        b.timeline[i - 1] = b.timeline[i];
                        b.timeline[i] = tmp;
                      })
                    }
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="btn tiny"
                    disabled={i >= body.timeline.length - 1}
                    onClick={() =>
                      patch((b) => {
                        const tmp = b.timeline[i + 1];
                        b.timeline[i + 1] = b.timeline[i];
                        b.timeline[i] = tmp;
                      })
                    }
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="btn tiny danger"
                    disabled={body.timeline.length <= 1}
                    onClick={() => {
                      if (!window.confirm(`删除阶段 ${s.name}？`)) return;
                      patch((b) => {
                        b.timeline.splice(i, 1);
                        delete b.stage_weights[s.name];
                        b.relations = b.relations.filter(
                          (r) =>
                            r.attach_to_stage !== s.name &&
                            !Object.values(r.stage_map).includes(s.name),
                        );
                      });
                      setSel({ kind: "meta" });
                    }}
                  >
                    ×
                  </button>
                </div>
                {Object.keys(s.targets).map((tname) => (
                  <button
                    key={tname}
                    type="button"
                    className={
                      sel.kind === "target" &&
                      sel.stageIndex === i &&
                      sel.name === tname
                        ? "active nested"
                        : "nested"
                    }
                    onClick={() => setSel({ kind: "target", stageIndex: i, name: tname })}
                    title={tname}
                  >
                    {featureLabel(tname, catalog)}
                  </button>
                ))}
                <button
                  type="button"
                  className="nested muted-btn"
                  onClick={() => {
                    setSel({ kind: "stage", index: i });
                    setAddFeatureOpen(true);
                  }}
                >
                  + 指标
                </button>
              </div>
            ))}
          </div>
          <div className="tree-section">
            <div className="tree-head">
              <span>Relations</span>
              {editorMode === "guided" && body.timeline.length >= 2 ? (
                <select
                  className="tiny-select"
                  defaultValue=""
                  title="从关系模板添加"
                  onChange={(e) => {
                    const tid = e.target.value;
                    e.target.value = "";
                    if (!tid) return;
                    const tpl = RELATION_TEMPLATES.find((t) => t.id === tid);
                    if (!tpl) return;
                    const currIndex = body.timeline.length - 1;
                    const curr = body.timeline[currIndex];
                    const smap = relationStageMap(body.timeline, currIndex);
                    const feat = catalog.find((c) => c.name === tpl.feature);
                    patch((b) => {
                      b.relations.push({
                        name: tpl.feature,
                        attach_to_stage: curr.name,
                        stage_map: smap,
                        target: targetFromCatalog(feat),
                      });
                    });
                    setSel({ kind: "relation", index: body.relations.length });
                  }}
                >
                  <option value="">+ 模板</option>
                  {RELATION_TEMPLATES.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  ))}
                </select>
              ) : (
                <button
                  type="button"
                  className="btn tiny"
                  disabled={editorMode === "guided" && body.timeline.length < 2}
                  onClick={() => {
                    const name = relationFeatures[0]?.name;
                    if (!name) return;
                    const stage = body.timeline[0]?.name || "platform";
                    patch((b) => {
                      b.relations.push({
                        name,
                        attach_to_stage: stage,
                        stage_map: Object.fromEntries(b.timeline.map((s) => [s.name, s.name])),
                        target: { ...DEFAULT_TARGET },
                      });
                    });
                    setSel({ kind: "relation", index: body.relations.length });
                  }}
                >
                  +
                </button>
              )}
            </div>
            {body.relations.map((r, i) => (
              <div key={`${r.name}-${i}`} className="tree-row">
                <button
                  type="button"
                  className={sel.kind === "relation" && sel.index === i ? "active" : ""}
                  onClick={() => setSel({ kind: "relation", index: i })}
                >
                  {featureLabel(r.name, catalog)}
                </button>
                <button
                  type="button"
                  className="btn tiny danger"
                  onClick={() => {
                    patch((b) => {
                      b.relations.splice(i, 1);
                    });
                    setSel({ kind: "meta" });
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <div className="tree-section">
            <div className="tree-head">
              <span>Context</span>
              <button
                type="button"
                className="btn tiny"
                onClick={() => {
                  const name = contextFeatures[0]?.name;
                  if (!name) return;
                  patch((b) => {
                    b.context_features.push({
                      name,
                      lookback_bars: 252,
                      target: { ...DEFAULT_TARGET },
                    });
                  });
                  setSel({ kind: "context", index: body.context_features.length });
                }}
              >
                +
              </button>
            </div>
            {body.context_features.map((c, i) => (
              <div key={`${c.name}-${i}`} className="tree-row">
                <button
                  type="button"
                  className={sel.kind === "context" && sel.index === i ? "active" : ""}
                  onClick={() => setSel({ kind: "context", index: i })}
                >
                  {featureLabel(c.name, catalog)}
                </button>
                <button
                  type="button"
                  className="btn tiny danger"
                  onClick={() => {
                    patch((b) => {
                      b.context_features.splice(i, 1);
                    });
                    setSel({ kind: "meta" });
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </aside>

        <section className="panel editor-form">
          {sel.kind === "meta" && (
            <MetaForm body={body} patch={patch} />
          )}
          {sel.kind === "constraints" && (
            <ConstraintsForm body={body} patch={patch} />
          )}
          {sel.kind === "stage" && body.timeline[sel.index] && (
            <StageForm
              stage={body.timeline[sel.index]}
              weight={body.stage_weights[body.timeline[sel.index].name] ?? 0}
              guided={editorMode === "guided"}
              onRename={(name) => {
                const old = body.timeline[sel.index].name;
                if (!name.trim() || name === old) return;
                if (body.timeline.some((s) => s.name === name.trim())) {
                  setErr("阶段名已存在");
                  return;
                }
                patch((b) => {
                  const st = b.timeline[sel.index];
                  const w = b.stage_weights[st.name];
                  delete b.stage_weights[st.name];
                  st.name = name.trim();
                  b.stage_weights[st.name] = w ?? 0.3;
                  for (const r of b.relations) {
                    if (r.attach_to_stage === old) r.attach_to_stage = st.name;
                    for (const [k, v] of Object.entries(r.stage_map)) {
                      if (v === old) r.stage_map[k] = st.name;
                      if (k === old) {
                        r.stage_map[st.name] = r.stage_map[k];
                        delete r.stage_map[k];
                      }
                    }
                  }
                });
              }}
              onRole={(role) =>
                patch((b) => {
                  b.timeline[sel.index].role = role;
                })
              }
              onWeight={(w) =>
                patch((b) => {
                  b.stage_weights[b.timeline[sel.index].name] = w;
                })
              }
              onWindow={(min, max) =>
                patch((b) => {
                  b.timeline[sel.index].window = { min_length: min, max_length: max };
                })
              }
            />
          )}
          {sel.kind === "target" && body.timeline[sel.stageIndex]?.targets[sel.name] && (
            <TargetForm
              name={sel.name}
              title={`${featureLabel(sel.name, catalog)} (${sel.name})`}
              target={body.timeline[sel.stageIndex].targets[sel.name]}
              hint={catalogHint(sel.name)?.description}
              stageWeightSum={weightSum(body.timeline[sel.stageIndex].targets)}
              onChange={(t) =>
                patch((b) => {
                  b.timeline[sel.stageIndex].targets[sel.name] = t;
                })
              }
              onDelete={() => {
                patch((b) => {
                  delete b.timeline[sel.stageIndex].targets[sel.name];
                });
                setSel({ kind: "stage", index: sel.stageIndex });
              }}
            />
          )}
          {sel.kind === "relation" && body.relations[sel.index] && (
            <RelationForm
              rel={body.relations[sel.index]}
              stages={body.timeline.map((s) => s.name)}
              features={relationFeatures}
              hint={catalogHint(body.relations[sel.index].name)?.description}
              onChange={(r) =>
                patch((b) => {
                  b.relations[sel.index] = r;
                })
              }
            />
          )}
          {sel.kind === "context" && body.context_features[sel.index] && (
            <ContextForm
              ctx={body.context_features[sel.index]}
              features={contextFeatures}
              hint={catalogHint(body.context_features[sel.index].name)?.description}
              onChange={(c) =>
                patch((b) => {
                  b.context_features[sel.index] = c;
                })
              }
            />
          )}
        </section>

        <aside className="panel editor-help">
          <h3>说明</h3>
          <p className="muted">
            特征公式在 Catalog 中固定；此处只改窗口、目标值与结构。Stage ≤ 3。
            角色（role）只影响编辑与校验，不参与 Matcher 打分。
          </p>
          {sel.kind === "stage" && body.timeline[sel.index] && (
            <p className="muted">
              当前角色：
              {ROLE_LABEL[stageRoleOf(body.timeline[sel.index])!] || "未分类"}
              ；指标池 =
              {editorMode === "guided" ? " 通用 + 该角色专用" : " 全量"}
            </p>
          )}
          {sel.kind === "target" && (
            <p>
              <strong>{featureLabel(sel.name, catalog)}</strong>
              <span className="mono muted" style={{ marginLeft: "0.35rem", fontSize: "0.8rem" }}>
                {sel.name}
              </span>
              <br />
              {catalogHint(sel.name)?.description || "—"}
              {catalogHint(sel.name)?.tier && (
                <>
                  <br />
                  <span className="muted">
                    tier={catalogHint(sel.name)?.tier} · group=
                    {catalogHint(sel.name)?.ui_group}
                  </span>
                </>
              )}
            </p>
          )}
          <details>
            <summary>JSON 预览</summary>
            <pre className="json-preview">{JSON.stringify(body, null, 2)}</pre>
          </details>
        </aside>
      </div>

      {addFeatureOpen && sel.kind === "stage" && (
        <AddFeaturesModal
          guided={editorMode === "guided"}
          role={stageRoleOf(body.timeline[sel.index])}
          features={stageFeatures.filter((f) => {
            if (f.name in (body.timeline[sel.index]?.targets || {})) return false;
            if (editorMode === "guided") {
              return featureVisibleForRole(f, stageRoleOf(body.timeline[sel.index]));
            }
            return true;
          })}
          onClose={() => setAddFeatureOpen(false)}
          onAdd={(names) => {
            patch((b) => {
              for (const n of names) {
                b.timeline[sel.index].targets[n] = targetFromCatalog(
                  catalog.find((c) => c.name === n),
                );
              }
            });
            setAddFeatureOpen(false);
          }}
        />
      )}

      <section className="panel debug-panel">
        <div className="debug-head">
          <h2>调试</h2>
          <div className="toolbar">
            <button
              type="button"
              className={dbgMode === "eval" ? "btn primary" : "btn"}
              onClick={() => setDbgMode("eval")}
            >
              单票试跑
            </button>
            <button
              type="button"
              className={dbgMode === "scan" ? "btn primary" : "btn"}
              onClick={() => setDbgMode("scan")}
            >
              试扫榜单(不落库)
            </button>
          </div>
        </div>
        <p className="muted">试扫结果仅本次有效，不会写入 abnormal_signal</p>
        <div className="toolbar">
          {dbgMode === "eval" && (
            <label>
              股票
              <StockPicker mode="single" value={dbgCode} onChange={setDbgCode} />
            </label>
          )}
          <label>
            交易日
            <input type="date" value={dbgDate} onChange={(e) => setDbgDate(e.target.value)} />
          </label>
          {dbgMode === "scan" && (
            <label>
              TopN
              <PlainNum
                value={dbgLimit}
                fallback={50}
                onChange={(n) => setDbgLimit(Math.max(1, Math.min(500, n ?? 50)))}
              />
            </label>
          )}
          {dbgMode === "eval" ? (
            <button
              className="btn primary"
              type="button"
              disabled={!dbgCode.trim() || evalMut.isPending}
              onClick={() => {
                setErr(null);
                evalMut.mutate();
              }}
            >
              {evalMut.isPending ? "试跑中…" : "试跑"}
            </button>
          ) : (
            <button
              className="btn primary"
              type="button"
              disabled={dryMut.isPending}
              onClick={() => {
                setErr(null);
                dryMut.mutate();
              }}
            >
              {dryMut.isPending ? "提交中…" : "开始试扫"}
            </button>
          )}
        </div>

        {dbgMode === "eval" && evalResult && (
          <div className="eval-result">
            <p>
              <strong>{evalResult.matched ? "命中" : "未命中"}</strong>
              {" · 最终评分 "}
              {evalResult.similarity.toFixed(1)} / 阈值 {evalResult.threshold}
              {" · v "}
              {evalResult.version}
              {evalResult.hard_failed?.length ? (
                <span className="warn-text"> · hard_failed: {evalResult.hard_failed.join(", ")}</span>
              ) : null}
            </p>
            <p className="muted mono">
              {Object.entries(evalResult.chosen_window_ranges || {})
                .map(([k, r]) => `${k} ${r.start}→${r.end}`)
                .join(" · ")}
            </p>
            <Link
              to={`/stocks/${evalResult.code}?date=${evalResult.trade_date}`}
              className="btn"
            >
              在 K 线页打开
            </Link>
            <div style={{ marginTop: "0.75rem" }}>
              <EvalMetricsTable result={evalResult} catalog={catalog} />
            </div>
          </div>
        )}

        {dbgMode === "scan" && dryJobId && (
          <div style={{ marginTop: "0.75rem" }}>
            <JobProgress jobId={dryJobId} job={dryJob.data} title="试扫进度" />
            {dryJob.data?.status === "SUCCESS" && dryJob.data.result && (
              <DryHitsTable
                hits={
                  (dryJob.data.result.hits as Array<{
                    rank: number;
                    code: string;
                    name: string;
                    pattern_score: number;
                    chosen_window_ranges?: Record<string, { start: string; end: string }>;
                  }>) || []
                }
                onOpenEval={(code) => {
                  setDbgMode("eval");
                  setDbgCode(code);
                  setTimeout(() => evalMut.mutate(), 0);
                }}
              />
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function MetaForm({
  body,
  patch,
}: {
  body: DefinitionBody;
  patch: (fn: (b: DefinitionBody) => void) => void;
}) {
  return (
    <>
      <h3>基本信息</h3>
      <label className="field">
        中文名
        <input
          value={body.display_name}
          onChange={(e) => patch((b) => { b.display_name = e.target.value; })}
          placeholder="如：横盘突破"
        />
      </label>
      <label className="field">
        英文名
        <input
          value={body.display_name_en || ""}
          onChange={(e) => patch((b) => { b.display_name_en = e.target.value; })}
          placeholder="如：Range Breakout"
        />
      </label>
      <label className="field">
        描述
        <textarea
          rows={3}
          value={body.description}
          onChange={(e) => patch((b) => { b.description = e.target.value; })}
        />
      </label>
      <label className="field">
        最终评分阈值（0–100）
        <PlainNum
          value={body.threshold}
          onChange={(n) =>
            patch((b) => {
              const v = n ?? 80;
              b.threshold = Math.max(0, Math.min(100, v));
            })
          }
        />
      </label>
      <p className="muted" style={{ marginTop: "-0.35rem" }}>
        综合相似度 ≥ 该阈值且无硬约束失败时，才计为命中；发布后正式扫描生效。
      </p>
      <label className="field">
        history_bars
        <PlainNum
          value={body.history_bars}
          allowEmpty
          onChange={(n) => patch((b) => { b.history_bars = n; })}
        />
      </label>
      <p className="muted">context 权重: {body.stage_weights.context ?? 0}</p>
      <label className="field">
        stage_weights.context
        <PlainNum
          value={body.stage_weights.context ?? 0}
          onChange={(n) =>
            patch((b) => {
              b.stage_weights.context = n ?? 0;
            })
          }
        />
      </label>
    </>
  );
}

function ConstraintsForm({
  body,
  patch,
}: {
  body: DefinitionBody;
  patch: (fn: (b: DefinitionBody) => void) => void;
}) {
  const c = body.constraints || {};
  return (
    <>
      <h3>硬约束</h3>
      <label className="field check">
        <input
          type="checkbox"
          checked={c.exclude_st ?? true}
          onChange={(e) =>
            patch((b) => {
              b.constraints = { ...(b.constraints || {}), exclude_st: e.target.checked };
            })
          }
        />
        排除 ST
      </label>
      <label className="field">
        min_list_days
        <PlainNum
          value={c.min_list_days}
          allowEmpty
          onChange={(n) =>
            patch((b) => {
              b.constraints = { ...(b.constraints || {}), min_list_days: n };
            })
          }
        />
      </label>
      <label className="field">
        min_market_cap（亿元）
        <PlainNum
          value={c.min_market_cap}
          allowEmpty
          onChange={(n) =>
            patch((b) => {
              b.constraints = { ...(b.constraints || {}), min_market_cap: n };
            })
          }
        />
      </label>
      <label className="field">
        min_amount
        <PlainNum
          value={c.min_amount}
          allowEmpty
          onChange={(n) =>
            patch((b) => {
              b.constraints = { ...(b.constraints || {}), min_amount: n };
            })
          }
        />
      </label>
    </>
  );
}

function StageForm({
  stage,
  weight,
  guided,
  onRename,
  onRole,
  onWeight,
  onWindow,
}: {
  stage: DefinitionBody["timeline"][0];
  weight: number;
  guided: boolean;
  onRename: (n: string) => void;
  onRole: (role: StageRole | null) => void;
  onWeight: (w: number) => void;
  onWindow: (min: number, max: number) => void;
}) {
  const [name, setName] = useState(stage.name);
  useEffect(() => setName(stage.name), [stage.name]);
  const sum = weightSum(stage.targets);
  const role = stageRoleOf(stage);
  return (
    <>
      <h3>
        {guided && role ? `${ROLE_LABEL[role]} · ` : "Stage · "}
        {stage.name}
      </h3>
      <label className="field">
        角色
        <select
          value={role || ""}
          onChange={(e) => {
            const v = e.target.value as StageRole | "";
            onRole(v || null);
          }}
        >
          {!guided && <option value="">未分类</option>}
          {(Object.keys(ROLE_LABEL) as StageRole[]).map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        名称
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => onRename(name)}
          disabled={guided}
          title={guided ? "引导模式自动命名；切换高级可改" : undefined}
        />
      </label>
      <label className="field">
        stage_weight
        <PlainNum value={weight} onChange={(n) => onWeight(n ?? 0)} />
      </label>
      <div className="field-row">
        <label className="field">
          window min
          <PlainNum
            value={stage.window.min_length}
            onChange={(n) => onWindow(n ?? 1, stage.window.max_length)}
          />
        </label>
        <label className="field">
          window max
          <PlainNum
            value={stage.window.max_length}
            onChange={(n) => onWindow(stage.window.min_length, n ?? 1)}
          />
        </label>
      </div>
      <p className={Math.abs(sum - 1) > 0.05 ? "warn-text" : "muted"}>
        指标权重和 = {sum.toFixed(2)}（≠1 时警告，不阻断）
      </p>
    </>
  );
}

function TargetForm({
  name,
  target,
  hint,
  stageWeightSum,
  onChange,
  onDelete,
  showDelete = true,
  title,
}: {
  name: string;
  target: TargetValueJson;
  hint?: string;
  stageWeightSum: number;
  onChange: (t: TargetValueJson) => void;
  onDelete?: () => void;
  showDelete?: boolean;
  title?: string;
}) {
  const set = (k: keyof TargetValueJson, v: number | string | boolean | null) => {
    onChange({ ...target, [k]: v });
  };
  return (
    <>
      <div className="form-title-row">
        <h3>{title || featureLabel(name)}</h3>
        {showDelete && onDelete ? (
          <button type="button" className="btn danger" onClick={onDelete}>
            删除指标
          </button>
        ) : null}
      </div>
      {hint && <p className="muted">{hint}</p>}
      <div className="field-row">
        <label className="field">
          ideal
          <PlainNum value={target.ideal} onChange={(n) => set("ideal", n ?? 0)} />
        </label>
        <label className="field">
          tolerance
          <PlainNum value={target.tolerance} onChange={(n) => set("tolerance", n ?? 0)} />
        </label>
        <label className="field">
          weight
          <PlainNum value={target.weight ?? 0} onChange={(n) => set("weight", n ?? 0)} />
        </label>
      </div>
      <label className="field">
        mode
        <select value={target.mode || "two_sided"} onChange={(e) => set("mode", e.target.value)}>
          <option value="two_sided">two_sided</option>
          <option value="one_sided_high">one_sided_high</option>
          <option value="one_sided_low">one_sided_low</option>
        </select>
      </label>
      <div className="field-row">
        <label className="field">
          hard_min
          <PlainNum
            value={target.hard_min}
            allowEmpty
            onChange={(n) => set("hard_min", n)}
          />
        </label>
        <label className="field">
          hard_max
          <PlainNum
            value={target.hard_max}
            allowEmpty
            onChange={(n) => set("hard_max", n)}
          />
        </label>
      </div>
      <p className={Math.abs(stageWeightSum - 1) > 0.05 ? "warn-text" : "muted"}>
        本 Stage 权重和 {stageWeightSum.toFixed(2)}
      </p>
    </>
  );
}

function RelationForm({
  rel,
  stages,
  features,
  hint,
  onChange,
}: {
  rel: DefinitionBody["relations"][0];
  stages: string[];
  features: FeatureCatalogItem[];
  hint?: string;
  onChange: (r: DefinitionBody["relations"][0]) => void;
}) {
  return (
    <>
      <h3>Relation</h3>
      {hint && <p className="muted">{hint}</p>}
      <label className="field">
        特征
        <select
          value={rel.name}
          onChange={(e) => onChange({ ...rel, name: e.target.value })}
        >
          {features.map((f) => (
            <option key={f.name} value={f.name}>
              {featureOptionText(f)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        attach_to_stage
        <select
          value={rel.attach_to_stage}
          onChange={(e) => onChange({ ...rel, attach_to_stage: e.target.value })}
        >
          {stages.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <TargetForm
        name={rel.name}
        title={`目标 · ${featureLabel(rel.name, features)}`}
        target={rel.target}
        onChange={(t) => onChange({ ...rel, target: t })}
        showDelete={false}
        stageWeightSum={rel.target.weight ?? 0}
      />
    </>
  );
}

function ContextForm({
  ctx,
  features,
  hint,
  onChange,
}: {
  ctx: DefinitionBody["context_features"][0];
  features: FeatureCatalogItem[];
  hint?: string;
  onChange: (c: DefinitionBody["context_features"][0]) => void;
}) {
  return (
    <>
      <h3>Context</h3>
      {hint && <p className="muted">{hint}</p>}
      <label className="field">
        特征
        <select value={ctx.name} onChange={(e) => onChange({ ...ctx, name: e.target.value })}>
          {features.map((f) => (
            <option key={f.name} value={f.name}>
              {featureOptionText(f)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        lookback_bars
        <PlainNum
          value={ctx.lookback_bars}
          allowEmpty
          onChange={(n) => onChange({ ...ctx, lookback_bars: n })}
        />
      </label>
      <TargetForm
        name={ctx.name}
        title={`目标 · ${featureLabel(ctx.name, features)}`}
        target={ctx.target}
        onChange={(t) => onChange({ ...ctx, target: t })}
        showDelete={false}
        stageWeightSum={ctx.target.weight ?? 0}
      />
    </>
  );
}

function AddFeaturesModal({
  features,
  guided,
  role,
  onClose,
  onAdd,
}: {
  features: FeatureCatalogItem[];
  guided: boolean;
  role: StageRole | null;
  onClose: () => void;
  onAdd: (names: string[]) => void;
}) {
  const [picked, setPicked] = useState<string[]>([]);
  const groups = useMemo(() => {
    const universal = features.filter((f) => f.tier === "universal" || !f.tier);
    const roleSpecific = features.filter((f) => f.tier === "role_specific");
    const other = features.filter(
      (f) => f.tier && f.tier !== "universal" && f.tier !== "role_specific",
    );
    return [
      { title: "通用段内指标", items: universal },
      {
        title: role ? `${ROLE_LABEL[role]}专用` : "角色专用",
        items: roleSpecific,
      },
      ...(other.length ? [{ title: "其他", items: other }] : []),
    ].filter((g) => g.items.length > 0);
  }, [features, role]);

  const renderItem = (f: FeatureCatalogItem) => (
    <label key={f.name} className="check">
      <input
        type="checkbox"
        checked={picked.includes(f.name)}
        onChange={(e) => {
          setPicked((p) =>
            e.target.checked ? [...p, f.name] : p.filter((x) => x !== f.name),
          );
        }}
      />
      <span>{featureLabel(f)}</span>
      <span className="mono muted" style={{ fontSize: "0.78rem" }}>
        {" "}
        {f.name}
      </span>
      {f.ui_group && <span className="tag">{f.ui_group}</span>}
      <span className="muted"> {f.description}</span>
    </label>
  );

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>
          {guided ? "选择段内指标" : "从 Catalog 添加指标"}
          {guided && role ? ` · ${ROLE_LABEL[role]}` : ""}
        </h3>
        <div className="feature-pick-list">
          {guided
            ? groups.map((g) => (
                <div key={g.title} className="feature-group">
                  <div className="feature-group-title">{g.title}</div>
                  {g.items.map(renderItem)}
                </div>
              ))
            : features.map(renderItem)}
          {features.length === 0 && <p className="muted">无可添加特征</p>}
        </div>
        <div className="toolbar">
          <button type="button" className="btn" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={!picked.length}
            onClick={() => onAdd(picked)}
          >
            添加 {picked.length || ""}
          </button>
        </div>
      </div>
    </div>
  );
}

function DryHitsTable({
  hits,
  onOpenEval,
}: {
  hits: Array<{
    rank: number;
    code: string;
    name: string;
    pattern_score: number;
    chosen_window_ranges?: Record<string, { start: string; end: string }>;
  }>;
  onOpenEval: (code: string) => void;
}) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>#</th>
          <th>代码</th>
          <th>名称</th>
          <th>sim</th>
          <th>窗口</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {hits.map((h) => (
          <tr key={h.code}>
            <td>{h.rank}</td>
            <td className="mono">
              <Link to={`/stocks/${h.code}`}>{h.code}</Link>
            </td>
            <td>{h.name}</td>
            <td>{h.pattern_score.toFixed(1)}</td>
            <td className="muted mono">
              {Object.entries(h.chosen_window_ranges || {})
                .map(([k, r]) => `${k}:${r.start}→${r.end}`)
                .join(" · ")}
            </td>
            <td>
              <button type="button" className="btn tiny" onClick={() => onOpenEval(h.code)}>
                试跑明细
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
