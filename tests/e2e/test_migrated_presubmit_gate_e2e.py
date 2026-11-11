"""#892: the migrated pre-submit gate on the real flow.google.com editor.

#781 added cookie-bar dismissal, the blocking-overlay refusal and the submit hit-test,
proven only against `page.set_content` fixtures. This drives the real editor. The
glue cookie bar is not reliably present (it appeared 17 h after a spike read 0/3), so
the test asserts the invariant across both states: dismissed-or-absent, then both
controls receive pointer events. $0: the gate runs, nothing is submitted.

Needs GFLOW_CLI_E2E_PROFILE (served flow.google.com) and GFLOW_CLI_E2E_PROJECT.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.transports.migrated_composer import (
    COOKIE_BAR,
    READY_ANCHOR,
    MigratedComposer,
)

pytestmark = pytest.mark.e2e

_HIT_TEST_JS = """(el) => {
    const box = el.getBoundingClientRect();
    const top = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return !!top && (top === el || el.contains(top) || top.contains(el));
}"""


@pytest.mark.asyncio
@pytest.mark.e2e_auth
async def test_e2e_presubmit_gate_leaves_both_controls_hit_testable(
    e2e_profile_dir: Path,
) -> None:
    project = os.environ.get("GFLOW_CLI_E2E_PROJECT", "").strip()
    if not project:
        pytest.skip("GFLOW_CLI_E2E_PROJECT must name an existing Flow project id")
    async with FlowApiClient(profile_dir=e2e_profile_dir) as client:
        page = client._page  # noqa: SLF001 - the e2e reads the live page
        assert page is not None
        composer = MigratedComposer()
        if await composer.ensure_editor(page, project) != "classic":
            pytest.skip("this account is not served the classic migrated composer")
        bar_before = await page.locator(COOKIE_BAR).filter(visible=True).count()
        # Production order (`run_images`): the prompt is typed, then the gate runs. On an
        # empty composer the disabled submit lets its `flow-generate-icon-button` wrapper
        # take the hit-test (measured 2026-10-23), so the gate is only meaningful here.
        await composer.send_prompt(page, "a paper boat on a pond")

        submit = await composer._pre_submit_gate(page)  # noqa: SLF001 - the gate under test

        bar_after = await page.locator(COOKIE_BAR).filter(visible=True).count()
        trigger = page.locator(READY_ANCHOR).first
        trigger_hit = await trigger.evaluate(_HIT_TEST_JS)
        submit_hit = await submit.evaluate(_HIT_TEST_JS)

    print(f"[892] cookie bar visible before={bar_before} after={bar_after}")
    assert bar_after == 0
    assert trigger_hit, "settings trigger does not receive pointer events"
    assert submit_hit, "submit button does not receive pointer events"
