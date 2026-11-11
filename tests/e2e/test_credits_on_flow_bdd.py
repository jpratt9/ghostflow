"""E2E for #795: `gflow credits user` reads the balance flow.google.com shows.

Binds ``tests/features/credits_on_flow.feature`` (``@e2e @e2e_auth``), so it is selected by
``-m e2e_auth`` like a hand-written e2e — see ``docs/E2E_TESTING.md`` § BDD-bound e2e.

**Why an e2e.** The claim is about Flow: that its app still loads the balance on
``nzlxg`` with ``[0]`` as the number its own account menu shows. A mocked page asserts only
our parser. This runs the real command, then opens the real account menu and compares.

**Cost: zero.** Two page loads of flow.google.com and one click on the profile photo to
open the account menu (closed with Escape). Nothing is generated.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from pytest_bdd import given, scenarios, then, when

from gflow_cli.cli import main

scenarios("../features/credits_on_flow.feature")

#: Structural anchors measured 2026-10-22 (spike 2026-10-22-credits-balance-on-nzlxg.md):
#: Flow's own header avatar (`div.header-user-button`, holding the profile photo) opens its
#: account panel, whose balance sits in `span.credits-count`. The other photo in the top bar,
#: Google's account link, opens Google's popup instead, so the photo alone is not the anchor.
_AVATAR = '.header-user-button:has(img[src*="googleusercontent"])'
_MENU_BALANCE = "flow-account-panel span.credits-count"


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {}


@given("a live profile that reaches the Flow app")
def _profile(e2e_profile_dir: Path, ctx: dict[str, Any]) -> None:
    ctx["dir"] = e2e_profile_dir
    ctx["profile"] = e2e_profile_dir.name.removeprefix("profile_")


@when('I run "gflow credits user --json" for that profile')
def _run(ctx: dict[str, Any]) -> None:
    ctx["result"] = CliRunner().invoke(
        main, ["credits", "user", "--profile", ctx["profile"], "--json"]
    )


@then("the command exits 0")
def _exit_zero(ctx: dict[str, Any]) -> None:
    result = ctx["result"]
    assert result.exit_code == 0, result.output


@then("the JSON reports a non-negative integer balance for that profile")
def _balance(ctx: dict[str, Any]) -> None:
    out = ctx["result"].output
    # The envelope is pretty-printed and opens on a line of its own ("{" alone); log
    # lines are single-line JSON, so they never do.
    lines = out.splitlines(keepends=True)
    first = next(i for i, ln in enumerate(lines) if ln.strip() == "{")
    start = sum(len(ln) for ln in lines[:first])
    payload, _ = json.JSONDecoder().raw_decode(out[start:])
    assert payload["status"] == "ok", payload
    assert payload["profile"] == ctx["profile"]
    assert isinstance(payload["credits"], int) and not isinstance(payload["credits"], bool)
    assert payload["credits"] >= 0
    ctx["credits"] = payload["credits"]


async def _menu_balance(profile_dir: Path) -> int:
    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.transports.migrated_composer import MIGRATED_ROOT_URL

    async with FlowApiClient(profile_dir=profile_dir) as client:
        page = await client._checkout_page()  # noqa: SLF001 - e2e drives the live page
        try:
            await page.goto(MIGRATED_ROOT_URL, wait_until="domcontentloaded", timeout=60_000)
            await page.locator(_AVATAR).first.click(timeout=30_000)
            text = await page.locator(_MENU_BALANCE).first.inner_text(timeout=15_000)
            await page.keyboard.press("Escape")
        finally:
            client._checkin_page(page)  # noqa: SLF001
    digits = re.sub(r"\D", "", text)  # locale-free: the number, never the words around it
    assert digits, "the account menu's balance element held no number"
    return int(digits)


@then("the balance equals the number Flow's account menu shows")
def _matches_menu(ctx: dict[str, Any]) -> None:
    assert asyncio.run(_menu_balance(ctx["dir"])) == ctx["credits"]
