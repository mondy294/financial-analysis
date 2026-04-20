import { useEffect, useState } from "react";
import { getModelProviderSettings, saveModelProviderSettings } from "../api/client";
import type { ModelProviderSettings } from "../types";

export function SettingsPage() {
  const [settings, setSettings] = useState<ModelProviderSettings | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    void loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    setError(null);

    try {
      const payload = await getModelProviderSettings();
      setSettings(payload);
      setBaseUrl(payload.baseUrl);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载模型设置失败。");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const payload = await saveModelProviderSettings({
        baseUrl,
        apiKey: apiKey.trim() ? apiKey.trim() : undefined,
      });
      setSettings(payload);
      setBaseUrl(payload.baseUrl);
      setApiKey("");
      setSuccessMessage("模型设置已保存，后续新的 Agent 分析会使用最新配置。");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "保存模型设置失败。");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="settings-page-layout">
      <section className="panel form-panel">
        <div className="section-head">
          <div>
            <h3>模型接口设置</h3>
            <p>在这里配置你自己的大模型接口地址和 API Key。保存后，新的基金 Agent 分析会直接使用这里的设置。</p>
          </div>
        </div>

        {loading ? (
          <div className="empty-state compact-empty">正在加载当前模型设置...</div>
        ) : (
          <>
            <div className="settings-status-grid">
              <div className="detail-card">
                <span>当前模型</span>
                <strong>{settings?.model ?? "--"}</strong>
              </div>
              <div className="detail-card">
                <span>API Key</span>
                <strong>{settings?.apiKeyConfigured ? settings.apiKeyMasked ?? "已配置" : "未配置"}</strong>
              </div>
              <div className="detail-card">
                <span>接口来源</span>
                <strong>{settings?.hasCustomBaseUrl ? "页面自定义" : "环境默认"}</strong>
              </div>
              <div className="detail-card">
                <span>Key 来源</span>
                <strong>{settings?.hasCustomApiKey ? "页面自定义" : settings?.apiKeyConfigured ? "环境默认" : "未配置"}</strong>
              </div>
            </div>

            <div className="cache-hint">
              <strong>保存说明</strong>
              <span>接口地址会直接保存；API Key 输入框默认留空，只有当你填写了新值时才会覆盖当前已保存的 Key。</span>
            </div>

            {error ? (
              <div className="warning-box">
                <strong>设置失败</strong>
                <p>{error}</p>
              </div>
            ) : null}

            {successMessage ? (
              <div className="cache-hint">
                <strong>保存成功</strong>
                <span>{successMessage}</span>
              </div>
            ) : null}

            <label>
              <span>大模型接口 URL</span>
              <input
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder="例如 https://api.deepseek.com"
              />
            </label>

            <label>
              <span>API Key</span>
              <input
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={settings?.apiKeyConfigured ? "留空则保留当前 Key；输入新值则覆盖" : "请输入你的 API Key"}
              />
            </label>

            <div className="section-note">
              这里的配置只影响本地这套项目的 Agent 分析请求，不会改动你系统里的全局环境变量。
            </div>

            <div className="form-actions">
              <button type="button" className="primary-button" onClick={() => void handleSave()} disabled={saving}>
                {saving ? "保存中..." : "保存模型设置"}
              </button>
              <button type="button" className="secondary-button" onClick={() => void loadSettings()} disabled={loading || saving}>
                重新加载
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
