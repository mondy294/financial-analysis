import fs from "node:fs/promises";
import path from "node:path";
import { FundAgentService } from "../agent/fund-agent-service.js";

const fundCode = String(process.argv[2] || "161725").trim();
const horizon = String(process.argv[3] || "未来 1-3 个月").trim();
const userQuestion = String(process.argv[4] || "请分析未来走势并给出当下操作建议。").trim();

const service = new FundAgentService();
const input = {
  fundCode,
  horizon,
  userQuestion,
};

const output = await service.analyzeFund(input);
const examplesDir = path.resolve(process.cwd(), "examples");
const inputPath = path.join(examplesDir, `fund-agent-${fundCode}-input.json`);
const outputPath = path.join(examplesDir, `fund-agent-${fundCode}-output.json`);

await fs.mkdir(examplesDir, { recursive: true });
await Promise.all([
  fs.writeFile(inputPath, JSON.stringify(input, null, 2), "utf-8"),
  fs.writeFile(outputPath, JSON.stringify(output, null, 2), "utf-8"),
]);

console.log(`Smoke test completed for fund ${fundCode}.`);
console.log(`Input saved to: ${inputPath}`);
console.log(`Output saved to: ${outputPath}`);
