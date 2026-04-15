import { useEffect, useState } from "react";
import type { FundDetailResponse, HoldingDraft, HoldingItem } from "../types";
import { formatAmount, formatDateTime, formatNav, formatPercent, signedClass } from "../utils/fund";

type HoldingsPageProps = {
  items: HoldingItem[];
  loading: boolean;
  draft: HoldingDraft | null;
  onSave: (draft: HoldingDraft) => Promise<void>;
  onDelete: (code: string) => Promise<void>;
  onOpenDetail: (detail: FundDetailResponse | null) => void;
};

type HoldingFormState = {
  code: string;
  status: string;
  holdingReturnRate: string;
  positionAmount: string;
  costNav: string;
  note: string;
};

const emptyForm: HoldingFormState = {
  code: "",
  status: "持有中",
  holdingReturnRate: "",
  positionAmount: "",
  costNav: "",
  note: "",
};

function parseNullable(value: string) {
  if (value.trim() === "") {
    return null;
  }

  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function toInputValue(value: number | null) {
  return value === null ? "" : String(value);
}

function toFormState(draft: HoldingDraft): HoldingFormState {
  return {
    code: draft.code,
    status: draft.status,
    holdingReturnRate: toInputValue(draft.holdingReturnRate),
    positionAmount: toInputValue(draft.positionAmount),
    costNav: toInputValue(draft.costNav),
    note: draft.note,
  };
}

function toHoldingDraft(form: HoldingFormState): HoldingDraft {
  return {
    code: form.code,
    status: form.status,
    holdingReturnRate: parseNullable(form.holdingReturnRate),
    positionAmount: parseNullable(form.positionAmount),
    costNav: parseNullable(form.costNav),
    note: form.note,
  };
}

function isValidNumericInput(value: string) {
  return /^-?\d*(\.\d*)?$/.test(value);
}

function openEditor(setForm: (updater: (current: HoldingFormState) => HoldingFormState) => void, item: HoldingItem) {
  setForm(() =>
    toFormState({
      code: item.code,
      status: item.status,
      holdingReturnRate: item.holdingReturnRate,
      positionAmount: item.positionAmount,
      costNav: item.costNav,
      note: item.note,
    }),
  );
}

export function HoldingsPage({ items, loading, draft, onSave, onDelete, onOpenDetail }: HoldingsPageProps) {
  const [form, setForm] = useState<HoldingFormState>(draft ? toFormState(draft) : emptyForm);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (draft) {
      setForm(toFormState(draft));
    }
  }, [draft]);

  return (
    <div className="page-layout holdings-layout">
      <section className="panel form-panel">
        <div className="section-head">
          <div>
            <h3>持有录入</h3>
            <p>你自己的收益率、仓位和备注不可能靠公开接口给你猜出来，所以这块老老实实手填，数据会直接落到本地 JSON。</p>
          </div>
        </div>

        <form
          className="holding-form"
          onSubmit={async (event) => {
            event.preventDefault();
            setSaving(true);
            try {
              await onSave(toHoldingDraft(form));
              setForm(emptyForm);
            } catch {
              // 错误提示交给上层 toast，这里只避免 Promise 冒泡。
            } finally {
              setSaving(false);
            }
          }}
        >
          <div className="form-grid">
            <label>
              <span>基金编号</span>
              <input
                value={form.code}
                maxLength={6}
                inputMode="numeric"
                onChange={(event) => setForm((current) => ({ ...current, code: event.target.value.replace(/\D/g, "").slice(0, 6) }))}
                placeholder="例如 161725"
                required
              />
            </label>

            <label>
              <span>持有状态</span>
              <select value={form.status} onChange={(event) => setForm((current) => ({ ...current, status: event.target.value }))}>
                <option value="持有中">持有中</option>
                <option value="观察仓">观察仓</option>
                <option value="已止盈">已止盈</option>
                <option value="已止损">已止损</option>
              </select>
            </label>

            <label>
              <span>手动收益率（%）</span>
              <input
                value={form.holdingReturnRate}
                inputMode="decimal"
                onChange={(event) => {
                  const { value } = event.target;
                  if (!isValidNumericInput(value)) {
                    return;
                  }

                  setForm((current) => ({ ...current, holdingReturnRate: value }));
                }}
                placeholder="例如 12.50"
              />
            </label>

            <label>
              <span>持仓金额（元）</span>
              <input
                value={form.positionAmount}
                inputMode="decimal"
                onChange={(event) => {
                  const { value } = event.target;
                  if (!isValidNumericInput(value)) {
                    return;
                  }

                  setForm((current) => ({ ...current, positionAmount: value }));
                }}
                placeholder="例如 10000"
              />
            </label>

            <label>
              <span>成本净值</span>
              <input
                value={form.costNav}
                inputMode="decimal"
                onChange={(event) => {
                  const { value } = event.target;
                  if (!isValidNumericInput(value)) {
                    return;
                  }

                  setForm((current) => ({ ...current, costNav: value }));
                }}
                placeholder="例如 1.2350"
              />
            </label>
          </div>

          <label>
            <span>备注</span>
            <textarea
              value={form.note}
              onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))}
              rows={4}
              placeholder="例如：长期定投 / 回撤到某个区间再加仓 / 只是做观察仓"
            />
          </label>

          <div className="form-actions">
            <button type="submit" className="primary-button" disabled={saving}>
              {saving ? "保存中..." : "保存持有记录"}
            </button>
            <button type="button" className="secondary-button" onClick={() => setForm(emptyForm)}>
              清空表单
            </button>
          </div>
        </form>
      </section>

      <section className="panel holdings-list-panel">
        <div className="section-head">
          <div>
            <h3>我的持有</h3>
            <p>这页改成卡片式了，仓位、收益率、成本和备注不再挤在一条长表格里，看着终于像个正常页面。</p>
          </div>
          <div className="badge badge-muted">共 {items.length} 条</div>
        </div>

        {loading ? (
          <div className="empty-state">正在加载持有数据...</div>
        ) : items.length === 0 ? (
          <div className="empty-state">还没有持有记录。先查一只基金，再把你的仓位信息录进来。</div>
        ) : (
          <div className="holding-card-list">
            {items.map((item) => (
              <article key={item.code} className="holding-card">
                <div className="holding-card-head">
                  <div className="holding-card-title">
                    <strong>{item.detail?.fund.name || item.code}</strong>
                    <span>{item.code}</span>
                  </div>
                  <div className="badge-wrap">
                    <span className="badge badge-gold">{item.status}</span>
                    <span className="badge badge-muted">{formatDateTime(item.updatedAt)}</span>
                  </div>
                </div>

                <div className="holding-card-metrics">
                  <div className="detail-card">
                    <span>手动收益率</span>
                    <strong className={signedClass(item.holdingReturnRate)}>{formatPercent(item.holdingReturnRate)}</strong>
                  </div>
                  <div className="detail-card">
                    <span>持仓金额</span>
                    <strong>{formatAmount(item.positionAmount)}</strong>
                  </div>
                  <div className="detail-card">
                    <span>成本净值</span>
                    <strong>{formatNav(item.costNav)}</strong>
                  </div>
                  <div className="detail-card">
                    <span>最新净值</span>
                    <strong>{formatNav(item.detail?.fund.latestNav ?? null)}</strong>
                  </div>
                  <div className="detail-card">
                    <span>近 1 月</span>
                    <strong className={signedClass(item.detail?.performance.oneMonth ?? null)}>{formatPercent(item.detail?.performance.oneMonth ?? null)}</strong>
                  </div>
                  <div className="detail-card">
                    <span>最新估算涨跌</span>
                    <strong className={signedClass(item.detail?.fund.estimatedChangeRate ?? null)}>{formatPercent(item.detail?.fund.estimatedChangeRate ?? null)}</strong>
                  </div>
                </div>

                <div className="holding-card-note">
                  <span className="subtle-label">备注</span>
                  <p>{item.note || "暂无备注。"}</p>
                </div>

                {item.error ? <div className="empty-inline compact-empty">{item.error}</div> : null}

                <div className="row-actions">
                  <button type="button" className="inline-button" onClick={() => onOpenDetail(item.detail)}>
                    查看总览
                  </button>
                  <button type="button" className="inline-button" onClick={() => openEditor(setForm, item)}>
                    编辑仓位
                  </button>
                  <button type="button" className="inline-button danger-text" onClick={() => onDelete(item.code)}>
                    删除
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
