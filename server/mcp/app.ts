import Koa from "koa";
import Router from "@koa/router";
import bodyParser from "koa-bodyparser";
import { NodeStreamableHTTPServerTransport } from "@modelcontextprotocol/node";
import { McpServer } from "@modelcontextprotocol/server";
import { createFinancialMcpRegistry } from "./registry.js";

export class FinancialMcpApplication {
  private readonly app = new Koa();
  private readonly router = new Router();
  private readonly registry = createFinancialMcpRegistry();
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
