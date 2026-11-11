// Stub MCP server: serves gflow's REAL tools/list (snapshot taken by run.mjs) and records
// every tools/call to a log instead of executing it. No Flow credits, no browser.
import { appendFileSync, readFileSync } from "node:fs";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const tools = JSON.parse(readFileSync(process.env.STUB_TOOLS, "utf8"));
const fixtures = JSON.parse(readFileSync(process.env.STUB_FIXTURES, "utf8"));
const server = new Server({ name: "gflow", version: "stub" }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));
server.setRequestHandler(CallToolRequestSchema, async (req) => {
  appendFileSync(process.env.STUB_LOG, JSON.stringify({ toolName: req.params.name, arguments: req.params.arguments ?? {} }) + "\n");
  if (fixtures[req.params.name]) return fixtures[req.params.name];
  return { content: [{ type: "text", text: "Accepted. (Dry-run evaluation: the call was recorded, not executed.)" }] };
});
await server.connect(new StdioServerTransport());
