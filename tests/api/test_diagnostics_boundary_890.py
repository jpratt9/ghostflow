"""#890: the migrated composer's failure diagnostics stay inside the review boundary.

A signed-in Flow page puts account identifiers in element ids and class lists, so the
submit-gate blocker report keeps #778's closed vocabulary (tag + framework class
tokens), and nothing is written to the user's output directory: the incident bundle
already holds the screenshot and structural DOM.
"""

from __future__ import annotations

import pytest

from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.errors import UiSelectorDriftError

_COVERED = """
<button style="position:fixed;left:10px;top:10px;width:80px;height:40px">
  <mat-icon>arrow_forward</mat-icon>
</button>
<div id="someone@example.com" class="glue-cookie-notification-bar acct-someone-example"
     style="position:fixed;left:0;top:0;width:300px;height:100px;z-index:9">
  <span>covering</span>
</div>
"""


@pytest.mark.asyncio
async def test_submit_gate_blocker_report_uses_the_closed_vocabulary() -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is unavailable: {exc}")
        try:
            page = await browser.new_page()
            await page.set_content(_COVERED)
            submit = page.locator("button").first
            with pytest.raises(UiSelectorDriftError) as info:
                await MigratedComposer()._verify_submit_target(page, submit)  # noqa: SLF001
        finally:
            await browser.close()

    detail = info.value.detail
    assert "glue-cookie-notification-bar" in detail
    assert "someone@example.com" not in detail
    assert "acct-someone-example" not in detail


def test_ui_failure_detail_writes_no_files_outside_the_incident_bundle() -> None:
    assert not hasattr(MigratedComposer, "_capture_ui_failure")
