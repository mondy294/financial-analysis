import type { Server } from "node:http";
import { createStockMcpApp } from "./app.js";

const defaultHost = process.env.MCP_HOST || "127.0.0.1";
const defaultPort = Number(process.env.MCP_PORT || 4178);

export function startStockMcpServer(): Server {
  const app = createStockMcpApp();

  return app.listen(defaultPort, defaultHost, () => {
    console.log(`Stock MCP server is running at http://${defaultHost}:${defaultPort}/mcp`);
  });
}
