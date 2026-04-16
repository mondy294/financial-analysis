import fs from "node:fs/promises";
import path from "node:path";
import { createFinancialMcpRegistry } from "../mcp/registry.js";

const startTime = String(process.argv[2] || "2026-04-14").trim();
const endTime = String(process.argv[3] || "2026-04-16").trim();
const keywords = process.argv.slice(4).map((item) => String(item).trim()).filter(Boolean);

const registry = createFinancialMcpRegistry();
const input = {
  startTime,
  endTime,
  regions: ["国内", "海外"],
  limit: 60,
  ...(keywords.length > 0 ? { keywords } : {}),
};

const output = await registry.executeTool("get_fund_market_news", input);
const examplesDir = path.resolve(process.cwd(), "examples");
const inputPath = path.join(examplesDir, "fund-news-mcp-input.json");
const outputPath = path.join(examplesDir, "fund-news-mcp-output.json");

await fs.mkdir(examplesDir, { recursive: true });
await Promise.all([
  fs.writeFile(inputPath, JSON.stringify(input, null, 2), "utf-8"),
  fs.writeFile(outputPath, JSON.stringify(output, null, 2), "utf-8"),
]);

console.log("Market news MCP smoke test completed.");
console.log(`Input saved to: ${inputPath}`);
console.log(`Output saved to: ${outputPath}`);
