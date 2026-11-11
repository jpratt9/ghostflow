"""E2E: a generated image whose download fails keeps its media id (#1035).

Binds ``tests/features/image_download_failure_records.feature``. Selected by
``-m e2e_image``; see ``docs/E2E_TESTING.md`` § BDD-bound e2e.

**Why an e2e.** The offline tests prove the recorder and each call site with a fake
client. Only a live run proves the real failure lands where we catch it: the
``PermissionError`` comes from ``storage._write_local`` after ``download_image`` fetched
the bytes from Flow, i.e. after a real generation.

**The unwritable directory** is portable and needs no system path: a temp dir with a
deny-write ACE for Everyone on Windows (``icacls``), mode ``0o500`` on POSIX. A control
write proves the denial holds before any quota is spent.

#1091 adds the exit: ``storage.write_asset_async`` classifies that ``OSError`` as a
``ConfigurationError`` (exit 11) instead of letting it reach the "Unexpected error" catch-all.

**Cost.** One image of daily quota per scenario, zero Veo credits.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, scenarios, then, when

from gflow_cli.config import reset_settings
from gflow_cli.mcp import tools as mcp_tools

from .test_image_uuid_ref_e2e import _run_gflow

scenarios("../features/image_download_failure_records.feature")

_PROMPT = "a plain ceramic teapot on a wooden table, soft daylight"
_EVERYONE = "*S-1-1-0"


def _deny_writes(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["icacls", str(path), "/deny", f"{_EVERYONE}:(OI)(CI)W"],
            check=True,
            capture_output=True,
        )
    else:
        path.chmod(0o500)


def _allow_writes(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["icacls", str(path), "/remove:d", _EVERYONE], check=False, capture_output=True
        )
    else:
        path.chmod(0o700)


@pytest.fixture
def unwritable_dir(tmp_path: Path) -> Iterator[Path]:
    path = tmp_path / "unwritable"
    path.mkdir()
    _deny_writes(path)
    try:
        try:
            (path / "control.png").write_bytes(b"x")
        except PermissionError:
            pass
        else:
            pytest.skip("this account can write through the denial (root?); no reading")
        yield path
    finally:
        _allow_writes(path)


@given("an output directory gflow cannot write to", target_fixture="world")
def _world(unwritable_dir: Path, e2e_env: dict[str, str]) -> dict[str, Any]:
    return {"dir": unwritable_dir, "env": e2e_env}


@when("image t2i runs with --out pointed at that directory")
def _t2i(world: dict[str, Any]) -> None:
    world["proc"] = _run_gflow(
        [
            "image",
            "t2i",
            _PROMPT,
            "--model",
            "nano2",
            "--aspect",
            "1:1",
            "--out",
            str(world["dir"]),
        ],
        world["env"],
    )


@when("the MCP image tool generates into that directory")
def _mcp(world: dict[str, Any], e2e_profile_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    del e2e_profile_dir  # selects the real authenticated gflow home
    for key in ("GFLOW_CLI_DB_PATH", "GFLOW_CLI_OUTPUT_DIR", "GFLOW_CLI_HISTORY_PROMPTS"):
        monkeypatch.setenv(key, world["env"][key])
    # MCP may only write inside the output dir (GHSA-hqfj-4jww-76f2); widen it to hold the target.
    monkeypatch.setenv("GFLOW_CLI_OUTPUT_DIR", str(world["dir"].parent))
    reset_settings()
    world["result"] = asyncio.run(
        mcp_tools.gflow_generate_image(
            prompt=_PROMPT,
            model="nano2",
            profile=world["env"]["GFLOW_CLI_PROFILE"],
            output=str(world["dir"] / "teapot.png"),
            wait=True,
        )
    )
    print(f"[1035-mcp] result={ {k: v for k, v in world['result'].items() if k != 'error'} }")


def _catalog(world: dict[str, Any]) -> tuple[list[dict[str, Any]], list[sqlite3.Row]]:
    proc = _run_gflow(["data", "list", "images", "--json"], world["env"])
    assert proc.returncode == 0, proc.stderr[-600:]
    rows = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    with sqlite3.connect(world["env"]["GFLOW_CLI_DB_PATH"]) as conn:
        conn.row_factory = sqlite3.Row
        ops = conn.execute("SELECT status, flow_project_id, mode FROM operations").fetchall()
    return rows, ops


@then("the run fails and stderr names the media id and the project, with no signed URL")
def _cli_failed(world: dict[str, Any]) -> None:
    proc = world["proc"]
    assert proc.returncode != 0, f"exit {proc.returncode}; stderr tail: {proc.stderr[-800:]!r}"
    hint = [line for line in proc.stderr.splitlines() if not line.lstrip().startswith("{")]
    text = "\n".join(hint)
    assert "download failed" in text, text
    assert "flow-content.google" not in proc.stderr
    assert "Signature" not in proc.stderr
    rows, _ = _catalog(world)
    assert len(rows) == 1, rows
    media_id = rows[0]["media_id"]
    assert media_id in text, text
    assert rows[0]["project_id"] in text, text
    # The link is a project URL for THIS project, on one of Flow's two hosts. Not
    # inferred from INFO log lines: the default log level hides them since #1041.
    pid = rows[0]["project_id"]
    shapes = (
        re.compile(rf"https://flow\.google\.com/project/{pid}$"),
        re.compile(rf"https://labs\.google/fx/(?:[a-z]{{2,3}}/)?tools/flow/project/{pid}$"),
    )
    url_lines = [ln.split("project:", 1)[1].strip() for ln in hint if "project:" in ln]
    assert len(url_lines) == 1 and any(r.match(url_lines[0]) for r in shapes), url_lines
    print(f"[1035-cli] media={media_id} project={rows[0]['project_id']}")
    print("[1035-cli] hint:\n" + text)


@then("the failure exits 11 as a configuration error, not as an unexpected error")
def _classified(world: dict[str, Any]) -> None:
    # #1091: the raw PermissionError used to reach the catch-all ("file a bug", exit 1).
    proc = world["proc"]
    assert proc.returncode == 11, f"exit {proc.returncode}; stderr tail: {proc.stderr[-800:]!r}"
    assert "Unexpected error" not in proc.stderr
    # The classified message is Rich console output (stdout), which may wrap.
    flat = "".join(proc.stdout.split())
    assert "Configurationerror:Couldnotwritetheoutputfile" in flat, proc.stdout[-800:]
    assert str(world["dir"]) not in proc.stdout  # the detail is persisted to the catalog


@then("the failed task carries the media id and the project id")
def _mcp_failed(world: dict[str, Any]) -> None:
    result = world["result"]
    assert result.get("status") == "failed", result
    rows, _ = _catalog(world)
    assert len(rows) == 1, rows
    assert result.get("flow_media_id") == rows[0]["media_id"], result
    assert result.get("flow_project_id") == rows[0]["project_id"], result


@then("the catalog keeps the media id with no local copy, under one FAILED operation")
def _catalog_kept(world: dict[str, Any]) -> None:
    rows, ops = _catalog(world)
    assert len(rows) == 1, rows
    assert rows[0]["copy_count"] == 0, rows
    assert rows[0]["local_path"] is None, rows
    assert len(ops) == 1, [dict(o) for o in ops]
    assert ops[0]["status"] == "failed", dict(ops[0])
    assert ops[0]["flow_project_id"] == rows[0]["project_id"], dict(ops[0])
