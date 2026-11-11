# MCP tool-selection eval

Does a real agent pick the right gflow MCP tool, with the right arguments? Offline tests
prove the options exist; this proves an agent can find and use them.

```
MCPJam MCPClientManager ──tools/list──▶ real `gflow mcp run`      (snapshot, $0)
claude -p ──▶ stub.mjs (serves the snapshot, records tools/call, never executes)
```

- **Host:** `claude -p` on your Claude Code login. No API key, no MCPJam account or cloud
  (MCPJam's `EvalTest` gates every iteration on its cloud; it is deliberately unused).
- **Cost:** $0 Flow credits, no browser. Each run is one Claude Code request (~1 min).
- **Not CI.** Node is a dev-only dependency of this one folder.

## Run

```bash
cd scripts/dev/mcpjam
npm ci --ignore-scripts
node run.mjs                              # 12 cases x 5 iterations, model sonnet
node run.mjs --only creative-director --iterations 1 --model haiku
```

`GFLOW_BIN` overrides the server binary (default: the repo `.venv`). Point it at another
checkout's `gflow.exe` to A/B a description change. Reports land in the gitignored
`scripts/dev/_spike_out/mcpjam/`.

## Cases

`cases.json`: a prompt, the expected tool (`null` = no mutating call allowed), and
argument rules (`eq`, `contains`, `absent`). The first call to the expected tool is
graded, because models pre-flight with `auth_status` / `list_*` first.

Read-only lookups get fixtures in `run.mjs` (`gflow_list_tools` is the real reply). Without
them the model stops to ask instead of acting, which reads as a false miss.
