"""#1053: upscale and extend reach the #974 project-not-found landing check.

Flow answers a --project it will not open with flow.google.com/404?reason=project. The
generation paths stopped with exit 11 since #974; these three paths waited out their own
budget and then reported selector drift (exit 23) or a transport timeout (exit 9).
"""

from __future__ import annotations

from typing import Any

import pytest

from gflow_cli.api.transports import migrated_extend as mx
from gflow_cli.api.transports import migrated_upscale as mu
from gflow_cli.api.transports import migrated_video_upscale as mvu
from gflow_cli.errors import ConfigurationError

_LANDING = "https://flow.google.com/404?reason=project"
_MEDIA = "11111111-1111-1111-1111-111111111111"


class _LandedPage:
    """A page every navigation lands on the not-found page; it has no locator, so
    the unavailable-screen probe reads nothing (see `_shows_unavailable_screen`)."""

    def __init__(self, landing: str = _LANDING) -> None:
        self.url = "about:blank"
        self.visited: list[str] = []
        self._landing = landing

    async def goto(self, url: str, **_k: Any) -> None:
        self.visited.append(url)
        # Measured: only the project page redirects; the clip-editor URL stays put.
        self.url = self._landing if "/edit/" not in url else url

    async def wait_for_url(self, predicate: Any, **_k: Any) -> None:
        if not predicate(self.url):
            raise TimeoutError("url did not match")

    def on(self, *_a: Any) -> None: ...

    def remove_listener(self, *_a: Any) -> None: ...


async def _nothing(*_a: Any, **_k: Any) -> None:
    return None


@pytest.mark.asyncio
async def test_image_upscale_tile_miss_on_the_landing_is_exit_11(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mu, "wait_for_or_none", _nothing)
    with pytest.raises(ConfigurationError, match="reason=project"):
        await mu.open_tile_download_menu(
            _LandedPage(),  # type: ignore[arg-type]
            project_id="p",
            media_id=_MEDIA,
            tile_selector="img",
            tile_timeout_ms=1,
            kind="image",
            prefix="migrated upscale",
            route="upsampleImage",
        )


@pytest.mark.asyncio
async def test_video_upscale_reaches_the_landing_through_the_grid_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The clip-editor URL does not redirect (measured), so the project grid fallback
    is where the landing shows; it must not report drift there."""
    monkeypatch.setattr(mvu, "wait_for_or_none", _nothing)
    monkeypatch.setattr(mu, "wait_for_or_none", _nothing)
    page = _LandedPage()
    with pytest.raises(ConfigurationError, match="reason=project"):
        await mvu._open_download_menu(page, project_id="p", media_id=_MEDIA)  # type: ignore[arg-type]
    assert "/edit/" in page.visited[0] and "/edit/" not in page.visited[-1]


@pytest.mark.asyncio
async def test_extend_listing_timeout_on_the_landing_is_exit_11(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mx, "LISTING_BUDGET_S", 0.01)
    with pytest.raises(ConfigurationError, match="reason=project"):
        await mx._source_clip(_LandedPage(), project_id="p", media_id=_MEDIA)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_extend_listing_timeout_on_a_live_project_keeps_the_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The probe only replaces the diagnosis on the landing; otherwise exit 9 stands."""
    from gflow_cli.errors import TransportTimeoutError

    monkeypatch.setattr(mx, "LISTING_BUDGET_S", 0.01)
    page = _LandedPage(landing="https://flow.google.com/project/p")
    with pytest.raises(TransportTimeoutError):
        await mx._source_clip(page, project_id="p", media_id=_MEDIA)  # type: ignore[arg-type]
    assert page.visited[-1].endswith("/project/p")
