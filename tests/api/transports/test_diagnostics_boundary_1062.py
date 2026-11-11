"""#1062: page captures outside the incident bundle follow `incident_capture`, and
the remaining page-content paths keep to the closed vocabulary (#890 follow-up)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api.transports import migrated_composer as mc
from gflow_cli.api.transports import ui_automation as ua
from gflow_cli.api.transports import ui_automation_video as uav
from gflow_cli.config import reset_settings


@pytest.mark.asyncio
@pytest.mark.parametrize("capture", [ua._capture_debug_screenshot, uav._capture_debug_screenshot])  # noqa: SLF001
async def test_debug_screenshots_follow_incident_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capture: object
) -> None:
    monkeypatch.setenv("GFLOW_CLI_INCIDENT_CAPTURE", "false")
    reset_settings()
    page = MagicMock()
    page.screenshot = AsyncMock(side_effect=AssertionError("no capture when opted out"))

    assert await capture(page, tmp_path / "out", "debug.png") is None  # type: ignore[operator]
    assert not (tmp_path / "out").exists()


def test_count_panel_dom_dump_is_gone() -> None:
    """It wrote page title, ids, class lists, aria-labels and innerText to the output
    dir; the incident bundle's structural DOM owns that evidence."""
    assert not hasattr(ua.UiAutomationTransport, "_dump_count_panel_dom")


def test_recovery_detail_strips_the_query() -> None:
    page = MagicMock()
    page.url = "https://flow.google.com/project/p?authuser=someone@example.com"
    text = mc._recovery_detail(page, None, RuntimeError("x"))  # noqa: SLF001
    assert "someone@example.com" not in text
    assert "https://flow.google.com/project/p" in text
