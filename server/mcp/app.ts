import Koa from "koa";
import Router from "@koa/router";
import bodyParser from "koa-bodyparser";
import { NodeStreamableHTTPServerTransport } from "@modelcontextprotocol/node";
import { McpServer } from "@modelcontextprotocol/server";
import { registerStockTools } from "./stock-tools.js";

const server = new McpServer({
  name: "financial-analysis-stock-mcp",
  version: "1.0.0",
});

registerStockTools(server);

export function createStockMcpApp() {
  const app = new Koa();
  const router = new Router();

  app.use(bodyParser({ enableTypes: ["json"] }));

  router.get("/health", (ctx) => {
    ctx.body = {
      ok: true,
      name: "financial-analysis-stock-mcp",
      transport: "streamable-http",
      tools: ["get_realtime_stock_quotes", "get_fund_holding_stocks"],
    };
  });

  router.post("/mcp", async (ctx) => {
    ctx.respond = false;

    const transport = new NodeStreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
    });

    await server.connect(transport);
    await transport.handleRequest(ctx.req, ctx.res, ctx.request.body);
  });

  app.use(router.routes());
  app.use(router.allowedMethods());

  return app;
}
