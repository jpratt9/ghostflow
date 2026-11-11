r"""What does gflow report when Chrome loses a SUBMIT reply body, and how often does it? (#1010)

#1009 measured Chrome refusing to hand back the ``maseQ`` upload reply
(``Network.getResponseBody: No data found for resource with given identifier``) on 2 of 45
uploads, every one a SAVED write. #1010 asks whether the same loss on a generation submit
turns an accepted, billed job into a retryable error that invites a second billed submit.
Both submit listeners in ``migrated_composer.py`` read the reply with ``response.text()``:

- video (``submit_and_observe``): ``except Exception: return``. The workflow id is never
  learned, so the status replies are ignored too, and the run waits out
  ``SUBMIT_REPLY_BUDGET_S``.
- image (``submit_images_and_observe``): the raw Playwright error is set on the result.

Three arms, each through the production path:

``inject-image``  ``gflow image t2i --json`` with the FIRST ``ogiZ0b`` reply made unreadable.
``inject-video``  ``gflow video t2v --json`` with the FIRST submit-rpc reply made unreadable.
``count``         N natural t2i runs in one warm client; counts real unreadable bodies on
                  every batchexecute reply gflow reads. No injection.

The inject arms raise the exact error text #1009 captured, then reload the project and
count its media tiles, which answers the question the error cannot: did Flow make it?

**Pre-registered readings** (written before the first run):

| Observation | Reading |
|---|---|
| inject arm: exit 9 + ``retryable: true`` + a tile in the project | #1010 confirmed: a billed, accepted job is reported as a retryable timeout |
| inject arm: non-retryable error + a tile | job lost to the report, but nothing invites a re-submit; lower severity |
| inject arm: success | the driver recovers the result some other way; #1010 does not hold for that arm |
| inject arm: no tile after the wait | the injected run never really submitted; the arm measured nothing |
| count: k>0 of N submit bodies unreadable | the loss happens on submits too; rate k/N |
| count: 0/N | **does not reproduce here; settles nothing** about the natural rate |

**Cost:** ``inject-image`` and ``count`` spend image quota only (zero credits). ``inject-video``
spends ONE clip's credits (``--model veo-lite`` by default). Projects are titled
``spike-1010-<arm>-<ts>``; delete them by hand when done.

    uv run python scripts/dev/spike_migrated_submit_body_loss.py <profile> --arm inject-image
    uv run python scripts/dev/spike_migrated_submit_body_loss.py <profile> --arm inject-video
    uv run python scripts/dev/spike_migrated_submit_body_loss.py <profile> --arm count --runs 10
"""

# ruff: noqa: E501 - the outcome table reads better unwrapped
from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from playwright.async_api import Error as PlaywrightError  # noqa: E402
from playwright.async_api._generated import Response  # noqa: E402

from gflow_cli.api.image import Aspect as ImageAspect  # noqa: E402
from gflow_cli.api.image import GenerateImageRequest  # noqa: E402
from gflow_cli.api.transports.migrated_composer import (  # noqa: E402
    IMAGE_SUBMIT_RPC,
    MIGRATED_PROJECT_URL,
    SUBMIT_RPCS,
    create_project,
    url_rpcid,
)
from gflow_cli.cli import main as gflow_main  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _spike_common import build_client, default_out_path, resolve_profile_dir, step  # noqa: E402, isort: skip

#: The exact text #1009 captured live (docs/superpowers/spikes/2026-10-20-…-eviction.md).
LOST_BODY = (
    "Response.text: Protocol error (Network.getResponseBody): "
    "No data found for resource with given identifier"
)

_original_text = Response.text
_state: dict[str, Any] = {"inject": (), "injected": [], "reads": []}


async def _instrumented_text(self: Response) -> str:
    url = self.url
    rpcid = url_rpcid(url) if "batchexecute" in url else None
    if rpcid is not None and rpcid in _state["inject"] and not _state["injected"]:
        _state["injected"].append({"rpcid": rpcid, "t": time.time()})
        raise PlaywrightError(LOST_BODY)
    try:
        text = await _original_text(self)
    except Exception as exc:
        _state["reads"].append({"rpcid": rpcid, "ok": False, "error": str(exc)[:200]})
        raise
    if rpcid is not None:
        _state["reads"].append({"rpcid": rpcid, "ok": True, "bytes": len(text)})
    return text


Response.text = _instrumented_text  # type: ignore[method-assign]


async def _new_project(profile: str, arm: str) -> str:
    async with build_client(resolve_profile_dir(profile)) as client:
        page = client._page  # noqa: SLF001 - dev instrument
        assert page is not None
        project = await create_project(page, f"spike-1010-{arm}-{time.strftime('%H%M%S')}")
    return project.project_id


async def _tiles(profile: str, project_id: str, *, wait_s: float) -> dict[str, Any]:
    """Reload the project until a media tile shows or ``wait_s`` passes."""
    deadline = time.monotonic() + wait_s
    seen: dict[str, Any] = {}
    async with build_client(resolve_profile_dir(profile)) as client:
        page = client._page  # noqa: SLF001 - dev instrument
        assert page is not None
        while True:
            await page.goto(MIGRATED_PROJECT_URL.format(project_id=project_id))
            await page.wait_for_timeout(8000)
            seen = await page.evaluate(
                "() => ({ids: [...new Set([...document.querySelectorAll('[data-media-id]')]"
                ".map(e => e.getAttribute('data-media-id')))], videos: document.querySelectorAll('video').length,"
                # A finished video tile carries no data-media-id and no <video> until
                # hovered; its poster is the only content image (measured 2026-10-21).
                " content_imgs: [...document.querySelectorAll('img')].filter(i => /flow-content|\\/asb\\//.test(i.src)).length})"
            )
            if seen["ids"] or seen["videos"] or seen["content_imgs"] or time.monotonic() > deadline:
                return seen
            await page.wait_for_timeout(15000)


def _run_cli(argv: list[str]) -> dict[str, Any]:
    out = io.StringIO()
    started = time.monotonic()
    code: Any = 0
    with contextlib.redirect_stdout(out):
        try:
            gflow_main.main(args=argv, prog_name="gflow", standalone_mode=True)
        except SystemExit as exc:
            code = exc.code
    raw = out.getvalue()
    try:
        payload: Any = json.loads(raw.strip().splitlines()[-1]) if raw.strip() else None
    except json.JSONDecodeError:
        payload = raw[-2000:]
    return {"exit": code, "elapsed_s": round(time.monotonic() - started, 1), "json": payload}


def _inject(profile: str, arm: str, model: str | None) -> dict[str, Any]:
    project_id = asyncio.run(_new_project(profile, arm))
    step("project", project_id)
    if arm == "inject-image":
        _state["inject"] = (IMAGE_SUBMIT_RPC,)
        argv = ["image", "t2i", "a teal origami crane on a wooden table", "--count", "1"]
        wait_s = 120.0
    else:
        _state["inject"] = SUBMIT_RPCS
        argv = ["video", "t2v", "a slow pan across a teal origami crane on a wooden table"]
        argv += ["--model", model] if model else []
        wait_s = 420.0
    argv += ["--project", project_id, "--profile", profile, "--json"]
    result = _run_cli(argv)
    step(
        "cli", f"exit={result['exit']} elapsed={result['elapsed_s']}s injected={_state['injected']}"
    )
    _state["inject"] = ()
    tiles = asyncio.run(_tiles(profile, project_id, wait_s=wait_s))
    step("tiles", json.dumps(tiles))
    return {"project_id": project_id, "cli": result, "injected": _state["injected"], "tiles": tiles}


async def _count(profile: str, runs: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    async with build_client(resolve_profile_dir(profile)) as client:
        page = client._page  # noqa: SLF001 - dev instrument
        assert page is not None
        project = await create_project(page, f"spike-1010-count-{time.strftime('%H%M%S')}")
        step("project", project.project_id)
        for i in range(runs):
            before = len(_state["reads"])
            req = GenerateImageRequest(
                prompt=f"a teal origami crane, study {i + 1}", aspect=ImageAspect.LANDSCAPE
            )
            try:
                image = await client.generate_image(project_id=project.project_id, req=req)
                outcome = f"ok {image.media_name}"
            except Exception as exc:  # noqa: BLE001 - every outcome is data
                outcome = f"{type(exc).__name__}: {str(exc)[:160]}"
            reads = _state["reads"][before:]
            submit = [r for r in reads if r["rpcid"] == IMAGE_SUBMIT_RPC]
            rows.append(
                {
                    "run": i + 1,
                    "outcome": outcome,
                    "submit_reads": submit,
                    "unreadable": [r for r in reads if not r["ok"]],
                }
            )
            step(
                f"run {i + 1}",
                f"{outcome} | submit reads={submit} | unreadable={rows[-1]['unreadable']}",
            )
    return {"project_id": project.project_id, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("profile")
    parser.add_argument("--arm", choices=("inject-image", "inject-video", "count"), required=True)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--model", default="veo-lite", help="inject-video only")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = args.out or default_out_path(f"spike_migrated_submit_body_loss_{args.arm}", ".json")
    if args.arm == "count":
        findings = asyncio.run(_count(args.profile, args.runs))
    else:
        findings = _inject(args.profile, args.arm, args.model)
    out.write_text(json.dumps(findings, indent=2, default=str), encoding="utf-8")
    step("out", str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
