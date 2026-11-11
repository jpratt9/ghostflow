r"""#824 — which of our saved profiles get Flow's agent-only composer? ($0, read-only)

Develop's ``MigratedComposer._is_agent_only_composer`` names the #799 cohort: the
classic settings trigger (``.settings-trigger-button``) is in the DOM but hidden AND no
agent-mode chip (``button.agent-mode-chip``) exists at all. #824 can only be
live-verified on a profile Google has put in that cohort, so this asks which we hold.

COST: zero. Navigation and DOM reads only; no clicks, no project creation. A
batchexecute route aborts any generation rpcid anyway (belt and braces).

Per profile: open the projects page via labs.google (records the host Flow SERVED),
take the first ``a[href*='/project/']`` the page renders, open it, let it settle, then
classify from structure:

  about       landed on /about (no project opened for this session)
  classic     settings trigger visible (chip present? pressed?)
  agent_mode  trigger hidden + chip PRESSED  (#749, recoverable)
  agent_only  trigger hidden + NO chip       (#799/#824 cohort; develop's own probe agrees)
  no_trigger  trigger not in the DOM at all  (drift or a different surface — unmeasured)
  locked      ProfileLockedError (another process holds it — not retried by force)

Pre-registered reading (2026-10-17, before the run): >=1 agent_only -> #824 can be
live-verified on that profile. 0 agent_only -> named external blocker "no agent-only
account held". A profile we could not classify (locked / no project link) settles
nothing about that profile.

    uv run --no-sync python scripts/dev/spike_agent_only_cohort_profiles.py denon82 ffroliva ...
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _spike_common import build_client, default_out_path, step  # noqa: E402, isort: skip

from gflow_cli import auth as _auth  # noqa: E402
from gflow_cli.api.routes import EDITOR_BOOTSTRAP_URL  # noqa: E402
from gflow_cli.api.transports.migrated_composer import (  # noqa: E402
    AGENT_MODE_CHIP,
    AGENT_MODE_CHIP_ANY,
    READY_ANCHOR,
    MigratedComposer,
)
from gflow_cli.errors import ProfileLockedError  # noqa: E402

SUBMITS = ("fZytfe", "YhhmEf", "eb1hJf", "MZZa6b", "nprQif")


async def _abort_submits(route: Any) -> None:
    body = (route.request.post_data or "") + route.request.url
    if any(r in body for r in SUBMITS):
        step("ABORT", "submit rpc blocked")
        await route.abort()
    else:
        await route.continue_()


async def _classify(profile: str) -> dict[str, Any]:
    pdir = _auth.profile_dir(profile)
    row: dict[str, Any] = {"profile": profile}
    if not pdir.exists():
        return row | {"composer": "no_profile_dir"}
    try:
        async with build_client(pdir) as client:
            ctx, page = client._context, client._page  # noqa: SLF001
            assert ctx is not None and page is not None
            await ctx.route(re.compile(r"batchexecute"), _abort_submits)
            await page.goto(EDITOR_BOOTSTRAP_URL, wait_until="domcontentloaded", timeout=60_000)
            try:
                await page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:  # noqa: BLE001 — settle is best-effort
                pass
            await page.wait_for_timeout(3000)
            row["landing"] = f"{urlparse(page.url).netloc}{urlparse(page.url).path}"
            link = page.locator("a[href*='/project/']").first
            if not await link.count():
                return row | {"composer": "no_project_link"}
            href = await link.get_attribute("href") or ""
            pid = href.rstrip("/").split("/project/")[-1].split("/")[0]
            row["project"] = pid[:8] + "..."
            await page.goto(
                f"https://{urlparse(page.url).netloc}/project/{pid}"
                if "flow.google.com" in page.url
                else href
                if href.startswith("http")
                else f"https://{urlparse(page.url).netloc}{href}",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            trig = page.locator(READY_ANCHOR).first
            try:  # attached, not visible: hidden-but-present is the very signal
                await trig.wait_for(state="attached", timeout=30_000)
            except Exception:  # noqa: BLE001
                pass
            await page.wait_for_timeout(4000)
            u = urlparse(page.url)
            row["served"] = f"{u.netloc}{u.path[:9]}"
            row["trigger_in_dom"] = await trig.count() > 0
            row["trigger_visible"] = bool(row["trigger_in_dom"] and await trig.is_visible())
            row["chip_any"] = await page.locator(AGENT_MODE_CHIP_ANY).count()
            row["chip_pressed"] = await page.locator(AGENT_MODE_CHIP).count()
            row["develop_probe_agent_only"] = await MigratedComposer._is_agent_only_composer(  # noqa: SLF001
                page, trig
            )
            if "/about" in u.path:
                c = "about"
            elif row["trigger_visible"]:
                c = "classic"
            elif row["trigger_in_dom"] and row["chip_pressed"]:
                c = "agent_mode"
            elif row["trigger_in_dom"] and not row["chip_any"]:
                c = "agent_only"
            elif row["trigger_in_dom"]:
                c = "hidden_trigger_unpressed_chip"
            else:
                c = "no_trigger"
            row["composer"] = c
            shot = default_out_path(f"agent_only_cohort_{profile}", ".png")
            await page.screenshot(path=str(shot))
            row["screenshot"] = shot.name
    except ProfileLockedError:
        row["composer"] = "locked"
    except Exception as e:  # noqa: BLE001 — one profile's failure is that profile's row
        row["composer"] = "error"
        row["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return row


async def _main(profiles: list[str]) -> int:
    rows = []
    for p in profiles:
        row = await _classify(p)
        step("row", json.dumps(row))
        rows.append(row)
    out = default_out_path("agent_only_cohort_profiles")
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    step("out", str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))
