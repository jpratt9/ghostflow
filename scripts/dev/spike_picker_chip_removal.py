r"""How many Backspaces delete a just-committed mention chip? ($0)

Commits the picker's FIRST option for ``--query`` (Enter), then presses Backspace one at
a time, recording the chips and the composer's text after each press. Nothing is
submitted; the composer is cleared at the end.

    uv run python scripts/dev/spike_picker_chip_removal.py \
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
    COMPOSER,
    MigratedComposer,
)

from _spike_common import build_client, default_out_path, resolve_profile_dir, step  # noqa: E402, isort: skip

_STATE_JS = """
(sel) => {
  const c = document.querySelector(sel);
  return {
    text: c ? JSON.stringify(c.textContent) : null,
    html: c ? c.innerHTML.slice(0, 600) : null,
    picker_open: document.querySelectorAll("button.asset-item[role='option']").length,
  };
}
"""


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--query", required=True)
    args = ap.parse_args()
    composer = MigratedComposer()
    rows: list[dict[str, Any]] = []
    async with build_client(resolve_profile_dir(args.profile)) as client:
        page = client._page  # noqa: SLF001 - dev instrument
        assert page is not None
        await composer.ensure_editor(page, args.project)
        await composer.clear_composer(page)
        await page.locator(COMPOSER).first.click(timeout=5000)
        await page.keyboard.type("@", delay=120)
        await page.wait_for_timeout(2200)
        await page.keyboard.type(args.query, delay=100)
        await page.wait_for_timeout(2500)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2500)
        rows.append(
            {
                "after": "enter",
                "chips": await composer.read_chips(page),
                **await page.evaluate(_STATE_JS, COMPOSER),
            }
        )
        for i in range(1, 4):
            await page.keyboard.press("Backspace")
            await page.wait_for_timeout(800)
            rows.append(
                {
                    "after": f"backspace{i}",
                    "chips": await composer.read_chips(page),
                    **await page.evaluate(_STATE_JS, COMPOSER),
                }
            )
        await composer.clear_composer(page)
    out = default_out_path("spike_picker_chip_removal")
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    for r in rows:
        step(
            r["after"],
            f"chips={[(c['text'][:20], c['reference_type']) for c in r['chips']]} "
            f"text={r['text']} picker={r['picker_open']}",
        )
        step("  html", str(r["html"])[:400])
    step("done", f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
