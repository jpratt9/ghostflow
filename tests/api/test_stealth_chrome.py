"""StealthChrome: clip_fixer's stealth Chrome in place of a Playwright launch, shared across
gflow processes.

The launcher process and Playwright are faked; nothing starts a browser.
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gflow_cli.api import stealth_chrome
from gflow_cli.api.stealth_chrome import IDLE_S, LAUNCHER, StealthChrome

PAGE_CDP = [["Page.addScriptToEvaluateOnNewDocument", {"source": "stealth()"}]]
ME = os.getpid()


def _state_info(launcher_pid: int, **overrides: Any) -> dict[str, Any]:
    return {
        "launcher_pid": launcher_pid,
        "browser_pid": 4321,
        "cdp": "127.0.0.1:9222",
        "page_cdp": PAGE_CDP,
        "visible": False,
        "proxy": None,
    } | overrides


class _FakeLauncher:
    """A launcher process: once started, it writes its state file, unless told it fails."""

    pid = 777

    def __init__(self, args: list[str], *, starts: bool) -> None:
        self.args = args
        self.killed = False
        self._failed = not starts
        if starts:
            state = Path(args[args.index("--state") + 1])
            state.write_text(json.dumps(_state_info(self.pid, visible="--visible" in args)))

    def poll(self) -> int | None:
        return 1 if self._failed else None

    def kill(self) -> None:
        self.killed = True


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Fakes for the launcher (``world["launches"]``), which pids are alive and the signals sent."""
    record: dict[str, Any] = {
        "launches": [],
        "alive": {ME, _FakeLauncher.pid},
        "signals": [],
        "starts": True,
    }

    def popen(args: list[str], **kwargs: Any) -> _FakeLauncher:
        launcher = _FakeLauncher(args, starts=record["starts"])
        record["launches"].append((launcher, kwargs))
        return launcher

    def kill(pid: int, sig: int) -> None:
        record["signals"].append((pid, sig))
        if sig in (signal.SIGTERM, signal.SIGKILL):
            record["alive"].discard(pid)

    monkeypatch.setattr(stealth_chrome.subprocess, "Popen", popen)
    monkeypatch.setattr(stealth_chrome, "_alive", lambda pid: pid in record["alive"])
    monkeypatch.setattr(stealth_chrome.os, "kill", kill)
    return record


def _fake_playwright() -> tuple[Any, Any, Any, Any, Any]:
    session = MagicMock(send=AsyncMock())
    page = MagicMock(name="page", close=AsyncMock())
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


def _state(tmp_path: Path) -> Path:
    return tmp_path / "stealth_profile_someone.json"


async def test_the_first_open_starts_a_detached_launcher_and_attaches(
    tmp_path: Path, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GFLOW_CLI_STEALTH_PYTHON", "/opt/clip-fixer/python3")
    pw, _browser, context, *_ = _fake_playwright()
    profile = _profile(tmp_path)

    ctx = await StealthChrome().open(pw, profile)

    ((launcher, kwargs),) = world["launches"]
    assert launcher.args == [
        "/opt/clip-fixer/python3",
        str(LAUNCHER),
        str(profile),
        "--state",
        str(_state(tmp_path)),
        "--idle",
        str(IDLE_S),
    ]
    assert kwargs["start_new_session"] is True
    pw.chromium.connect_over_cdp.assert_awaited_once_with("http://127.0.0.1:9222")
    assert ctx is context
    assert (tmp_path / f"{_state(tmp_path).name}.users" / str(ME)).exists()


async def test_a_caller_named_in_the_env_keeps_the_browser_after_this_process(
    tmp_path: Path, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(stealth_chrome.USER_PID_ENV, "4242")
    pw, *_ = _fake_playwright()
    chrome = StealthChrome()
    await chrome.open(pw, _profile(tmp_path))

    await chrome.close()

    users = tmp_path / f"{_state(tmp_path).name}.users"
    assert (users / "4242").exists()  # the launcher clears it once 4242 is gone
    assert not (users / str(ME)).exists()


async def test_a_second_open_attaches_to_the_running_chrome(
    tmp_path: Path, world: dict[str, Any]
) -> None:
    _state(tmp_path).write_text(json.dumps(_state_info(ME, cdp="127.0.0.1:9333")))
    pw, *_ = _fake_playwright()

    await StealthChrome().open(pw, _profile(tmp_path))

    assert world["launches"] == []
    pw.chromium.connect_over_cdp.assert_awaited_once_with("http://127.0.0.1:9333")


async def test_an_off_screen_chrome_is_replaced_for_a_visible_sign_in(
    tmp_path: Path, world: dict[str, Any]
) -> None:
    world["alive"].add(5555)
    _state(tmp_path).write_text(json.dumps(_state_info(5555)))
    pw, *_ = _fake_playwright()

    await StealthChrome().open(pw, _profile(tmp_path), visible=True)

    assert (5555, signal.SIGTERM) in world["signals"]
    ((launcher, _kwargs),) = world["launches"]
    assert launcher.args[-3:] == ["--idle", "0", "--visible"]


async def test_a_dead_launchers_state_is_replaced(tmp_path: Path, world: dict[str, Any]) -> None:
    _state(tmp_path).write_text(json.dumps(_state_info(6666)))  # 6666 isn't alive
    pw, *_ = _fake_playwright()

    await StealthChrome().open(pw, _profile(tmp_path))

    assert len(world["launches"]) == 1


async def test_the_proxy_goes_to_the_launcher(tmp_path: Path, world: dict[str, Any]) -> None:
    pw, *_ = _fake_playwright()

    await StealthChrome().open(pw, _profile(tmp_path), proxy="http://127.0.0.1:7897")

    ((launcher, _kwargs),) = world["launches"]
    assert launcher.args[-2:] == ["--proxy-server", "http://127.0.0.1:7897"]


async def test_open_fails_when_the_launcher_exits_without_starting_chrome(
    tmp_path: Path, world: dict[str, Any]
) -> None:
    world["starts"] = False
    pw, *_ = _fake_playwright()

    with pytest.raises(RuntimeError, match="didn't start"):
        await StealthChrome().open(pw, _profile(tmp_path))
    pw.chromium.connect_over_cdp.assert_not_awaited()


async def test_tabs_are_cloaked_closed_when_done_and_the_browser_left_open(
    tmp_path: Path, world: dict[str, Any]
) -> None:
    pw, browser, context, page, session = _fake_playwright()
    chrome = StealthChrome()
    ctx = await chrome.open(pw, _profile(tmp_path))

    assert await ctx.new_page() is page
    context.new_cdp_session.assert_awaited_once_with(page)
    session.send.assert_awaited_once_with(*PAGE_CDP[0])
    await ctx.close()  # what gflow's teardown calls
    page.close.assert_awaited_once()
    browser.close.assert_not_awaited()

    await chrome.close()

    browser.close.assert_awaited_once()
    assert not (tmp_path / f"{_state(tmp_path).name}.users" / str(ME)).exists()
    assert world["signals"] == []  # nobody told the launcher to quit
    assert _state(tmp_path).exists()


async def test_close_before_open_does_nothing() -> None:
    await StealthChrome().close()
