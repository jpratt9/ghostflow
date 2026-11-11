r"""Deep dump of the `@` picker options: what marks a CHARACTER option vs a MEDIA one? ($0)

`spike_migrated_picker_option_kind.py` found no attribute or class on the option
``button`` itself that differs by kind (2026-10-13). This probe goes one level down:
every descendant's tag/classes/attributes, the thumbnail's computed geometry, and the
option's outerHTML — so a structural marker (not a translated label) can be found.

Credit-free: opens the picker and reads it, presses Escape, never Enter, never submits.

    uv run python scripts/dev/spike_picker_entity_marker.py \
        --profile <profile> --project <uuid> --query <name>
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

from gflow_cli.api.transports.migrated_composer import (  # noqa: E402
    _OPTION_TOKENS_JS,
    COMPOSER,
    PICKER_OPTION,
    MigratedComposer,
)

from _spike_common import build_client, default_out_path, resolve_profile_dir, step  # noqa: E402, isort: skip

_DEEP_JS = """
(sel) => [...document.querySelectorAll(sel)].map((o, i) => {
  const nodes = [o, ...o.querySelectorAll('*')];
  return {
    index: i,
    html: o.outerHTML.slice(0, 2500),
    nodes: nodes.map(e => {
      const cs = getComputedStyle(e);
      const r = e.getBoundingClientRect();
      return {
        tag: e.tagName.toLowerCase(),
        cls: typeof e.className === 'string' ? e.className : '',
        attrs: Object.fromEntries([...e.attributes]
          .filter(a => !a.name.startsWith('_ng'))
          .map(a => [a.name, a.value.slice(0, 120)])),
        radius: cs.borderRadius, w: Math.round(r.width), h: Math.round(r.height),
        objectFit: cs.objectFit,
        ownText: [...e.childNodes].filter(n => n.nodeType === 3)
          .map(n => n.textContent.trim()).join('').slice(0, 60),
      };
    }),
    ngContext: typeof o.__ngContext__,
  };
})
"""


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--query", required=True)
    args = ap.parse_args()
    composer = MigratedComposer()
    findings: dict[str, Any] = {"query": args.query}
    async with build_client(resolve_profile_dir(args.profile)) as client:
        page = client._page  # noqa: SLF001 - dev instrument
        assert page is not None
        await composer.ensure_editor(page, args.project)
        await composer.clear_composer(page)
        replies: list[dict[str, Any]] = []

        async def on_response(resp: Any) -> None:
            if "batchexecute" not in resp.url:
                return
            try:
                text = await resp.text()
            except Exception:  # noqa: BLE001 - best effort
                return
            rpc = resp.url.split("rpcids=")[-1].split("&")[0]
            replies.append({"rpc": rpc, "len": len(text), "text": text[:20000]})

        page.on("response", on_response)
        await page.locator(COMPOSER).first.click(timeout=5000)
        await page.keyboard.type("@", delay=120)
        await page.wait_for_timeout(2200)
        await page.keyboard.type(args.query, delay=100)
        await page.wait_for_timeout(2600)
        findings["options"] = await page.evaluate(_DEEP_JS, PICKER_OPTION)
        # Is each option's thumbnail token a media tile in the project grid?
        findings["option_tokens"] = await page.evaluate(_OPTION_TOKENS_JS, PICKER_OPTION)
        findings["grid_tokens"] = await page.evaluate(
            "() => [...document.querySelectorAll('img[data-media-id]')].map(e =>"
            " ((e.getAttribute('src') || '').match(/\\/asb\\/([A-Za-z0-9_-]+)/) || [])[1] || '')"
        )
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        page.remove_listener("response", on_response)
        # Local, gitignored evidence only: replies may carry ids and signed URLs.
        findings["replies"] = replies
        findings["chips_after_escape"] = await composer.read_chips(page)
    out = default_out_path("spike_picker_entity_marker")
    out.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    for o in findings["options"]:
        step(f"opt{o['index']}", json.dumps(o["nodes"])[:1500])
    grid = set(findings["grid_tokens"])
    step("grid tiles", str(len(grid)))
    for i, t in enumerate(findings["option_tokens"]):
        step(f"opt{i} in grid", str(t in grid))
    for r in findings["replies"]:
        step("reply", f"{r['rpc']} {r['len']} bytes")
    step("chips after Escape", str(findings["chips_after_escape"]))
    step("done", f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
