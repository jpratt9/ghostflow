"""Spike: does `_mint_recaptcha_token` return or raise on a page parked at `about:blank`?

#891 / #781. `migrated_images_prefer` gates the pre-mint skip. For an **unported
form on a warm migrated client** it returns False, so the client mints — and
`uses_page_owned_image_recaptcha` docstring records that every migrated image run
ends by parking the page on `about:blank`. The merged comment justifies that as
harmless:

    a redundant mint on a migrated run is free because the page mints its own

which assumes the mint SUCCEEDS. This measures whether it does.

Already settled offline, so this spike only has to answer the last link:

    flow_host_kind("about:blank")                 -> None   (not "migrated")
    raise_if_migrated(<page at about:blank>)      -> returns, does NOT bail

so the exit-36 guard inside `_mint_recaptcha_token` does not fire and control
reaches `TokenMinter.mint`. The open question is what THAT does.

**Costs nothing and needs no Flow account.** A blank page carries no
`recaptcha/enterprise.js` whoever is signed in, so an anonymous Chromium answers
the question exactly as a logged-in profile would. No credits, no generation, no
account writes.

Run:
    uv run python scripts/dev/spike_mint_on_about_blank.py
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

OUT = Path(__file__).parent / "_spike_out"


async def main() -> None:
    from playwright.async_api import async_playwright

    from gflow_cli.api.transports._common import flow_host_kind, raise_if_migrated

    result: dict[str, Any] = {"spike": "mint_on_about_blank", "issue": "#891"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("about:blank")

        result["page_url"] = page.url
        result["flow_host_kind"] = flow_host_kind(page.url)

        # Link 2: does the exit-36 guard fire here? (Expected: no.)
        try:
            raise_if_migrated(page, at="spike")
            result["raise_if_migrated"] = "returned (no bail to exit 36)"
        except Exception as exc:  # noqa: BLE001 - reporting, not handling
            result["raise_if_migrated"] = f"{type(exc).__name__}: {exc}"

        # Link 3 — the open question. Drive the REAL minter, not a reimplementation.
        from gflow_cli.api._engine import mint_evaluate_kwargs
        from gflow_cli.api.recaptcha import TokenMinter

        minter = TokenMinter(page, mint_evaluate_kwargs=mint_evaluate_kwargs())
        started = time.monotonic()
        try:
            token = await minter.mint("imageGeneration")
            result["mint"] = "RETURNED"
            result["token_len"] = len(token)
        except Exception as exc:  # noqa: BLE001 - the whole point is to see it
            result["mint"] = "RAISED"
            result["mint_error_class"] = type(exc).__name__
            result["mint_error"] = str(exc)[:400]
        result["mint_seconds"] = round(time.monotonic() - started, 2)

        await browser.close()

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "mint_on_about_blank.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
