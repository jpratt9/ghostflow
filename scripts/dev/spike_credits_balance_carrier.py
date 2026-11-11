r"""Where does flow.google.com carry the user's credit balance? ($0, read-only) — #795

QUESTION. `gflow credits` reads the balance through a labs.google access token and
aisandbox-pa `routes.CREDITS`. Since 2026-10-22 the labs session BFF answers 410 for every
account, so that path is dead everywhere. The 2026-09-14 spike
(docs/superpowers/spikes/2026-09-14-credits-on-migrated-host.md) never found the balance on
flow.google.com: it never opened the account menu and only key-scanned positional bodies.
This spike looks where that one did not.

COST: $0. Navigation, DOM reads, opening and closing the account (avatar) menu. Nothing is
typed, selected, submitted, created, uploaded or deleted. The one optional extra call is
an HTTP GET of `routes.CREDITS` with a Bearer the PAGE ITSELF already sent to aisandbox-pa
(read from a request header in-process, never written to disk or stdout).

PER RUN (``--runs N``, default 2; each run is a fresh navigation of flow.google.com/):
  * the host and path that served (never assumed)
  * every batchexecute reply (rpcid, status, full body -> gitignored capture) and its
    request `f.req`; every aisandbox-pa / labs request (route, status, and only whether an
    Authorization header was present)
  * `WIZ_global_data`: every key whose value is an integer or an integer string
  * the top bar, structurally: clickable elements in the top 96 px with tag, class, whether
    they hold a profile photo (`img[src*="googleusercontent"]`) and their icon ligature
  * the avatar menu: click the element holding the profile photo, record what appears
    (new overlay / dialog / iframe), the integers in it, the structural path of each
    integer's element, and responses fired while it is open; close with Escape
  * cross-match: every integer the UI showed is searched for in every captured reply and
    in WIZ_global_data; a hit prints rpcid + JSON path (never the value)

PRE-REGISTERED READING (written and committed before the first run)
  * lands on /about or accounts.google.com, or no profile photo in the top bar
    -> UNMEASURED for this profile; say which; stop.
  * the avatar menu shows an integer AND the same integer sits at one rpcid + path in N/N runs
    -> CARRIER FOUND for this profile: that rpcid + path. One profile does not generalize;
       a second account is needed before claiming it does.
  * the integer is in a reply in some runs only
    -> the carrier flaps or is fetched lazily; record which phase (load vs menu-open).
  * the avatar menu shows an integer and no reply / WIZ key carries it
    -> rendered from a source not recorded here (iframe, non-batchexecute fetch, computed);
       carrier UNMEASURED; next rung is the HAR harness.
  * the avatar menu shows no integer
    -> the balance is not in the avatar menu on this profile. NOT "no balance on this
       host": the settings pane and any plan page remain unmeasured.
  * the page sent a Bearer to aisandbox-pa and routes.CREDITS answers 200 with it
    -> the existing endpoint still works with a token obtainable on flow.google.com;
       compare its number with the UI.
  * the page never sent a Bearer to aisandbox-pa
    -> no token from this page state; says nothing about other page states.

    python scripts/dev/spike_credits_balance_carrier.py --profile denon82 --runs 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Page, Request, Response

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _spike_common import (  # noqa: E402, isort: skip
    build_client,
    default_out_path,
    resolve_profile_dir,
    step,
)
from gflow_cli.api import routes  # noqa: E402

ROOT = "https://flow.google.com/"
_STEM = "spike_credits_balance_carrier"
_AVATAR = 'img[src*="googleusercontent"]'  # the profile photo; structural, locale-free

_TOPBAR_JS = r"""
() => [...document.querySelectorAll('button, a, [role="button"]')]
  .filter(e => { const r = e.getBoundingClientRect();
                 return r.width > 0 && r.height > 0 && r.top < 96; })
  .map(e => ({
    tag: e.tagName.toLowerCase(), cls: (e.className || '').toString().slice(0, 80),
    photo: !!e.querySelector('img[src*="googleusercontent"]'),
    icon: (e.querySelector('mat-icon, i.google-symbols')?.textContent || '').trim(),
    x: Math.round(e.getBoundingClientRect().left),
  }))
"""

_WIZ_JS = r"""
() => { const w = window.WIZ_global_data || {}; const out = {};
  for (const [k, v] of Object.entries(w))
    if ((typeof v === 'number' && Number.isInteger(v)) ||
        (typeof v === 'string' && /^\d{1,9}$/.test(v))) out[k] = String(v);
  return {keys: Object.keys(w).length, ints: out}; }
"""

# Every visible element whose OWN text holds an integer, with a structural path. Discovery
# only: the text is read to find the number, never used as an anchor.
_INTS_JS = r"""
() => { const out = [];
  const path = e => { const p = [];
    for (let n = e; n && p.length < 6; n = n.parentElement)
      p.unshift(n.tagName.toLowerCase()
        + (n.classList.length ? '.' + [...n.classList].slice(0, 2).join('.') : ''));
    return p.join(' > '); };
  for (const e of document.querySelectorAll('body *')) {
    const own = [...e.childNodes].filter(n => n.nodeType === 3)
      .map(n => n.textContent).join(' ').trim();
    if (!/\d/.test(own) || !e.getClientRects().length) continue;
    for (const m of own.matchAll(/\d[\d.,   ]*\d|\d/g))
      out.push({n: m[0].replace(/[^\d]/g, ''), path: path(e), text: own.slice(0, 80)});
  }
  return out; }
"""


def _rpcid(url: str) -> str | None:
    return (parse_qs(urlparse(url).query).get("rpcids") or [None])[0]


def _paths(node: Any, target: str, prefix: str = "") -> list[str]:
    """JSON paths in *node* whose scalar value equals the integer string *target*."""
    hits: list[str] = []
    if isinstance(node, list):
        for i, v in enumerate(node):
            hits += _paths(v, target, f"{prefix}[{i}]")
    elif isinstance(node, dict):
        for k, v in node.items():
            hits += _paths(v, target, f"{prefix}.{k}")
    elif not isinstance(node, bool) and isinstance(node, int | str) and str(node) == target:
        hits.append(prefix or "$")
    return hits


def _decode_batchexecute(body: str) -> list[tuple[str, Any]]:
    """(rpcid, decoded inner payload) for each wrb.fr frame in a batchexecute reply."""
    out: list[tuple[str, Any]] = []
    for line in body.splitlines():
        if not line.startswith("[["):
            continue
        try:
            frames = json.loads(line)
        except json.JSONDecodeError:
            continue
        for f in frames:
            if isinstance(f, list) and len(f) > 2 and f[0] == "wrb.fr" and isinstance(f[2], str):
                try:
                    out.append((f[1], json.loads(f[2])))
                except json.JSONDecodeError:
                    out.append((f[1], f[2]))
    return out


assert _paths([[1, ["x", 4321]], {"a": "4321"}], "4321") == ["[0][1][1]", "[1].a"]
assert _decode_batchexecute(')]}\'\n\n12\n[["wrb.fr","abc","[1,[42]]",null]]') == [
    ("abc", [1, [42]])
]


async def _one_run(page: Page, run: int, state: dict[str, Any]) -> dict[str, Any]:
    rec: dict[str, Any] = {"run": run, "replies": [], "bearer_seen": False}
    state["rec"], state["phase"] = rec, "load"
    step("nav", f"run {run}: {ROOT}")
    await page.goto(ROOT, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(10_000)
    rec["landed"] = re.sub(r"\?.*", "", page.url)
    rec["wiz"] = await page.evaluate(_WIZ_JS)
    rec["topbar"] = await page.evaluate(_TOPBAR_JS)
    before = {(i["n"], i["path"]) for i in await page.evaluate(_INTS_JS)}
    avatar = page.locator(f"button:has({_AVATAR}), a:has({_AVATAR}), [role=button]:has({_AVATAR})")
    rec["avatar_count"] = await avatar.count()
    if "flow.google.com" not in page.url or "/about" in page.url or not rec["avatar_count"]:
        rec["verdict"] = "UNMEASURED: not on the app, or no profile photo in the top bar"
        return rec
    state["phase"] = "menu"
    await avatar.first.click()
    await page.wait_for_timeout(4_000)
    after = await page.evaluate(_INTS_JS)
    rec["menu_new_ints"] = [i for i in after if (i["n"], i["path"]) not in before]
    rec["menu_frames"] = [re.sub(r"\?.*", "", f.url) for f in page.frames][:10]
    rec["menu_overlays"] = await page.locator(
        ".cdk-overlay-pane:visible, [role=dialog]:visible, [role=menu]:visible"
    ).count()
    shot = default_out_path(f"{_STEM}_run{run}", ".png")
    await page.screenshot(path=str(shot))
    rec["screenshot"] = shot.name
    for _ in range(2):
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
    state["phase"] = "closed"
    return rec


async def _credits_with_page_bearer(page: Page, bearer: str) -> dict[str, Any]:
    resp = await page.context.request.get(
        f"{routes.FLOW_API_BASE}/credits",  # the retired credits route (#795)
        headers={
            "authorization": bearer,
            "origin": "https://flow.google.com",
            "referer": "https://flow.google.com/",
        },
    )
    body = await resp.text()
    return {"status": resp.status, "body": body[:2000]}


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--profile", required=True)
    ap.add_argument("--runs", type=int, default=2)
    args = ap.parse_args()
    profile_dir = resolve_profile_dir(args.profile)
    out: dict[str, Any] = {"profile": args.profile, "runs": []}
    state: dict[str, Any] = {"rec": None, "phase": "load", "bearer": None}
    pending: list[asyncio.Task[None]] = []

    def on_request(req: Request) -> None:
        if "aisandbox-pa.googleapis.com" in req.url and state["rec"] is not None:
            auth = req.headers.get("authorization")
            if auth and auth.lower().startswith("bearer "):
                state["rec"]["bearer_seen"] = True
                state["bearer"] = auth  # memory only; never written

    async def on_response(resp: Response) -> None:
        rec, url = state["rec"], resp.url
        if rec is None or not any(
            h in url for h in ("flow.google.com", "aisandbox-pa", "labs.google")
        ):
            return
        entry: dict[str, Any] = {
            "route": _rpcid(url) or re.sub(r"\?.*", "", url)[:120],
            "status": resp.status,
            "phase": state["phase"],
        }
        if "batchexecute" in url or "aisandbox-pa" in url:
            try:
                entry["body"] = await resp.text()
            except Exception as exc:  # noqa: BLE001 - name the read failure, never hide it
                entry["body_error"] = type(exc).__name__
            if "batchexecute" in url:
                entry["freq"] = (resp.request.post_data or "")[:1500]
        rec["replies"].append(entry)

    async with build_client(profile_dir) as client:
        context = client._context  # noqa: SLF001 - spike reads the live context
        assert context is not None
        context.on("request", on_request)
        context.on("response", lambda r: pending.append(asyncio.ensure_future(on_response(r))))
        page = await context.new_page()
        try:
            for run in range(1, args.runs + 1):
                out["runs"].append(await _one_run(page, run, state))
            if state["bearer"]:
                step("http", "routes.CREDITS with the Bearer the page itself sent")
                out["credits_with_page_bearer"] = await _credits_with_page_bearer(
                    page, state["bearer"]
                )
        finally:
            await asyncio.gather(*pending, return_exceptions=True)
            path = default_out_path(_STEM)
            path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
            step("wrote", str(path))

    # ---- cross-match: summary prints paths and digit counts, never a value ----
    for rec in out["runs"]:
        print(
            f"\nrun {rec['run']}: landed={rec['landed']} avatar={rec.get('avatar_count')} "
            f"bearer_seen={rec['bearer_seen']} wiz_keys={rec['wiz']['keys']} "
            f"overlays={rec.get('menu_overlays')} frames={rec.get('menu_frames')}"
        )
        if rec.get("verdict"):
            print("  ", rec["verdict"])
            continue
        ui = {i["n"] for i in rec["menu_new_ints"] if len(i["n"]) >= 2}
        for i in rec["menu_new_ints"]:
            print(f"  menu int: {len(i['n'])} digits at {i['path']}")
        routes_seen = sorted({(r["route"], r["phase"]) for r in rec["replies"]})
        print("  routes:", routes_seen)
        for n in sorted(ui):
            hits = [f"WIZ:{k}" for k, v in rec["wiz"]["ints"].items() if v == n]
            for r in rec["replies"]:
                for rpc, payload in _decode_batchexecute(r.get("body", "")):
                    hits += [f"{rpc}({r['phase']}){p}" for p in _paths(payload, n)]
                if "aisandbox-pa" in r["route"] and n in r.get("body", ""):
                    hits.append(f"{r['route']}({r['phase']}) raw")
            print(f"  ui int ({len(n)} digits) found at: {hits or 'NOWHERE recorded'}")
    cb = out.get("credits_with_page_bearer")
    if cb:
        ui_all = {i["n"] for rec in out["runs"] for i in rec.get("menu_new_ints", [])}
        print(
            f"\nroutes.CREDITS with page Bearer: status={cb['status']} "
            f"ui_int_in_body={[len(n) for n in ui_all if n in cb['body']]}"
        )
    else:
        print("\nroutes.CREDITS with page Bearer: not attempted (page sent no Bearer)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
