import { useState } from "react";
import type { ScreenerPreset, ScreenerQueryPayload } from "../types";

type ScreenerPresetBarProps = {
  presets: ScreenerPreset[];
  query: ScreenerQueryPayload;
  onApply: (preset: ScreenerPreset) => void;
  onSave: (name: string) => Promise<void>;
  onDelete: (presetId: string) => Promise<void>;
};

export function ScreenerPresetBar({ presets, onApply, onSave, onDelete }: ScreenerPresetBarProps) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  return (
    <section className="panel preset-panel">
      <div className="section-head compact-head">
        <div>
          <h3>筛选方案</h3>
          <p>把常用的底仓、观察池和防守型筛选条件存起来，下次不用重配。</p>
        </div>
      </div>

      <div className="preset-form-row">
        <input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：低波红利底仓" />
        <button
          type="button"
          className="secondary-button"
          disabled={saving || !name.trim()}
          onClick={async () => {
            setSaving(true);
            try {
              await onSave(name.trim());
              setName("");
            } finally {
              setSaving(false);
            }
          }}
        >
          {saving ? "保存中..." : "保存当前方案"}
        </button>
      </div>

      {presets.length === 0 ? (
        <div className="empty-inline compact-empty">还没有保存过筛选方案。调顺手后存一个，后面会省很多事。</div>
      ) : (
        <div className="preset-list">
          {presets.map((preset) => (
            <article key={preset.id} className="preset-card">
              <div>
                <strong>{preset.name}</strong>
                <span>更新于 {new Date(preset.updatedAt).toLocaleString("zh-CN")}</span>
              </div>
              <div className="row-actions">
                <button type="button" className="inline-button" onClick={() => onApply(preset)}>
                  应用
                </button>
                <button type="button" className="inline-button danger-text" onClick={() => void onDelete(preset.id)}>
                  删除
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
