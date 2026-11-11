r"""#997: where is the caret when gflow types the 4th ``@``, and does the picker open? ($0)

The reporter (external, gflow 0.83.1, macOS) says that on flow.google.com the 4th and
later references never attach: before every ``@``, ``_mention_by_token`` /
``_mention_by_name`` click the CENTRE of the composer (``page.locator(COMPOSER).first
.click()``); with three chips the first line is full, the centre click lands the caret
directly behind chip 3 with no space, and the mention plugin does not open its picker
for an ``@`` typed there. Proposed fix: after the click, collapse a DOM Range to the end
of the contenteditable before typing ``@``.

This drives exactly that gesture, N mentions per run, in four ARMS, on a fresh editor
load per run (image mode bound first, as the in-place path does):

  click         production: composer click, then ``@``            (the control)
  range_end     click + reporter's DOM Range collapsed to end     (the proposed fix)
  end_key       click + ``End``                                   (reporter: does NOT help)
  ctrl_end      click + ``Control+End``                           (a keyboard alternative)

Per mention it records, BEFORE typing ``@``: the click point and ``elementFromPoint``
there; the selection (anchor node, offset, whether the node immediately before the caret
is a chip, chips before/after the caret, text after the caret, caret rect); chip line
tops (how many visual lines). AFTER ``@`` (when production types its query): picker
option count and the composer tail. The commit is production's own (see AMENDED below);
it presses Enter only when the target option is offered, and a run stops at its first
failed mention.

COST: navigation, the settings pane, DOM reads and typing only. NOTHING IS SUBMITTED;
the composer is cleared at the end of every run and the page reloaded before the next,
which also drops any client-side request state the chips left behind.

AMENDED after two invalid runs (2026-10-19 17:00, 17:03; the reading below is unchanged):
a hand-rolled commit (bare-picker Enter, then a caption query + token pick) added no chip
even for mention 1, so it measured the spike, not #997. Each mention now calls
production ``MigratedComposer._mention_by_token`` UNCHANGED, with ``page.keyboard.type``
wrapped: the hook fires after production's composer click and before its ``@``, records
the caret, and (fix arms only) moves it. Targets are project grid images
(``img[data-media-id]``) with their picker caption as the query — the in-place path.

Pre-registered reading (written before the first run, 2026-10-19):

  control arm, mention 4 picker fails R/R runs, and in those runs the caret sits
      directly behind a chip (not at document end)
      -> reproduced; the reporter's mechanism is observed, stable.
  control arm mention 4 fails in some runs only -> it flaps; the mechanism is real
      but layout/timing dependent (viewport width decides when line 1 fills).
  control arm, mentions 1..N all open the picker in 0/R failing runs
      -> DOES NOT REPRODUCE HERE; settles nothing (the reporter's viewport/OS may wrap
      at a different chip count). Read the chip line count: if all chips fit on one line
      the precondition (a wrap) was never met, and that is the finding.
  range_end arm opens the picker for every mention while control fails
      -> the proposed fix is supported by a controlled comparison.
  end_key arm fails like control -> the reporter's "End does not help" holds.
  The failing mention number need not be 4: it is wherever line 1 fills at THIS width.

Added 2026-10-19 ~17:12, before any --send-prompt run (run 1 of the matrix had shown the
control arm inserting chip 4 BEFORE chip 3): with --send-prompt and exactly 4 mentions,
  control arm sequence has PROMPT anywhere but last, R/R -> the wedged caret also splits
      the user's prompt around chips (a second, silent consequence); range_end arm PROMPT
      last -> the proposed fix also covers it.
  PROMPT last in the control arm -> no prompt-placement consequence observed.

    uv run python scripts/dev/spike_997_fourth_ref_caret.py \
        --profile denon82 --project <uuid> [--mentions 5] [--runs 3] [--arms click range_end]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gflow_cli.api.image import GenerateImageRequest  # noqa: E402
from gflow_cli.api.transports.migrated_composer import (  # noqa: E402
    _OPTION_TITLES_JS,
    _OPTION_TOKENS_JS,
    COMPOSER,
    MENTION_CHIP,
    PICKER_OPTION,
    MigratedComposer,
)

from _spike_common import build_client, default_out_path, resolve_profile_dir, step  # noqa: E402, isort: skip

ARMS = ("click", "range_end", "end_key", "ctrl_end")

# The reporter's proposed fix, verbatim in effect.
_RANGE_END_JS = """(sel) => {
  const ce = document.querySelector(sel); if (!ce) return;
  ce.focus();
  const r = document.createRange(); r.selectNodeContents(ce); r.collapse(false);
  const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
}"""

_CARET_JS = """([sel, chipSel]) => {
  const ce = document.querySelector(sel);
  if (!ce) return {composer: false};
  const s = window.getSelection();
  const out = {
    composer: true,
    focused: document.activeElement === ce || ce.contains(document.activeElement),
    composer_rect: (() => { const b = ce.getBoundingClientRect();
      return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)]; })(),
    chips: ce.querySelectorAll(chipSel).length,
    chip_line_tops: [...new Set([...ce.querySelectorAll(chipSel)].map(
      c => Math.round(c.getBoundingClientRect().top)))],
    text_tail: JSON.stringify((ce.textContent || '').slice(-40)),
    html_tail: ce.innerHTML.slice(-500),
  };
  if (!s || !s.rangeCount) { out.selection = null; return out; }
  const r = s.getRangeAt(0);
  const a = s.anchorNode;
  out.selection = {
    in_composer: ce.contains(r.startContainer),
    collapsed: r.collapsed,
    anchor_node: a ? (a.nodeType === 3 ? '#text' : a.nodeName) : null,
    anchor_offset: s.anchorOffset,
    anchor_parent_class: a && a.parentElement ? String(a.parentElement.className).slice(0, 80) : null,
  };
  // The node immediately before the caret, and whether it is (inside) a chip.
  let prev = null;
  const c = r.startContainer, o = r.startOffset;
  if (c.nodeType === 3) {
    if (o > 0) prev = {kind: 'text', char: JSON.stringify(c.data.slice(o - 1, o))};
    else { let n = c; while (n && n !== ce && !n.previousSibling) n = n.parentNode;
           prev = n && n !== ce ? {kind: 'node', node: n.previousSibling} : null; }
  } else {
    const n = o > 0 ? c.childNodes[o - 1] : null;
    prev = n ? {kind: 'node', node: n} : null;
  }
  if (prev && prev.kind === 'node') {
    const n = prev.node;
    const el = n.nodeType === 1 ? n : n.parentElement;
    prev = {kind: n.nodeType === 3 ? 'text' : n.nodeName,
            is_chip: !!(el && (el.matches(chipSel) || el.querySelector(chipSel) || el.closest(chipSel))),
            char: n.nodeType === 3 ? JSON.stringify(n.data.slice(-1)) : null};
  }
  out.selection.before_caret = prev;
  const all = [...ce.querySelectorAll(chipSel)];
  out.selection.chips_before_caret = all.filter(ch => {
    const x = document.createRange(); x.setStartAfter(ch);
    return r.compareBoundaryPoints(Range.START_TO_START, x) >= 0; }).length;
  const tail = document.createRange(); tail.selectNodeContents(ce); tail.setStart(r.endContainer, r.endOffset);
  out.selection.text_after_caret = JSON.stringify(tail.toString().slice(0, 40));
  out.selection.chips_after_caret = all.length - out.selection.chips_before_caret;
  const cr = r.getBoundingClientRect();
  out.selection.caret_rect = [Math.round(cr.left), Math.round(cr.top)];
  return out;
}"""

_GRID_JS = r"""() => [...document.querySelectorAll('img[data-media-id]')].map(e => {
  const m = (e.getAttribute('src') || '').match(/\/asb\/([A-Za-z0-9_-]+)/);
  return [e.getAttribute('data-media-id'), m ? m[1] : ''];
}).filter(x => x[1])"""

_PROMPT_MARK = "SPIKE997PROMPT"

# Document order of chips (by their text) and the prompt marker.
_SEQUENCE_JS = """([sel, chipSel]) => {
  const ce = document.querySelector(sel); if (!ce) return null;
  const out = [];
  const walk = (n) => {
    if (n.nodeType === 1 && n.matches(chipSel)) { out.push('chip:' + (n.textContent || '').trim()); return; }
    if (n.nodeType === 3 && n.data.includes('SPIKE997PROMPT')) { out.push('PROMPT'); return; }
    for (const c of n.childNodes) walk(c);
  };
  walk(ce);
  return out;
}"""

_POINT_JS = """([x, y, chipSel]) => {
  const e = document.elementFromPoint(x, y);
  if (!e) return null;
  return {tag: e.tagName, cls: String(e.className).slice(0, 80),
          in_chip: !!e.closest(chipSel), contenteditable: e.closest('[contenteditable]') !== null};
}"""


async def _hook_state(page: Any, arm: str) -> dict[str, Any]:
    """Runs AFTER production's composer click and BEFORE its ``@`` keystroke."""
    box = await page.locator(COMPOSER).first.bounding_box()
    pt = None
    if box:  # Playwright clicks the centre of the box; the click has just happened there
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        pt = {
            "x": round(x),
            "y": round(y),
            "element": await page.evaluate(_POINT_JS, [x, y, MENTION_CHIP]),
        }
    after_click = await page.evaluate(_CARET_JS, [COMPOSER, MENTION_CHIP])
    if arm == "range_end":
        await page.evaluate(_RANGE_END_JS, COMPOSER)
        await page.wait_for_timeout(300)
    elif arm == "end_key":
        await page.keyboard.press("End")
        await page.wait_for_timeout(300)
    elif arm == "ctrl_end":
        await page.keyboard.press("Control+End")
        await page.wait_for_timeout(300)
    before_at = (
        after_click if arm == "click" else await page.evaluate(_CARET_JS, [COMPOSER, MENTION_CHIP])
    )
    return {"click_point": pt, "after_click": after_click, "before_at": before_at}


async def _targets(page: Any, n: int) -> list[tuple[str, str, str]]:
    """(media_id, /asb/ token, picker caption) for n distinct project images, $0."""
    grid = await page.evaluate(_GRID_JS)
    await page.locator(COMPOSER).first.click(timeout=5000)
    await page.keyboard.type("@", delay=120)
    await page.wait_for_timeout(2500)
    titles = [str(t) for t in await page.evaluate(_OPTION_TITLES_JS, PICKER_OPTION)]
    tokens = [str(t) for t in await page.evaluate(_OPTION_TOKENS_JS, PICKER_OPTION)]
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(800)
    caption = {tok: t for tok, t in zip(tokens, titles, strict=False) if tok and t}
    out: list[tuple[str, str, str]] = []
    seen_caps: set[str] = set()
    for media_id, token in grid:
        cap = caption.get(token, "")
        if cap and cap not in seen_caps and "\n" not in cap and "@" not in cap and len(cap) <= 120:
            seen_caps.add(cap)
            out.append((media_id, token, cap))
    return out[:n]


async def _run(
    page: Any,
    composer: MigratedComposer,
    project: str,
    arm: str,
    targets: list[tuple[str, str, str]],
    send_prompt: bool = False,
) -> dict[str, Any]:
    """Production ``_mention_by_token`` per target, unchanged; the arm acts at the hook."""
    await page.reload(wait_until="domcontentloaded", timeout=45_000)
    kind = await composer.ensure_editor(page, project)
    await composer.apply_image_settings(page, GenerateImageRequest(prompt="spike-997"))
    await composer.clear_composer(page)
    run: dict[str, Any] = {
        "arm": arm,
        "composer_kind": kind,
        "viewport": page.viewport_size,
        "mentions": [],
    }
    kb = page.keyboard
    orig_type = kb.type
    pending: dict[str, Any] = {}

    async def hooked(text: str, **kw: Any) -> None:
        if text == "@":
            pending.update(await _hook_state(page, arm))
        elif text not in (" ",) and "before_at" in pending and "picker_options" not in pending:
            # production has waited 2200 ms after '@': did the picker open?
            pending["picker_options"] = await page.locator(PICKER_OPTION).count()
            pending["after_at"] = await page.evaluate(_CARET_JS, [COMPOSER, MENTION_CHIP])
        await orig_type(text, **kw)

    kb.type = hooked  # type: ignore[method-assign]
    try:
        for i, (media_id, token, cap) in enumerate(targets, start=1):
            pending.clear()
            try:
                await composer._mention_by_token(page, cap, token, media_id, expect_chips=i)  # noqa: SLF001
                outcome = "attached"
            except Exception as exc:  # noqa: BLE001 - the outcome under test
                outcome = f"{type(exc).__name__}: {exc}"[:240]
            chips = await composer.read_chips(page)
            run["mentions"].append(
                {"i": i, **pending, "outcome": outcome, "chips_after": len(chips)}
            )
            if outcome != "attached":
                break
        if send_prompt and run["mentions"] and run["mentions"][-1]["outcome"] == "attached":
            # Production follows the mentions with send_prompt(append=True), which types
            # wherever the last mention left the caret. Where does the prompt land?
            kb.type = orig_type  # type: ignore[method-assign]
            await composer.send_prompt(page, _PROMPT_MARK, append=True)
            await page.wait_for_timeout(500)
            run["sequence"] = await page.evaluate(_SEQUENCE_JS, [COMPOSER, MENTION_CHIP])
    finally:
        kb.type = orig_type  # type: ignore[method-assign]
        await composer.clear_composer(page)
    run["attached"] = sum(1 for m in run["mentions"] if m["outcome"] == "attached")
    return run


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--mentions", type=int, default=5)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    ap.add_argument(
        "--send-prompt",
        action="store_true",
        help="after the mentions, call production send_prompt(append=True) and record order",
    )
    args = ap.parse_args()
    composer = MigratedComposer()
    out = default_out_path("spike_997_fourth_ref_caret")
    findings: dict[str, Any] = {"project": args.project, "runs": []}

    def save() -> None:
        out.write_text(json.dumps(findings, indent=2), encoding="utf-8")

    async with build_client(resolve_profile_dir(args.profile)) as client:
        page = client._page  # noqa: SLF001 - dev instrument
        assert page is not None
        await composer.ensure_editor(page, args.project)
        targets = await _targets(page, args.mentions)
        findings["targets"] = [(m[:8], t[:8], len(c)) for m, t, c in targets]
        step("targets", f"{len(targets)} distinct captioned images in grid+picker")
        if len(targets) < 4:
            step("abort", "need >= 4 referenceable images in this project")
            save()
            return 2
        for r in range(1, args.runs + 1):
            for arm in args.arms:  # interleaved, so drift over time hits every arm alike
                try:
                    run = await _run(page, composer, args.project, arm, targets, args.send_prompt)
                    if "sequence" in run:  # chip captions -> requested order (1-based)
                        order = {c: k for k, (_, _, c) in enumerate(targets, start=1)}
                        run["sequence"] = [
                            s if s == "PROMPT" else order.get(s[5:], "?") for s in run["sequence"]
                        ]
                except Exception as exc:  # noqa: BLE001 - record and keep measuring
                    run = {"arm": arm, "error": f"{type(exc).__name__}: {exc}"[:300]}
                    try:
                        await composer.clear_composer(page)
                    except Exception:  # noqa: BLE001
                        pass
                run["run"] = r
                findings["runs"].append(run)
                save()
                fails = [m for m in run.get("mentions", []) if m["outcome"] != "attached"]
                f = fails[0] if fails else None
                step(
                    f"run{r} {arm}",
                    f"attached={run.get('attached')} "
                    + (
                        f"FAIL@{f['i']} picker={f.get('picker_options')} "
                        f"prev={((f.get('before_at') or {}).get('selection') or {}).get('before_caret')} "
                        f"after={((f.get('before_at') or {}).get('selection') or {}).get('text_after_caret')} "
                        f"lines={(f.get('before_at') or {}).get('chip_line_tops')} {f['outcome'][:90]}"
                        if f
                        else ""
                    )
                    + (run.get("error") or ""),
                )
    save()
    step("done", f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
