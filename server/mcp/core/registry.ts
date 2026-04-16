import type { McpServer } from "@modelcontextprotocol/server";
import type { BaseMcpTool, ToolResultPayload } from "./tool.js";

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

  listOpenAiToolDefinitions() {
    return this.tools.map((tool) => tool.getOpenAiToolDefinition());
  }

  getTool(name: string) {
    return this.tools.find((tool) => tool.name === name) ?? null;
  }

  async executeTool(name: string, input: unknown): Promise<ToolResultPayload> {
    const tool = this.getTool(name);
    if (!tool) {
      throw new Error(`未找到工具：${name}`);
    }
    return tool.invoke(input);
  }
}
