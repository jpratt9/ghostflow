// Tool-selection eval for gflow's MCP server, with Claude Code as the host.
// 1. MCPJam's MCPClientManager snapshots the REAL gflow tools/list over stdio.
// 2. stub.mjs serves that snapshot and records calls instead of executing them.
// 3. Each case runs `claude -p` (the user's subscription) against the stub only.
// No gflow tool ever executes: $0 Flow credits, no browser. EvalTest/MCPJam Cloud unused.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

process.env.DO_NOT_TRACK = "1";
process.env.MCPJAM_TELEMETRY_DISABLED = "1";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..", "..", "..");
const { values: opt } = parseArgs({
  options: {
    model: { type: "string", default: "sonnet" },
    iterations: { type: "string", default: "5" },
    cases: { type: "string", default: join(here, "cases.json") },
    only: { type: "string" },
  },
});

const venvBin = process.platform === "win32" ? join("Scripts", "gflow.exe") : join("bin", "gflow");
const gflowBin = process.env.GFLOW_BIN ?? join(repo, ".venv", venvBin);
if (!existsSync(gflowBin)) throw new Error(`gflow not found at ${gflowBin}; set GFLOW_BIN`);
const outDir = join(repo, "scripts", "dev", "_spike_out", "mcpjam");
const work = join(outDir, "work"); // empty cwd: no project CLAUDE.md / .mcp.json for the host
mkdirSync(work, { recursive: true });

// 1. Snapshot the live tool surface. cwd = outDir keeps the repo .env out; the SDK still
// merges process.env, and $GFLOW_CLI_HOME/.env still loads (both harmless: tools/list only).
const { MCPClientManager } = await import("@mcpjam/sdk");
const manager = new MCPClientManager();
await manager.connectToServer("gflow", { command: gflowBin, args: ["mcp", "run"], cwd: outDir, env: { PYTHONUTF8: "1" } });
let tools;
try {
  tools = (await manager.listTools("gflow")).tools;
  // Read-only lookups must answer with data, or the host stops to ask instead of acting.
  // list_tools is local + $0, so record its real reply; browser-backed reads get fixtures.
  const fixtures = {
    gflow_list_tools: await manager.executeTool("gflow", "gflow_list_tools", {}),
    gflow_auth_status: { content: [{ type: "text", text: JSON.stringify({ profile: "default", status: "valid", flow_host: "flow.google.com" }) }] },
    gflow_character_list: { content: [{ type: "text", text: JSON.stringify({ characters: [
      { entity_id: "3f2a9c1e-7b4d-4e2a-9c1f-0d8e5b6a7c21", display_name: "Maya" },
      { entity_id: "9b1d4e7a-2c3f-4a5b-8d6e-1f0a2b3c4d5e", display_name: "Bob" },
    ] }) }] },
    gflow_list_projects: { content: [{ type: "text", text: JSON.stringify({ projects: [{ id: "7f3e2a10-1c4b-4d5e-8f9a-0b1c2d3e4f50", name: "Demo", characters: ["Maya", "Bob"] }] }) }] },
  };
  writeFileSync(join(outDir, "fixtures.json"), JSON.stringify(fixtures, null, 2));
} finally {
  await manager.disconnectServer("gflow");
}
const toolsFile = join(outDir, "tools.json");
writeFileSync(toolsFile, JSON.stringify(tools, null, 2));
console.log(`snapshot: ${tools.length} tools`);

// Never let the host fall back to API billing: the subscription login is the only auth.
const hostEnv = { ...process.env };
for (const k of Object.keys(hostEnv)) if (/^ANTHROPIC_/.test(k)) delete hostEnv[k];

const logFile = join(outDir, "calls.jsonl");
const mcpConfig = join(outDir, "mcp.json");
writeFileSync(mcpConfig, JSON.stringify({
  mcpServers: { gflow: { command: process.execPath, args: [join(here, "stub.mjs")], env: { STUB_TOOLS: toolsFile, STUB_LOG: logFile, STUB_FIXTURES: join(outDir, "fixtures.json") } } },
}));

const cases = JSON.parse(readFileSync(opt.cases, "utf8")).filter((c) => !opt.only || c.id === opt.only);
const n = Number(opt.iterations);
const report = [];

for (const c of cases) {
  const outcomes = [];
  for (let i = 0; i < n; i++) { // sequential on purpose
    rmSync(logFile, { force: true });
    const r = spawnSync("claude", [
      "-p", c.prompt, "--model", opt.model, "--output-format", "json",
      "--strict-mcp-config", "--mcp-config", mcpConfig, "--tools", "", "--allowedTools", "mcp__gflow",
      "--no-session-persistence",
    ], { cwd: work, env: hostEnv, encoding: "utf8", timeout: 180_000, input: "" }); // no shell: keeps "" and backslashes intact
    if (r.error) throw new Error(`claude -p did not run: ${r.error.message}`); // ENOENT/timeout: abort, not 60 blank misses
    let res = {};
    try { res = JSON.parse(r.stdout); } catch { /* reported below */ }
    if (r.status !== 0 || res.is_error) {
      outcomes.push({ pass: false, error: true, why: `RUN ERROR (exit ${r.status}): ${(res.result ?? r.stderr ?? "").slice(0, 300)}` });
      continue;
    }
    const calls = existsSync(logFile) ? readFileSync(logFile, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];
    // Read-only pre-flight calls (auth_status, list_*) are fine: grade the first call to the
    // expected tool; with no expected tool, only a mutating call fails the case.
    const mutating = calls.filter((x) => /generate|upscale|download|_add|_rm|_apply|toggle|set_enabled/.test(x.toolName));
    const pick = c.tool ? calls.find((x) => x.toolName === c.tool) ?? calls[0] : mutating[0];
    const call = pick && { ...pick, toolName: `mcp__gflow__${pick.toolName}` };
    outcomes.push({ ...grade(c, call), calls: calls.map((x) => x.toolName), cost_usd: res.total_cost_usd, reply: res.result?.slice(0, 300) });
  }
  const passed = outcomes.filter((o) => o.pass).length;
  report.push({ id: c.id, passed, n, outcomes });
  console.log(`${passed === n ? "PASS" : "MISS"} ${c.id}: ${passed}/${n}`);
  for (const o of outcomes.filter((o) => !o.pass)) console.log(`     ${o.why}`);
}

const total = report.reduce((s, r) => s + r.passed, 0);
const all = report.reduce((s, r) => s + r.n, 0);
console.log(`\nclaude -p --model ${opt.model}: ${total}/${all} = ${((100 * total) / all).toFixed(1)}%`);
const file = join(outDir, `eval-${new Date().toISOString().replace(/[:.]/g, "-")}.json`);
writeFileSync(file, JSON.stringify({ host: "claude-code", model: opt.model, iterations: n, report }, null, 2));
console.log(`report: ${file}`);

function grade(c, call) {
  const want = c.tool && `mcp__gflow__${c.tool}`;
  const got = call ? `${call.toolName}(${JSON.stringify(call.arguments)})` : "no tool call";
  if (want === null) return { pass: !call, why: `expected no tool, got ${got}`, call };
  if (!call || call.toolName !== want) return { pass: false, why: `expected ${c.tool}, got ${got}`, call };
  for (const [key, rule] of Object.entries(c.args)) {
    const v = call.arguments?.[key];
    const ok =
      "eq" in rule ? v === rule.eq
      : "contains" in rule ? JSON.stringify(v ?? "").includes(rule.contains)
      : "absent" in rule ? v == null || (Array.isArray(v) && v.length === 0)
      : false;
    if (!ok) return { pass: false, why: `${key}: wanted ${JSON.stringify(rule)}, got ${got}`, call };
  }
  return { pass: true, why: "", call };
}
