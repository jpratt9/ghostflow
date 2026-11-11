r"""#882 — can `video extend` be DRIVEN through the flow.google.com UI? ($0, abort-armed)

Fork PR #882 ports extend to flow.google.com by minting a reCAPTCHA token itself and
replaying batchexecute ``fZytfe`` via ``page.request.post``. Develop refuses to mint on
that host, and every other migrated port drives the Angular UI and watches the wire
passively. This spike asks whether the UI exposes an Extend path a driver could click.

COST: ZERO credits, ZERO image quota. Every batchexecute request goes through a
context-level route BEFORE any click. The route ABORTS (never continues):

* any rpcid in ``ALWAYS_ABORT`` (fZytfe, YhhmEf, eb1hJf, MZZa6b, nprQif — the measured
  generation / extend submits), and
* once ``--steps`` begin, ANY rpcid not seen during the passive project load and not
  named with ``--allow-rpc`` (an unknown rpc is presumed billable until read).

The aborted request's URL + post body are recorded with ``at=`` and every string longer
than 40 chars redacted (length kept), so a page-minted reCAPTCHA token shows up as
``<redacted:N>`` in its slot rather than as a value. aisandbox ``*Generate*``/``*Extend*``
REST calls are aborted as well, belt and braces.

Steps are given as ``--step`` actions so the path can be walked in short runs, each one
inventorying structure (custom-element tags, mat-icon ligatures, roles, hrefs) before
and after, plus a screenshot. Anchors are structural only; aria-labels are RECORDED (so
a human can read the screenshot against them) but never used as a click anchor.

    uv run --no-sync python scripts/dev/spike_migrated_extend_ui_path.py \
        --profile ffroliva --project <pid> --media <media id> \
        --step "click:<css>" --step "hover:<css>" --step "fill:<css>=text" \
        --step "submit:<css>" [--allow-rpc rqZuUc]

Pre-registered readings (written 2026-10-17, before the first run):

A1  Extend affordance reached by a structural click path -> record the path.
    No affordance after a full inventory of project page + clip view + any scene view
    -> "unmeasured: extend path not found" (NOT "unsupported").
A2  rqZuUc observed (passively, while walking the path) before Extend is reachable
    -> "reaching extend creates a scene" (free, but leaves state: record scene id).
    Extend reachable with no rqZuUc -> "no scene needed".
A3  submit click -> an fZytfe request captured and aborted
      with a long string in inner[1][10][0]  -> "UI-driven port viable; the PAGE mints".
      with no token slot                     -> describe the shape as captured.
    submit click -> no fZytfe, other rpc aborted -> describe what fired.
    submit click -> nothing fired -> "unmeasured: submit path did not reach the wire".
A4  the passive Zzl0ze listing carries a record whose [2] == --media
      -> its [0] is the workflow id (shape recorded); else -> "not in Zzl0ze".

Second round (2026-10-17, #882 takeover task 1; written before the run):

B1  --direct-editor: page.goto(/project/<pid>/edit/<media>) as the FIRST navigation
      -> URL kept + `flow-scene-builder` and `button.add-clip-button` present
         -> "direct goto reaches the extend-capable editor; it replaces the grid walk".
      -> redirected / no builder -> "grid walk required" (record where it landed).
B2  `flow-video-tile` attribute dump: an attribute or a src/href carrying --media
      -> "tile is tied to its media id by <that attribute>"; none -> "no media id in tile DOM".
B3  every Zzl0ze record (len 8) dumped redacted, side by side with the --media one
      -> a slot that differs between image and video records -> "kind is slot <n>";
         none differs -> "kind not distinguishable from Zzl0ze".
B4  rpcids fired by the direct editor load -> does the editor URL itself fire Zzl0ze?
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _spike_common import (  # noqa: E402, isort: skip
    build_client,
    default_out_path,
    resolve_profile_dir,
    step,
)

from gflow_cli.api.transports.batchexecute import parse_frames  # noqa: E402
from gflow_cli.api.transports.migrated_composer import MigratedComposer  # noqa: E402
from gflow_cli.api.transports.migrated_recover import MIGRATED_CLIP_URL  # noqa: E402

ALWAYS_ABORT = {"fZytfe", "YhhmEf", "eb1hJf", "MZZa6b", "nprQif"}
_LONG = 40

_INV_JS = r"""() => {
  const tally = (xs) => { const m = new Map(); for (const k of xs) m.set(k, (m.get(k)||0)+1);
    return Object.fromEntries([...m.entries()].sort((a,b)=>b[1]-a[1])); };
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0
    && getComputedStyle(e).visibility !== 'hidden'; };
  const lig = (e) => { const i = e.querySelector('mat-icon, .google-symbols');
    return i ? (i.textContent||'').trim() : ''; };
  const chain = (e) => { const out = []; let n = e.parentElement;
    while (n && out.length < 3) { if (n.tagName.includes('-')) out.push(n.tagName.toLowerCase());
      n = n.parentElement; } return out; };
  const all = [...document.querySelectorAll('*')];
  const btns = [...document.querySelectorAll('button, [role="button"], [role="menuitem"], a[href]')]
    .filter(vis).map(b => { const r = b.getBoundingClientRect(); return {
      tag: b.tagName.toLowerCase(), role: b.getAttribute('role'), lig: lig(b),
      cls: (b.className||'').toString().split(/\s+/).filter(c => c && !c.startsWith('mdc-')
        && !c.startsWith('mat-mdc') && !c.startsWith('ng-')).slice(0,4).join('.'),
      anc: chain(b), href: b.getAttribute('href'), dis: !!b.disabled,
      aria_recorded_not_anchor: (b.getAttribute('aria-label')||'').slice(0,40),
      x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; });
  const ov = document.querySelector('.cdk-overlay-container');
  return {
    url: location.href, lang: document.documentElement.lang,
    custom_tags: tally(all.map(e => e.tagName.toLowerCase()).filter(t => t.includes('-'))),
    ligatures_visible: tally([...document.querySelectorAll('mat-icon, .google-symbols')]
      .filter(vis).map(e => (e.textContent||'').trim()).filter(t => /^[a-z0-9_]{2,40}$/.test(t))),
    roles: tally([...document.querySelectorAll('[role]')].map(e => e.getAttribute('role'))),
    overlay: ov ? { panes: ov.querySelectorAll('.cdk-overlay-pane').length,
      tags: tally([...ov.querySelectorAll('*')].map(e => e.tagName.toLowerCase()).filter(t=>t.includes('-'))),
      ligs: [...ov.querySelectorAll('mat-icon')].filter(vis).map(e => (e.textContent||'').trim()),
      items: [...ov.querySelectorAll('[role="menuitem"], [role="option"], button')].filter(vis)
        .map(b => ({tag: b.tagName.toLowerCase(), role: b.getAttribute('role'), lig: lig(b),
          aria_recorded_not_anchor: (b.getAttribute('aria-label')||'').slice(0,40),
          text_recorded_not_anchor: (b.textContent||'').replace(/\s+/g,' ').trim().slice(0,50)})) } : null,
    editors: [...document.querySelectorAll('textarea, [contenteditable="true"]')].filter(vis)
      .map(e => ({tag: e.tagName.toLowerCase(), cls: (e.className||'').toString().slice(0,60), anc: chain(e)})),
    videos: [...document.querySelectorAll('video')].length,
    scene_hrefs: [...document.querySelectorAll('a[href*="/scene"]')].map(a => a.getAttribute('href')).slice(0,10),
    buttons: btns,
  };
}"""


_TILES_JS = r"""(media) => [...document.querySelectorAll('flow-video-tile, flow-image-tile, [data-media-id]')]
  .slice(0, 12).map(t => { const attrs = (e) => Object.fromEntries([...e.attributes]
      .filter(a => !a.name.startsWith('_ng')).map(a => [a.name, a.value.slice(0, 160)]));
    const kids = [...t.querySelectorAll('*')].map(e => ({tag: e.tagName.toLowerCase(), a: attrs(e)}))
      .filter(k => Object.keys(k.a).some(n => n.startsWith('data-') || n === 'src' || n === 'href'))
      .slice(0, 8);
    return {tag: t.tagName.toLowerCase(), attrs: attrs(t), kids,
      carries_media: t.outerHTML.includes(media)}; })"""


def _redact(text: str) -> str:
    text = re.sub(r"(at=)[^&]+", r"\1<redacted>", text)
    return re.sub(
        rf"[A-Za-z0-9_\-:.]{{{_LONG + 1},}}",
        lambda m: f"<redacted:{len(m.group(0))}>",
        text,
    )


def _rpcids(url: str, post: str | None) -> set[str]:
    ids = set(parse_qs(urlparse(url).query).get("rpcids", [""])[0].split(",")) - {""}
    if post:
        freq = parse_qs(post).get("f.req", [""])[0]
        ids |= set(re.findall(r'\[\s*"([A-Za-z0-9]{5,7})"\s*,\s*"', freq))
    return ids


def _decode_inner(post: str | None) -> Any:
    """f.req -> [[[rpcid, inner_json, null, "generic"]]] -> json.loads(inner_json)."""
    if not post:
        return None
    try:
        outer = json.loads(parse_qs(post)["f.req"][0])
        return [[row[0], json.loads(row[1])] for row in outer[0]]
    except Exception:  # noqa: BLE001 — shape is the finding; keep the raw if it fails
        return None


def _redact_tree(node: Any) -> Any:
    if isinstance(node, str):
        return f"<redacted:{len(node)}>" if len(node) > _LONG else node
    if isinstance(node, list):
        return [_redact_tree(x) for x in node]
    return node


async def _main(a: argparse.Namespace) -> int:
    report: dict[str, Any] = {
        "profile": a.profile,
        "project": a.project,
        "media": a.media,
        "steps": [],
        "aborted": [],
        "continued_rpcids": {},
        "recaptcha_requests": [],
        "zzl0ze_match": None,
    }
    passive: set[str] = set()
    state = {"active": False}
    phase = {"name": "load"}
    allow = set(a.allow_rpc)

    async def on_batch(route: Any) -> None:
        req = route.request
        post = req.post_data
        ids = _rpcids(req.url, post)
        bad = ids & ALWAYS_ABORT
        if state["active"]:
            bad |= ids - passive - allow
        if bad:
            report["aborted"].append(
                {
                    "rpcids": sorted(ids),
                    "why": sorted(bad),
                    "phase": "active" if state["active"] else "passive",
                    "url": _redact(unquote(req.url)),
                    "post_redacted": _redact(unquote(post or ""))[:4000],
                    "inner_redacted": _redact_tree(_decode_inner(post)),
                }
            )
            step("ABORT", f"{sorted(ids)} (blocked {sorted(bad)})")
            await route.abort()
            return
        if not state["active"]:
            passive.update(ids)
        for i in ids:
            report["continued_rpcids"][i] = report["continued_rpcids"].get(i, 0) + 1
        await route.continue_()

    async def on_rest(route: Any) -> None:
        report["aborted"].append({"rest": _redact(route.request.url)})
        step("ABORT", f"REST {route.request.url[:100]}")
        await route.abort()

    async def on_response(resp: Any) -> None:
        url = str(resp.url)
        if "recaptcha" in url:
            report["recaptcha_requests"].append(urlparse(url).path)
        if "batchexecute" not in url:
            return
        try:
            text = await resp.text()
        except Exception:  # noqa: BLE001
            return
        ids = _rpcids(url, None)
        report.setdefault("rpcids_by_phase", {}).setdefault(phase["name"], []).extend(sorted(ids))
        if ids & set(allow):  # replies to rpcs we let through during the walk: kept, redacted
            report.setdefault("allowed_replies", []).append(
                {"rpcids": sorted(ids), "status": resp.status, "body": _redact(text)[:3000]}
            )
        if "Zzl0ze" not in url and "rqZuUc" not in url:
            return
        frames = parse_frames(text)
        for rpcid, payload in frames:
            if rpcid == "rqZuUc":  # the scene the page created: ids only, kept for cleanup
                report.setdefault("scene_created", []).append(_redact_tree(payload))
            if rpcid != "Zzl0ze":
                continue
            hit = _find_media(payload, a.media)
            if hit is not None:
                report["zzl0ze_match"] = hit
            report.setdefault("zzl0ze_records", []).extend(
                {"phase": phase["name"], "is_media": r[2] == a.media, "rec": _shape(r)}
                for r in _records(payload)
            )

    out_shot = default_out_path("extend_ui_path", "")
    async with build_client(resolve_profile_dir(a.profile)) as client:
        ctx = client._context  # noqa: SLF001
        page = client._page  # noqa: SLF001
        assert ctx is not None and page is not None
        await ctx.route(re.compile(r"batchexecute"), on_batch)
        await ctx.route(
            re.compile(r"aisandbox-pa\.googleapis\.com/.*([Gg]enerate|[Ee]xtend)"), on_rest
        )
        page.on("response", on_response)
        page.on(
            "request",
            lambda r: (
                "recaptcha" in r.url
                and report["recaptcha_requests"].append("REQ " + urlparse(r.url).path)
            ),
        )
        if a.direct_editor:
            await page.goto(
                MIGRATED_CLIP_URL.format(project_id=a.project, media_id=a.media),
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(8000)
            report["direct_editor"] = await page.evaluate(
                """() => ({url: location.href,
                  builder: !!document.querySelector('flow-scene-builder'),
                  add_clip: !!document.querySelector('flow-scene-timeline button.add-clip-button'),
                  extend_menu: !!document.querySelector('flow-extend-menu'),
                  prompt_box: !!document.querySelector('flow-edit-video-prompt-box')})"""
            )
            step("direct", json.dumps(report["direct_editor"]))
        else:
            await MigratedComposer().ensure_editor(page, a.project)
            await page.wait_for_timeout(4000)
            report["tiles"] = await page.evaluate(_TILES_JS, a.media)
        phase["name"] = "walk"
        report["passive_rpcids"] = sorted(passive)
        step("passive", f"rpcids={sorted(passive)}")

        async def snap(label: str) -> None:
            inv = await page.evaluate(_INV_JS)
            shot = Path(f"{out_shot}_{len(report['steps']):02d}_{label}.png")
            await page.screenshot(path=str(shot))
            inv["label"], inv["screenshot"] = label, shot.name
            report["steps"].append(inv)
            step(
                label,
                f"{inv['url']} buttons={len(inv['buttons'])} overlay="
                f"{(inv['overlay'] or {}).get('panes')} shot={shot.name}",
            )

        await snap("start")
        state["active"] = True
        for i, s in enumerate(a.step):
            kind, _, arg = s.partition(":")
            try:
                if kind == "click":
                    await page.locator(arg).first.click(timeout=8000)
                elif kind == "hover":
                    await page.locator(arg).first.hover(timeout=8000)
                elif kind == "fill":
                    sel, _, text = arg.partition("=")
                    await page.locator(sel).first.click(timeout=8000)
                    await page.keyboard.type(text, delay=20)
                elif kind == "press":
                    await page.keyboard.press(arg)
                elif kind == "goto":
                    await page.goto(arg, wait_until="domcontentloaded")
                elif kind == "submit":
                    await page.locator(arg).first.click(timeout=8000)
                    await page.wait_for_timeout(8000)
                elif kind == "wait":
                    await page.wait_for_timeout(int(arg))
                await page.wait_for_timeout(2000)
            except Exception as e:  # noqa: BLE001 — a missed anchor is evidence about the anchor
                step("step", f"{s!r} FAILED: {str(e)[:200]}")
                report.setdefault("failures", []).append({"step": s, "error": str(e)[:300]})
            await snap(f"s{i}_{kind}")

    report["passive_rpcids"] = sorted(passive)
    out = default_out_path("extend_ui_path")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    step("out", str(out))
    return 0


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _records(node: Any) -> list[list[Any]]:
    """Every list shaped like a generation record: uuid at [0] and [2]."""
    out: list[list[Any]] = []
    if isinstance(node, list):
        if len(node) > 2 and all(isinstance(node[i], str) and _UUID.match(node[i]) for i in (0, 2)):
            out.append(node)
        for c in node:
            out.extend(_records(c))
    return out


def _shape(node: Any, depth: int = 0) -> Any:
    """Redacted structure: uuids -> 'U', long strings -> '<s:N>', small values kept."""
    if isinstance(node, str):
        if _UUID.match(node):
            return "U"
        return node if len(node) <= 24 else f"<s:{len(node)}>"
    if isinstance(node, list):
        return [_shape(c, depth + 1) for c in node] if depth < 5 else f"<list:{len(node)}>"
    return node


def _find_media(node: Any, media: str) -> Any:
    """First record list whose [2] == media; returns [0], [2] and the record's length."""
    if isinstance(node, list):
        if len(node) > 2 and node[2] == media and isinstance(node[0], str):
            return {
                "rec0_workflow_id": node[0],
                "rec2_media_id": node[2],
                "rec_len": len(node),
                "rec1": node[1]
                if isinstance(node[1], str | int | None)
                else type(node[1]).__name__,
            }
        for c in node:
            hit = _find_media(c, media)
            if hit is not None:
                return hit
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--profile", default="ffroliva")
    ap.add_argument("--project", required=True)
    ap.add_argument("--media", default="")
    ap.add_argument("--step", action="append", default=[])
    ap.add_argument("--allow-rpc", action="append", default=[])
    ap.add_argument("--direct-editor", action="store_true")
    raise SystemExit(asyncio.run(_main(ap.parse_args())))
