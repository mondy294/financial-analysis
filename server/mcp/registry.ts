import { createFinancialMcpContext } from "./core/context.js";
import { McpToolRegistry } from "./core/registry.js";
import {
  FundAnalysisTool,
  FundHoldingBreadthTool,
  FundPeerBenchmarkTool,
  FundScreenerOptionsTool,
  FundSectorsTool,
  ListMyFundHoldingsTool,
  MyFundHoldingTool,
  QueryFundUniverseTool,
  RefreshFundUniverseCacheTool,
  SectorFundsTool,
} from "./tools/fund-tools.js";
import { FundHoldingStocksTool, RealtimeStockQuotesTool } from "./tools/stock-tools.js";

export function createFinancialMcpRegistry() {
  const context = createFinancialMcpContext();

  return new McpToolRegistry([
    new RealtimeStockQuotesTool(context),
    new FundHoldingStocksTool(context),
    new FundAnalysisTool(context),
    new FundPeerBenchmarkTool(context),
    new FundHoldingBreadthTool(context),
    new MyFundHoldingTool(context),
    new ListMyFundHoldingsTool(context),
    new FundScreenerOptionsTool(context),
    new QueryFundUniverseTool(context),
    new FundSectorsTool(context),
    new SectorFundsTool(context),
    new RefreshFundUniverseCacheTool(context),
  ]);
}
