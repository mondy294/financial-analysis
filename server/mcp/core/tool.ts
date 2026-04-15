import type { McpServer } from "@modelcontextprotocol/server";
import { z } from "zod";
import type { FinancialMcpContext } from "./context.js";

type ToolResultPayload = {
  summary: string;
  structuredContent?: Record<string, unknown>;
};

export abstract class BaseMcpTool<TSchema extends z.ZodTypeAny> {
  abstract readonly name: string;
  abstract readonly title: string;
  abstract readonly description: string;
  abstract readonly inputSchema: TSchema;

  constructor(protected readonly context: FinancialMcpContext) {}

  register(server: McpServer) {
    const config = {
      title: this.title,
      description: this.description,
      inputSchema: this.inputSchema,
    };

    const callback = async (input: unknown) => {
      try {
        const result = await this.execute(input as z.infer<TSchema>);
        return {
          content: [{ type: "text", text: result.summary }],
          ...(result.structuredContent !== undefined ? { structuredContent: result.structuredContent } : {}),
        };
      } catch (error) {
        return {
          isError: true,
          content: [{ type: "text", text: error instanceof Error ? error.message : `${this.title}失败。` }],
        };
      }
    };

    (server.registerTool as unknown as (name: string, config: unknown, cb: (input: unknown) => Promise<unknown>) => unknown)(
      this.name,
      config,
      callback,
    );
  }

  getManifest() {
    return {
      name: this.name,
      title: this.title,
      description: this.description,
    };
  }

  protected abstract execute(input: z.infer<TSchema>): Promise<ToolResultPayload>;
}
