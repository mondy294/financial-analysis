import type { McpServer } from "@modelcontextprotocol/server";
import type { BaseMcpTool } from "./tool.js";

export class McpToolRegistry {
  constructor(private readonly tools: BaseMcpTool<any>[]) {}

  registerAll(server: McpServer) {
    for (const tool of this.tools) {
      tool.register(server);
    }
  }

  listToolNames() {
    return this.tools.map((tool) => tool.name);
  }

  listToolManifests() {
    return this.tools.map((tool) => tool.getManifest());
  }
}
