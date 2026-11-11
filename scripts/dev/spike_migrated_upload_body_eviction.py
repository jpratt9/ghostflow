r"""Does Chrome evict the ``maseQ`` reply body before the driver reads it? ($0, #1009)

#1009 reports exit 27 *"maseQ answered 200 without a media id"* on uploads that
succeeded: ``response.text()`` raises ``Network.getResponseBody: No data found for
resource with given identifier`` and ``_upload_via_toolbar`` swallows it as an empty
body. The reporter measured: with 2 x ~2 MB PNG references the SECOND upload's body was
unreadable on every run; a fuller project made even the first fail; fulfilling the reply
through ``page.route`` + ``route.fetch()`` took 0/6 runs to 5/6.

This drives **the real driver method** in one fresh project, alternating two arms in
pairs (A B A B ...) so project fill — the reporter's second variable — is spread evenly
across both instead of confounding them:

  ``baseline``  the shipped path, untouched
  ``route``     the reporter's shim: ``page.route`` + ``route.fetch`` + ``route.fulfill``

Per upload it records whether ``response.text()`` read the ``maseQ`` body or raised (and
the exact error), the driver's outcome, and how many responses / body bytes the page had
already seen (DevTools buffer pressure is the hypothesis). For recovery option (b) —
find the media id again by the run-unique display name, without re-sending anything — it
also records which LATER batchexecute replies carry that display name next to a UUID.

**Pre-registered readings** (written before the first run):

| Observation | Reading |
|---|---|
| baseline shows ``No data found`` on N>0 uploads, route shows 0 | eviction reproduced; the shim works here |
| baseline 0/N unreadable | **does not reproduce here; settles nothing** about #1009 — report unmeasured |
| both arms unreadable at similar rates | the shim is not the fix; the reporter's 5/6 was luck or another variable |
| unreadable rate rises with responses-seen | consistent with buffer pressure, not proof of it |
| some later rpc reply carries the display name + a UUID | option (b) is wire-feasible; name that rpcid |
| none does | option (b) needs a DOM or a new rpc; the picker carries no UUID (#639 recon) |

**Cost:** uploads and project creation only — no submit, zero credits, zero quota. The
uploads stay in a project titled ``spike-1009-<ts>``; delete it by hand when done.

    uv run python scripts/dev/spike_migrated_upload_body_eviction.py <profile> [--pairs 4] [--kb 2048]
"""

# ruff: noqa: E501 - the outcome table and the injected JS read better unwrapped
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from PIL import Image  # noqa: E402

from gflow_cli.api.transports.migrated_composer import (  # noqa: E402
    UPLOAD_RPC,
    MigratedComposer,
    create_project,
    url_rpcid,
)

from _spike_common import build_client, default_out_path, resolve_profile_dir, step  # noqa: E402, isort: skip

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
UPLOAD_GLOB = f"**/*rpcids={UPLOAD_RPC}*"
#: Option (c): read the reply in the page's own JS, which no DevTools buffer can evict.
_HOOK_JS = r"""(() => {
  if (window.__gfm) return; window.__gfm = [];
  const hit = u => String(u || "").includes("rpcids=maseQ");
  const of = window.fetch;
  window.fetch = async function (...a) {
    const r = await of.apply(this, a);
    try { if (hit((a[0] && a[0].url) || a[0])) r.clone().text().then(t => window.__gfm.push(t)); }
    catch (e) { window.__gfm.push("ERR " + e); }
    return r;
  };
  const oo = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (m, u, ...r) { this.__gfu = u; return oo.call(this, m, u, ...r); };
  const os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (...a) {
    if (hit(this.__gfu)) this.addEventListener("load", () => {
      try { window.__gfm.push("XHR " + this.responseText); } catch (e) { window.__gfm.push("ERR " + e); }
    });
    return os.apply(this, a);
  };
})();"""


def _noise_png(path: Path, kb: int) -> Path:
    """Incompressible RGB noise, so the PNG lands near ``kb`` like the reporter's files."""
    side = int((kb * 1024 / 3) ** 0.5)
    Image.frombytes("RGB", (side, side), os.urandom(side * side * 3)).save(path)
    return path


async def _main(profile: str, pairs: int, kb: int, out: Path) -> int:
    pressure = {"responses": 0, "bytes": 0}
    current: dict[str, Any] = {}
    late: list[dict[str, Any]] = []

    async with build_client(resolve_profile_dir(profile)) as client:
        page = client._page  # noqa: SLF001 - dev instrument
        assert page is not None

        async def on_response(response: Any) -> None:
            pressure["responses"] += 1
            try:
                pressure["bytes"] += int((await response.all_headers()).get("content-length", 0))
            except Exception:  # noqa: BLE001 - a header we cannot read is still a response
                pass
            url = str(getattr(response, "url", ""))
            if "batchexecute" not in url:
                return
            rpcid = url_rpcid(url)
            try:
                text = await response.text()
            except Exception as exc:  # noqa: BLE001 - an unreadable body IS the finding
                if rpcid == UPLOAD_RPC and current:
                    current["body"] = f"ERROR: {str(exc)[:200]}"
                return
            if rpcid == UPLOAD_RPC and current:
                current["body"] = f"ok {len(text)}B uuids={len(_UUID_RE.findall(text))}"
            # Option (b): does any OTHER reply name the upload next to an id?
            for name in [r.get("display_name") for r in late if r.get("display_name")]:
                if name and name in text and rpcid != UPLOAD_RPC:
                    late.append(
                        {"carrier": rpcid, "name": name, "uuids": len(_UUID_RE.findall(text))}
                    )

        async def keep(route: Any) -> None:
            resp = await route.fetch()
            await route.fulfill(response=resp)

        page.on("response", on_response)
        await page.add_init_script(_HOOK_JS)  # lands on create_project's navigation
        title = f"spike-1009-{time.strftime('%H%M%S')}"
        project = await create_project(page, title)
        step("project", f"{title} -> {project.project_id}")
        composer = MigratedComposer()
        await composer.ensure_editor(page, project.project_id)

        rows: list[dict[str, Any]] = []
        img_dir = out.with_suffix("")
        img_dir.mkdir(parents=True, exist_ok=True)
        for p in range(pairs):
            for arm in ("baseline", "route") if p % 2 == 0 else ("route", "baseline"):
                for idx in (1, 2):  # the reporter's two references, back to back
                    img = _noise_png(img_dir / f"ref_p{p}_{arm}_{idx}.png", kb)
                    current.clear()
                    current.update(
                        arm=arm, pair=p, idx=idx, img_bytes=img.stat().st_size, **pressure
                    )
                    n0 = await page.evaluate("(window.__gfm || []).length")
                    if arm == "route":
                        await page.route(UPLOAD_GLOB, keep)
                    try:
                        media_id, name = await composer._upload_via_toolbar(  # noqa: SLF001
                            page, project.project_id, img
                        )
                        current.update(result="ok", media_id=media_id, display_name=name)
                        late.append({"display_name": name})  # before the window, not after
                    except Exception as exc:  # noqa: BLE001 - the failure IS the measurement
                        current.update(result=type(exc).__name__, detail=str(exc)[:200])
                        # A failed attempt can leave the toolbar menu open over `+`, which
                        # then blocks every later click (run 3 wedged on exactly that).
                        await page.keyboard.press("Escape")
                    finally:
                        if arm == "route":
                            await page.unroute(UPLOAD_GLOB, keep)
                    await page.wait_for_timeout(3_000)  # let late replies land for (b)
                    got = await page.evaluate(f"(window.__gfm || []).slice({n0})")
                    current["hook"] = [
                        f"{t[:4]} {len(t)}B uuids={len(_UUID_RE.findall(t))}" for t in got
                    ]
                    rows.append(dict(current))
                    step(
                        "upload",
                        json.dumps(
                            {
                                k: current.get(k)
                                for k in (
                                    "arm",
                                    "pair",
                                    "idx",
                                    "responses",
                                    "result",
                                    "body",
                                    "hook",
                                )
                            }
                        ),
                    )

    def rate(arm: str) -> str:
        r = [x for x in rows if x["arm"] == arm]
        bad = sum(1 for x in r if str(x.get("body", "")).startswith("ERROR"))
        ok = sum(1 for x in r if x.get("result") == "ok")
        return f"unreadable {bad}/{len(r)}, driver ok {ok}/{len(r)}"

    carriers = [x for x in late if "carrier" in x]
    hook_ok = sum(1 for x in rows if any("uuids=0" not in h for h in x.get("hook", [])))
    findings = {
        "profile": profile,
        "project": project.project_id,
        "kb": kb,
        "baseline": rate("baseline"),
        "route": rate("route"),
        "option_b_carriers": carriers,
        "option_c_hook_ok": hook_ok,
        "rows": rows,
    }
    out.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    step("verdict", f"baseline: {findings['baseline']}")
    step("verdict", f"route:    {findings['route']}")
    step("verdict", f"option (c) page-JS hook read a body with ids: {hook_ok}/{len(rows)}")
    step("verdict", f"option (b) carriers: {sorted({c['carrier'] for c in carriers})}")
    step("out", str(out))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile")
    parser.add_argument("--pairs", type=int, default=4)
    parser.add_argument("--kb", type=int, default=2048)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = args.out or default_out_path("spike_migrated_upload_body_eviction", ".json")
    return asyncio.run(_main(args.profile, args.pairs, args.kb, out))


if __name__ == "__main__":
    raise SystemExit(main())
