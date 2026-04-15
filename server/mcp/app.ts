import Koa from "koa";
import Router from "@koa/router";
import bodyParser from "koa-bodyparser";
import { NodeStreamableHTTPServerTransport } from "@modelcontextprotocol/node";
import { McpServer } from "@modelcontextprotocol/server";
import { createFinancialMcpContext } from "./core/context.js";
import { McpToolRegistry } from "./core/registry.js";
import { FundAnalysisTool, FundScreenerOptionsTool, FundSectorsTool, ListMyFundHoldingsTool, MyFundHoldingTool, QueryFundUniverseTool, RefreshFundUniverseCacheTool, SectorFundsTool } from "./tools/fund-tools.js";
import { FundHoldingStocksTool, RealtimeStockQuotesTool } from "./tools/stock-tools.js";

export class FinancialMcpApplication {
  private readonly app = new Koa();
  private readonly router = new Router();
  private readonly context = createFinancialMcpContext();
  private readonly registry = new McpToolRegistry([
    new RealtimeStockQuotesTool(this.context),
    new FundHoldingStocksTool(this.context),
    new FundAnalysisTool(this.context),
    new MyFundHoldingTool(this.context),
    new ListMyFundHoldingsTool(this.context),
    new FundScreenerOptionsTool(this.context),
    new QueryFundUniverseTool(this.context),
    new FundSectorsTool(this.context),
    new SectorFundsTool(this.context),
    new RefreshFundUniverseCacheTool(this.context),
  ]);
  private readonly server = new McpServer({
    name: "financial-analysis-mcp",
    version: "2.0.0",
  });

  constructor() {
    this.registry.registerAll(this.server);
    this.configureMiddleware();
    this.configureRoutes();
  }

  createApp() {
    return this.app;
  }

  private configureMiddleware() {
    this.app.use(bodyParser({ enableTypes: ["json"] }));
  }

  private configureRoutes() {
    this.router.get("/health", (ctx) => {
      ctx.body = {
        ok: true,
        name: "financial-analysis-mcp",
        transport: "streamable-http",
        toolCount: this.registry.listToolNames().length,
        tools: this.registry.listToolManifests(),
      };
    });

    this.router.post("/mcp", async (ctx) => {
      ctx.respond = false;

      const transport = new NodeStreamableHTTPServerTransport({
        sessionIdGenerator: undefined,
      });

      await this.server.connect(transport);
      await transport.handleRequest(ctx.req, ctx.res, ctx.request.body);
    });

    this.app.use(this.router.routes());
    this.app.use(this.router.allowedMethods());
  }
}

export function createFinancialMcpApp() {
  return new FinancialMcpApplication().createApp();
}
