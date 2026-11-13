"""clip_fixer's stealth Chrome in place of a Playwright-launched one, shared across gflow processes.

``stealth_launcher.py`` keeps it open, detached, under the Python that has clip_fixer's
requirements, and writes its CDP address to a state file beside the profile. Playwright attaches
over CDP, so the rest of gflow drives Flow exactly as it drove its own Chrome. The first gflow
process to need it starts the launcher; later ones attach to the same Chrome; it quits once none
has used it for IDLE_S (an on-screen one, for signing in, as soon as it's done with). Every tab a
process opens gets the CDP commands clip_fixer's stealth setup sends its first tab, and is closed
when the process is done; closing the context only lets go of the browser.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, TypeGuard

import structlog
from playwright.async_api import BrowserContext, Page

logger = structlog.get_logger(__name__)

LAUNCHER = Path(__file__).resolve().parent.parent / "stealth_launcher.py"
IDLE_S = 60  # an off-screen stealth Chrome nobody has used for this long quits
# A caller making several videos in a row (a content pipeline) names its own pid here, so the
# browser stays open between its ghostflow commands for as long as it runs, and quits IDLE_S after
# it's gone.
USER_PID_ENV = "GFLOW_CLI_STEALTH_USER_PID"
START_TIMEOUT_S = 120.0  # clip_fixer's setup: chromedriver, then Chrome, on a cold machine
QUIT_TIMEOUT_S = 30.0
CLOSE_TIMEOUT_S = 15.0  # for a caller's bounded teardown step


def _alive(pid: int | None) -> TypeGuard[int]:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read(state: Path) -> dict[str, Any] | None:
    try:
        return json.loads(state.read_text())
    except (OSError, ValueError):
        return None


async def _stop(info: dict[str, Any], state: Path) -> None:
    """Have the launcher `info` names quit its Chrome, killing both if it won't, and forget it."""
    launcher = info.get("launcher_pid")
    if _alive(launcher):
        with contextlib.suppress(ProcessLookupError):
            os.kill(launcher, signal.SIGTERM)
        deadline = time.monotonic() + QUIT_TIMEOUT_S
        while _alive(launcher) and time.monotonic() < deadline:
            await asyncio.sleep(0.5)
        for pid in (launcher, info.get("browser_pid")):
            if _alive(pid):
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)
    if _read(state) == info:
        state.unlink(missing_ok=True)


class StealthChrome:
    """This process's use of the stealth Chrome on one profile."""

    def __init__(self) -> None:
        self._browser: Any = None
        self._page_cdp: list[list[Any]] = []
        self._sessions: list[Any] = []  # kept open: a CDP session's scripts go when it does
        self._opened: list[Page] = []  # tabs this process opened, closed when it's done
        self._user: Path | None = None

    async def open(
        self, pw: Any, profile_dir: Path, *, visible: bool = False, proxy: str | None = None
    ) -> BrowserContext:
        """The stealth Chrome's default context on ``profile_dir``, attached over CDP: the one
        already open when it's the same kind, else a new one. Off-screen unless ``visible`` (a
        person signing in needs to see it); through ``proxy`` (GFLOW_CLI_BROWSER_PROXY) when one
        is set."""
        state = profile_dir.parent / f"stealth_{profile_dir.name}.json"
        users = Path(f"{state}.users")
        users.mkdir(parents=True, exist_ok=True)
        self._user = users / str(os.getpid())
        self._user.touch()  # first, so the browser can't go idle under us
        caller = os.environ.get(USER_PID_ENV, "")
        if caller.isdigit():
            (users / caller).touch()  # left for the launcher to clear once that process is gone
        info = _read(state)
        if info is not None and not (
            _alive(info.get("launcher_pid"))
            and info.get("visible") == visible
            and info.get("proxy") == proxy
        ):
            await _stop(info, state)  # gone, or the other kind (on screen or off, another proxy)
            info = None
        if info is not None:
            try:
                self._browser = await pw.chromium.connect_over_cdp(f"http://{info['cdp']}")
            except Exception:
                logger.warning(
                    "stealth_chrome.attach_failed", launcher_pid=info.get("launcher_pid")
                )
                await _stop(info, state)
                info = None
            else:
                logger.info("stealth_chrome.attached", browser_pid=info.get("browser_pid"))
        if info is None:
            info = await self._launch(state, profile_dir, visible, proxy)
            self._browser = await pw.chromium.connect_over_cdp(f"http://{info['cdp']}")
        self._page_cdp = info["page_cdp"]
        context: BrowserContext = self._browser.contexts[0]
        new_page = context.new_page

        async def cloaked_new_page() -> Page:
            page = await new_page()
            await self._cloak(context, page)
            self._opened.append(page)
            return page

        async def let_go(*_args: Any, **_kwargs: Any) -> None:
            await self._close_tabs()  # the browser itself stays, for the next process

        context.new_page = cloaked_new_page  # type: ignore[method-assign]
        context.close = let_go  # type: ignore[method-assign]
        return context

    async def _launch(
        self, state: Path, profile_dir: Path, visible: bool, proxy: str | None
    ) -> dict[str, Any]:
        """Start a launcher, detached so it outlives this process, and wait for its state file."""
        log_path = profile_dir.parent / "stealth_launcher.log"
        python = os.environ.get("GFLOW_CLI_STEALTH_PYTHON", "python3")
        args = [python, str(LAUNCHER), str(profile_dir), "--state", str(state)]
        args += ["--idle", "0" if visible else str(IDLE_S)]
        args += ["--visible"] if visible else []
        args += ["--proxy-server", proxy] if proxy else []
        with log_path.open("ab") as log:
            proc = subprocess.Popen(  # noqa: ASYNC220, S603 - asyncio children die on exit
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=log,
                start_new_session=True,
            )
        deadline = time.monotonic() + START_TIMEOUT_S
        while time.monotonic() < deadline:
            info = _read(state)
            if info is not None and info.get("launcher_pid") == proc.pid:
                logger.info(
                    "stealth_chrome.started", browser_pid=info.get("browser_pid"), visible=visible
                )
                return info
            if proc.poll() is not None:
                break
            await asyncio.sleep(0.5)
        if proc.poll() is None:
            proc.kill()
        raise RuntimeError(f"clip_fixer's stealth Chrome didn't start; see {log_path}")

    async def _cloak(self, context: BrowserContext, page: Page) -> None:
        session = await context.new_cdp_session(page)
        for method, params in self._page_cdp:
            await session.send(method, params)  # pyright: ignore[reportUnknownMemberType]
        self._sessions.append(session)

    async def _close_tabs(self) -> None:
        opened, self._opened = self._opened, []
        for page in opened:
            with contextlib.suppress(Exception):
                await page.close()

    async def close(self) -> None:
        """Close this process's tabs and let go of the browser; it stays open for the next
        process."""
        if self._browser is not None:
            await self._close_tabs()
            with contextlib.suppress(Exception):
                await self._browser.close()  # a CDP attach only disconnects
            self._browser = None
        if self._user is not None:
            self._user.unlink(missing_ok=True)
            self._user = None
