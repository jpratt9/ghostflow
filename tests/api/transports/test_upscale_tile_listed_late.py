"""#1067: a tile made seconds ago is not on the project grid's load-time listing yet.

The upscale used to wait 30 s on a grid that could never gain it, then report selector
drift (exit 23); a 20 s pause before the call, or a cold run, passed. Reloading inside
the wait is what lists it."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from gflow_cli.api.transports import migrated_upscale as mu

_MEDIA = "11111111-1111-1111-1111-111111111111"


class _Page:
    url = "https://flow.google.com/project/p"

    def __init__(self) -> None:
        self.reloads = 0

    async def goto(self, url: str, **_k: Any) -> None: ...

    async def reload(self, **_k: Any) -> None:
        self.reloads += 1

    async def wait_for_timeout(self, _ms: int) -> None: ...


@pytest.mark.asyncio
async def test_a_tile_listed_only_after_a_reload_is_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _Page()
    tile = MagicMock()

    async def click() -> None: ...

    tile.click = click

    async def listed_after_one_reload(p: _Page, _sel: str, _ms: int) -> Any:
        return tile if p.reloads else None

    async def nothing(*_a: Any, **_k: Any) -> None: ...

    monkeypatch.setattr(mu, "wait_for_or_none", listed_after_one_reload)
    monkeypatch.setattr(mu, "click_download_button", nothing)
    monkeypatch.setattr(mu, "raise_if_known_landing", nothing)
    await mu.open_tile_download_menu(
        page,  # type: ignore[arg-type]
        project_id="p",
        media_id=_MEDIA,
        tile_selector="img",
        tile_timeout_ms=30_000,
        kind="image",
        prefix="migrated upscale",
        route="upsampleImage",
    )
    assert page.reloads == 1


@pytest.mark.asyncio
async def test_the_video_budget_gets_one_reload_then_reports_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Video upscale's 15 s tile budget is two grid loads: one reload, then exit 23."""
    from gflow_cli.errors import UiSelectorDriftError

    page = _Page()

    async def never(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(mu, "wait_for_or_none", never)
    monkeypatch.setattr(mu, "raise_if_known_landing", never)
    with pytest.raises(UiSelectorDriftError):
        await mu.open_tile_download_menu(
            page,  # type: ignore[arg-type]
            project_id="p",
            media_id=_MEDIA,
            tile_selector="video",
            tile_timeout_ms=15_000,
            kind="video",
            prefix="migrated video upscale",
            route="video_upscale",
        )
    assert page.reloads == 1
