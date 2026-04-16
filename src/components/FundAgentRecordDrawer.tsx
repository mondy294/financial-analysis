import { useEffect } from "react";
import type { FundAgentAnalysisRecord, HoldingItem } from "../types";
import { formatDateTime, formatNav, formatPercent } from "../utils/fund";
import { FundAgentNewsDigest } from "./FundAgentNewsDigest";

type FundAgentRecordDrawerProps = {
  open: boolean;
  fundCode: string;
  fundName: string;
  holding: HoldingItem;
  analysis: FundAgentAnalysisRecord | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

function ensureStringList(value: unknown) {
  if (!Array.isArray(value)) {
    return [] as string[];
  }

  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function ensureText(value: string | null | undefined, fallback = "--") {
  return typeof value === "string" && value.trim().length > 0 ? value : fallback;
}

function renderList(items: unknown, emptyText = "暂无可展示内容") {
  const safeItems = ensureStringList(items);

  if (safeItems.length === 0) {
    return <p className="empty-state compact-empty">{emptyText}</p>;
  }

  return (
    <ul className="agent-analysis-list">
      {safeItems.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function renderPlanLevels(levels: FundAgentAnalysisRecord["report"]["planLevels"]) {
  if (!Array.isArray(levels) || levels.length === 0) {
    return <p className="empty-state compact-empty">暂无关键价位计划</p>;
  }

  return (
    <div className="agent-tool-trace-list">
      {levels.map((level, index) => (
        <article key={`${level.kind}-${level.reference}-${index}`} className="agent-tool-trace-item">
          <h4>{level.kind}</h4>
          <p>参考位：{formatNav(level.nav)}{level.relativeToLatest !== null && level.relativeToLatest !== undefined ? `（相对当前 ${formatPercent(level.relativeToLatest)}）` : ""}</p>
          <p>依据：{ensureText(level.reference, "--")}</p>
          <p>触发条件：{ensureText(level.condition, "--")}</p>
          <p>执行动作：{ensureText(level.action, "--")}</p>
          <p>原因：{ensureText(level.reason, "--")}</p>
        </article>
      ))}
    </div>
  );
}

export function FundAgentRecordDrawer({
  open,
  fundCode,
  fundName,
  holding,
  analysis,
  loading,
  error,
  onClose,
}: FundAgentRecordDrawerProps) {
  useEffect(() => {
    if (!open) {
      return;
    }

    function handleKeydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  const report = analysis?.report ?? null;
  const toolTrace = Array.isArray(analysis?.toolTrace) ? analysis.toolTrace : [];

  return (
    <div className="agent-record-overlay" onClick={onClose}>
      <aside className="agent-record-drawer" onClick={(event) => event.stopPropagation()}>
        <div className="agent-record-drawer-head">
          <div>
            <span className="eyebrow">Saved Agent Record</span>
            <h3>{fundName}</h3>
            <p>{fundCode} · {holding.status} · 存在项目文件中的最新 AI 分析记录</p>
          </div>
          <div className="badge-wrap">
            <span className="badge badge-gold">{holding.status}</span>
            <span className="badge badge-muted">{analysis ? `记录更新 ${formatDateTime(analysis.updatedAt)}` : "暂无记录"}</span>
            <button type="button" className="secondary-button" onClick={onClose}>
              关闭
            </button>
          </div>
        </div>

        {loading ? (
          <div className="empty-state">正在读取这只持有基金的 AI 分析记录...</div>
        ) : error ? (
          <div className="warning-box agent-analysis-block">
            <strong>读取失败</strong>
            <p>{error}</p>
          </div>
        ) : !analysis || !report ? (
          <div className="agent-record-empty panel">
            <div className="section-head compact-head">
              <div>
                <h3>还没有 AI 分析记录</h3>
                <p>这只基金已经在你的持有里了，但项目文件中还没有它的最新 AI 分析结果。</p>
              </div>
            </div>
            <p className="empty-state compact-empty">先在详情卡里点一次“AI 分析未来走势”，系统就会自动覆盖保存这只基金的最新分析，后面从这里直接抽屉回看。</p>
          </div>
        ) : (
          <div className="agent-record-drawer-body">
            <div className="agent-record-summary-grid">
              <article className="detail-card">
                <span>趋势判断</span>
                <strong>{ensureText(report.outlook, "无法判断")}</strong>
              </article>
              <article className="detail-card">
                <span>动作标签</span>
                <strong>{ensureText(report.actionTag, "暂无标签")}</strong>
              </article>
              <article className="detail-card">
                <span>置信度</span>
                <strong>{report.confidence ?? "--"}</strong>
              </article>
              <article className="detail-card">
                <span>仓位幅度</span>
                <strong>{ensureText(report.positionSizing, "暂无建议")}</strong>
              </article>
            </div>

            <div className="agent-analysis-hero agent-record-hero">
              <article className="agent-analysis-highlight">
                <span>结论摘要</span>
                <strong>{ensureText(report.summary, "暂无分析摘要")}</strong>
                <p>{ensureText(report.actionAdvice, "暂无具体操作建议")}</p>
              </article>
              <article className="agent-analysis-highlight">
                <span>当前计划</span>
                <strong>{ensureText(report.actionTag, "待补充")}</strong>
                <p>{ensureText(report.planSummary, "暂无可执行计划")}</p>
              </article>
            </div>

            <FundAgentNewsDigest report={report} toolTrace={toolTrace} />

            <div className="agent-analysis-flow">
              <article className="agent-analysis-section">
                <h4>当前持仓背景</h4>
                <p>{ensureText(report.holdingContext, "暂无持仓背景")}</p>
              </article>
              <article className="agent-analysis-section">
                <h4>最近一周发生了什么</h4>
                <p>{ensureText(report.recentWeekSummary, "暂无最近一周变化说明")}</p>
              </article>
              <article className="agent-analysis-section">
                <h4>变化的可能原因</h4>
                {renderList(report.recentWeekDrivers, "暂无变化原因说明")}
              </article>
              <article className="agent-analysis-section">
                <h4>现在该怎么做</h4>
                <p>{ensureText(report.positionInstruction, "暂无明确仓位动作")}</p>
                <p>建议幅度：{ensureText(report.positionSizing, "暂无建议")}</p>
              </article>
              <article className="agent-analysis-section">
                <h4>执行规则</h4>
                {renderList(report.executionRules, "暂无执行规则")}
              </article>
              <article className="agent-analysis-section">
                <h4>关键价位计划</h4>
                {renderPlanLevels(report.planLevels)}
              </article>
              <article className="agent-analysis-section">
                <h4>重新评估条件</h4>
                {renderList(report.reEvaluationTriggers, "暂无重新评估条件")}
              </article>
              <article className="agent-analysis-section">
                <h4>核心依据</h4>
                {renderList(report.reasoning, "暂无核心依据")}
              </article>
              <article className="agent-analysis-section">
                <h4>主要风险</h4>
                {renderList(report.risks, "暂无主要风险提示")}
              </article>
              <article className="agent-analysis-section">
                <h4>接下来盯这些</h4>
                {renderList(report.watchItems, "暂无后续观察点")}
              </article>
            </div>

            {toolTrace.length > 0 ? (
              <div className="agent-tool-trace">
                <strong>生成这份记录时用到的工具</strong>
                <div className="agent-tool-trace-list">
                  {toolTrace.map((item) => (
                    <article key={`${item.toolName}-${item.summary}`} className="agent-tool-trace-item">
                      <h4>{item.toolName}</h4>
                      <p>{item.summary}</p>
                    </article>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="disclaimer-banner">
              <strong>风险提示</strong>
              <span>{ensureText(report.disclaimer, "以上内容仅供研究参考，不构成投资建议。")}</span>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
