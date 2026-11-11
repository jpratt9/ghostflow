"""Spike (#1097): what does server shutdown do to a task a tool call detached?

$0, no browser. Runs gflow's REAL `run_stdio` / `run_http` with one extra tool that
`asyncio.create_task`s a long coroutine, then shuts the server down the way a client
does (stdin EOF for stdio, CTRL_BREAK / SIGINT for http) and reads back what the
coroutine's `except CancelledError` managed to write.

    uv run python scripts/dev/spike_mcp_detached_shutdown.py            # both
    uv run python scripts/dev/spike_mcp_detached_shutdown.py stdio

Output goes to scripts/dev/_spike_out/mcp_detached_shutdown/ (gitignored).
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "_spike_out" / "mcp_detached_shutdown"
_DETACHED: set[asyncio.Task[None]] = set()


def _child(transport: str, marker: str, port: int) -> None:
    from gflow_cli.mcp import server as srv

    async def _long(path: Path) -> None:
        path.write_text("started\n")
        try:
            await asyncio.sleep(120)
            with path.open("a") as f:
                f.write("finished\n")
        except asyncio.CancelledError:
            # Stands in for daemon.process_task's mark_interrupted DB write.
            await asyncio.sleep(0.2)
            with path.open("a") as f:
                f.write("cancel-handler-committed\n")
            raise

    @srv.server.tool()
    async def spike_detach() -> dict[str, str]:
        task = asyncio.create_task(_long(Path(marker)))
        _DETACHED.add(task)
        task.add_done_callback(_DETACHED.discard)
        return {"status": "pending"}

    if transport == "stdio":
        asyncio.run(srv.run_stdio())
    else:
        asyncio.run(srv.run_http(port=port))


def _rpc(msg_id: int | None, method: str, params: dict[str, object]) -> bytes:
    body: dict[str, object] = {"jsonrpc": "2.0", "method": method, "params": params}
    if msg_id is not None:
        body["id"] = msg_id
    return (json.dumps(body) + "\n").encode()


_INIT = {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "spike", "version": "0"},
}


def _launch(transport: str, marker: Path, port: int, home: str) -> subprocess.Popen[bytes]:
    env = {**os.environ, "GFLOW_CLI_HOME": home, "PYTHONUTF8": "1"}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    return subprocess.Popen(
        [sys.executable, __file__, "--child", transport, str(marker), str(port)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=(OUT / f"{transport}.stderr.log").open("wb"),
        env=env,
        creationflags=flags,
    )


def _wait_for(marker: Path, text: str, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if marker.exists() and text in marker.read_text():
            return True
        time.sleep(0.1)
    return False


def run_stdio(home: str) -> dict[str, object]:
    marker = OUT / "stdio.marker"
    marker.unlink(missing_ok=True)
    proc = _launch("stdio", marker, 0, home)
    assert proc.stdin and proc.stdout
    proc.stdin.write(_rpc(1, "initialize", _INIT))
    proc.stdin.flush()
    init_reply = proc.stdout.readline().decode()
    proc.stdin.write(_rpc(None, "notifications/initialized", {}))
    proc.stdin.write(_rpc(2, "tools/call", {"name": "spike_detach", "arguments": {}}))
    proc.stdin.flush()
    call_reply = proc.stdout.readline().decode()
    started = _wait_for(marker, "started", 10)
    t0 = time.monotonic()
    proc.stdin.close()  # the client went away
    try:
        code = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = "hung>30s"
    return {
        "initialize_ok": '"result"' in init_reply,
        "tool_reply": call_reply.strip()[:200],
        "task_started": started,
        "exit_code": code,
        "seconds_to_exit": round(time.monotonic() - t0, 2),
        "marker": marker.read_text().splitlines() if marker.exists() else None,
    }


def run_http(home: str) -> dict[str, object]:
    port = 8765
    marker = OUT / "http.marker"
    marker.unlink(missing_ok=True)
    proc = _launch("http", marker, port, home)
    url = f"http://127.0.0.1:{port}/mcp"
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    reply = ""
    for _ in range(50):
        try:
            for i, (method, params) in enumerate(
                [("initialize", _INIT), ("tools/call", {"name": "spike_detach", "arguments": {}})]
            ):
                req = urllib.request.Request(
                    url, data=_rpc(i + 1, method, params), headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    sid = r.headers.get("mcp-session-id")
                    if sid:
                        headers["mcp-session-id"] = sid
                    reply = r.read().decode()[:200]
            break
        except OSError:
            time.sleep(0.2)
    started = _wait_for(marker, "started", 10)
    t0 = time.monotonic()
    if sys.platform == "win32":
        proc.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        proc.send_signal(signal.SIGINT)
    try:
        code = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = "hung>30s"
    return {
        "tool_reply": reply.strip(),
        "task_started": started,
        "exit_code": code,
        "seconds_to_exit": round(time.monotonic() - t0, 2),
        "marker": marker.read_text().splitlines() if marker.exists() else None,
    }


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        _child(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    which = sys.argv[1:] or ["stdio", "http"]
    with tempfile.TemporaryDirectory() as home:
        results = {t: (run_stdio if t == "stdio" else run_http)(home) for t in which}
    print(json.dumps(results, indent=2))
    (OUT / "result.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
