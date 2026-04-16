import { FundAgentService } from "../agent/fund-agent-service.js";
import { analyzeWatchlistFundsAndPersist } from "../agent/fund-agent-batch-service.js";

const horizon = String(process.argv[2] || "未来 1-3 个月").trim() || "未来 1-3 个月";
const userQuestion = String(
  process.argv[3]
    || "请按默认流程分析未来走势、当前操作建议与未来多情景预测，并覆盖保存每只基金的最新分析记录。",
).trim();

const service = new FundAgentService();
const result = await analyzeWatchlistFundsAndPersist({
  service,
  horizon,
  userQuestion,
});

console.log(`Watchlist batch analysis finished. total=${result.total} succeeded=${result.succeeded} failed=${result.failed}`);

result.items.forEach((item) => {
  if (item.status === "success") {
    console.log(`✔ ${item.fundCode} ${item.fundName ?? ""} ${item.updatedAt ?? ""}`.trim());
    return;
  }

  console.error(`✖ ${item.fundCode} ${item.error ?? "分析失败"}`);
});

if (result.failed > 0) {
  process.exitCode = 1;
}
