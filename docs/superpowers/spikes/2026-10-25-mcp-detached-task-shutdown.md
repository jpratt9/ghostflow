# Spike: what server shutdown does to a detached MCP task (#1097)

**Date:** 2026-10-25 · **Cost:** $0, no browser · **Script:** `scripts/dev/spike_mcp_detached_shutdown.py`

## Question
The #1097 fix runs a `wait=false` job as a task that a tool call detaches with
`asyncio.create_task`. When the server shuts down mid-job, is that task cancelled, and
does the write in its `except CancelledError` handler commit? `process_task`'s
`mark_interrupted` lives in that handler.

## Method
The script runs gflow's real `run_stdio` / `run_http` with one extra tool. The tool
detaches a 120 s coroutine whose cancel handler appends to a marker file after one
`await` (0.2 s). The coroutine has started when the server is shut down the way a client
would do it:
- **stdio:** close stdin.
- **http:** `CTRL_BREAK_EVENT` on Windows, `SIGINT` elsewhere.

## Result (Windows 11, uvicorn 0.52.1, mcp 2.3.0)

| Transport | Exit | Time to exit | Cancel handler committed? |
|---|---|---|---|
| stdio, stdin EOF | 0 | 0.66 s | **yes** |
| http, CTRL_BREAK | 3 | 0.19 s | **no** |

## Why the two differ
- **stdio:** `server.run` returns at EOF. `asyncio.run` then cancels every remaining
  task and runs the loop until each one has finished. The handler completes.
- **http:** uvicorn shuts down gracefully ("Application shutdown complete"). Then
  `Server.capture_signals` **re-raises the captured signal**
  (`signal.raise_signal(captured_signal)`). With the default handler restored, that
  kills the process before `asyncio.run` gets to cancel anything. Because the re-raise
  happens inside `serve()`, code placed after `await server.serve()` never runs either.

## Consequence for the plan (T7)
On HTTP, the drain has to run in the **ASGI lifespan shutdown**: cancel every detached
task and await it, with a time limit. That point is reached before the signal re-raise.
stdio seemed to need no extra code, because `asyncio.run` gave the fake handler time to commit. **Wrong for a real job; see the correction below.**

A hard kill (`taskkill /F`, `SIGKILL`) still leaves the row `processing`. That case stays
under the existing KNOWN_ISSUES manual-reconcile entry.

## Correction, same day: stdio needs the drain too

The stdio row above used a fake coroutine that held no browser. With a real job, the
live e2e (`tests/e2e/test_mcp_wait_false_bdd.py`) once failed to exit within 60 s. The
server log showed why: `browser_teardown.context_close_error` (`TimeoutError`) and then
`force_close_failed`. `asyncio.run` cancels **every** task at once, Playwright's own
connection tasks included, so the job's `context.close()` can never get a reply. It sits
out its 30 s bound, the forced close fails, and the driver stop adds another 10 s.

`run_stdio` therefore calls `drain_detached()` right after `server.run` returns, while
Playwright is still alive. Measured on the same scenario: the server exited **1.1 s**
after stdin closed, with no teardown errors, and the row ended `indeterminate` (that
close landed after submit).
