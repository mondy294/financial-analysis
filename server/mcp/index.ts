import type { Server } from "node:http";
import { createFinancialMcpApp } from "./app.js";

const defaultHost = process.env.MCP_HOST || "127.0.0.1";
const defaultPort = Number(process.env.MCP_PORT || 9090);

export function startFinancialMcpServer(): Server {
  const app = createFinancialMcpApp();

  return app.listen(defaultPort, defaultHost, () => {
    console.log(`Financial MCP server is running at http://${defaultHost}:${defaultPort}/mcp`);
  });
}
