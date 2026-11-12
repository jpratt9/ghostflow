"""StealthChrome: clip_fixer's stealth Chrome in place of a Playwright launch.

The launcher process and Playwright are faked; nothing starts a browser.
"""

from __future__ import annotations

import asyncio
import json
import signal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api import stealth_chrome
from gflow_cli.api.stealth_chrome import LAUNCHER, StealthChrome

PAGE_CDP = [["Page.addScriptToEvaluateOnNewDocument", {"source": "stealth()"}]]
ADDRESS_LINE = (
    b"GFLOW_STEALTH "
    + json.dumps({"cdp": "127.0.0.1:9222", "browser_pid": 4321, "page_cdp": PAGE_CDP}).encode()
    + b"\n"
)


class _FakeProc:
    """The launcher process: its stdout lines, a stdin to close, and whether it exits when asked."""

    def __init__(self, lines: list[bytes], *, exits: bool = True) -> None:
        self.stdout = asyncio.StreamReader()
        for line in lines:
            self.stdout.feed_data(line)
        self.stdout.feed_eof()
        self.stdin = MagicMock()
        self.returncode: int | None = None
        self.killed = False
        self._exits = exits

    async def wait(self) -> int:
        if not self._exits:
            await asyncio.sleep(3600)
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.killed = True


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Record how the launcher is started and hand back the fake process set in ``spawned["proc"]``."""
    record: dict[str, Any] = {}

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        record["args"], record["kwargs"] = args, kwargs
        return record["proc"]

    monkeypatch.setattr(stealth_chrome.asyncio, "create_subprocess_exec", fake_exec)
    return record


def _fake_playwright() -> tuple[Any, Any, Any, Any, Any]:
    session = MagicMock(send=AsyncMock())
    page = MagicMock(name="page")
    context = MagicMock(name="context")
    context.new_page = AsyncMock(return_value=page)
    context.new_cdp_session = AsyncMock(return_value=session)
    browser = MagicMock(contexts=[context], close=AsyncMock())
    pw = MagicMock()
    pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    return pw, browser, context, page, session


def _profile(tmp_path: Path) -> Path:
    profile = tmp_path / "profile_someone"
    profile.mkdir()
    return profile


async def test_open_attaches_over_cdp_and_cloaks_every_new_tab(
    tmp_path: Path, spawned: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GFLOW_CLI_STEALTH_PYTHON", "/opt/clip-fixer/python3")
    spawned["proc"] = _FakeProc([b"[INFO] clip_fixer chatter\n", ADDRESS_LINE])
    pw, _browser, context, page, session = _fake_playwright()
    profile = _profile(tmp_path)

    ctx = await StealthChrome().open(pw, profile)

    assert spawned["args"] == ("/opt/clip-fixer/python3", str(LAUNCHER), str(profile))
    pw.chromium.connect_over_cdp.assert_awaited_once_with("http://127.0.0.1:9222")
    assert ctx is context
    assert (tmp_path / "stealth_launcher.log").exists()
    assert await ctx.new_page() is page
    context.new_cdp_session.assert_awaited_once_with(page)
    session.send.assert_awaited_once_with(*PAGE_CDP[0])


async def test_open_visible_asks_the_launcher_for_an_on_screen_window(
    tmp_path: Path, spawned: dict[str, Any]
) -> None:
    spawned["proc"] = _FakeProc([ADDRESS_LINE])
    pw, *_ = _fake_playwright()

    await StealthChrome().open(pw, _profile(tmp_path), visible=True)

    assert spawned["args"][-1] == "--visible"


async def test_open_hands_the_proxy_to_the_launcher(tmp_path: Path, spawned: dict[str, Any]) -> None:
    spawned["proc"] = _FakeProc([ADDRESS_LINE])
    pw, *_ = _fake_playwright()

    await StealthChrome().open(pw, _profile(tmp_path), proxy="http://127.0.0.1:7897")

    assert spawned["args"][-2:] == ("--proxy-server", "http://127.0.0.1:7897")


async def test_open_fails_when_the_launcher_exits_without_an_address(
    tmp_path: Path, spawned: dict[str, Any]
) -> None:
    spawned["proc"] = _FakeProc([b"Traceback (most recent call last):\n"])
    pw, *_ = _fake_playwright()

    with pytest.raises(RuntimeError, match="didn't start"):
        await StealthChrome().open(pw, _profile(tmp_path))
    pw.chromium.connect_over_cdp.assert_not_awaited()


async def test_close_detaches_and_lets_the_launcher_quit_chrome(
    tmp_path: Path, spawned: dict[str, Any]
) -> None:
    proc = spawned["proc"] = _FakeProc([ADDRESS_LINE])
    pw, browser, *_ = _fake_playwright()
    chrome = StealthChrome()
    await chrome.open(pw, _profile(tmp_path))

    await chrome.close()

    browser.close.assert_awaited_once()
    proc.stdin.close.assert_called_once()
    assert proc.returncode == 0
    assert not proc.killed


async def test_close_kills_the_launcher_and_chrome_when_quitting_hangs(
    tmp_path: Path, spawned: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = spawned["proc"] = _FakeProc([ADDRESS_LINE], exits=False)
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(stealth_chrome, "QUIT_TIMEOUT_S", 0.01)
    monkeypatch.setattr(stealth_chrome.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    pw, *_ = _fake_playwright()
    chrome = StealthChrome()
    await chrome.open(pw, _profile(tmp_path))

    await chrome.close()

    assert proc.killed
    assert killed == [(4321, signal.SIGKILL)]


async def test_close_before_open_does_nothing() -> None:
    await StealthChrome().close()
