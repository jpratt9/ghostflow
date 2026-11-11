"""#927: the standalone UiAutomationTransport launch honours GFLOW_CLI_BROWSER_WINDOW_POSITION.

FlowApiClient's launch was live-verified for #923; this is the other launch site,
`UiAutomationTransport.setup(page=None)`, read back through CDP
`Browser.getWindowForTarget`. $0: no generation, one Flow page load per arm.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from gflow_cli.api.transports.ui_automation import UiAutomationTransport
from gflow_cli.config import reset_settings

pytestmark = pytest.mark.e2e


async def _bounds(profile_dir: Path) -> dict[str, Any]:
    transport = UiAutomationTransport()
    await transport.setup(profile_dir)  # standalone: the transport owns the launch
    try:
        ctx, page = transport._ctx, transport._page  # noqa: SLF001 - the e2e reads the window
        assert ctx is not None and page is not None
        cdp = await ctx.new_cdp_session(page)
        win = await cdp.send("Browser.getWindowForTarget")
        return dict(win["bounds"])
    finally:
        await transport.teardown()


@pytest.mark.asyncio
@pytest.mark.e2e_auth
@pytest.mark.parametrize(
    ("position", "corners"),
    [
        # Windows clamped -30000 to -21845 when #923 was measured and stopped clamping by
        # 2026-10-25 (canary #559). Both are off every monitor, which is the contract.
        ("-30000,-30000", {-30000, -21845} if sys.platform == "win32" else {-30000}),
        ("0,0", {0}),
    ],
)
async def test_e2e_standalone_launch_places_the_window(
    e2e_profile_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    position: str,
    corners: set[int],
) -> None:
    monkeypatch.setenv("GFLOW_CLI_BROWSER_WINDOW_POSITION", position)
    reset_settings()

    bounds = await _bounds(e2e_profile_dir)

    assert bounds.get("left") == bounds.get("top"), bounds
    assert bounds.get("left") in corners, bounds
