"""clip_fixer's stealth Chrome in place of a Playwright-launched one.

``stealth_launcher.py`` opens it under the Python that has clip_fixer's requirements and hands back its CDP
address. Playwright attaches over CDP, so the rest of gflow drives Flow exactly as it drove its own Chrome.
Every tab opened through the context gets the CDP commands clip_fixer's stealth setup sends its first tab.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
from pathlib import Path
from typing import Any

import structlog
from playwright.async_api import BrowserContext, Page

logger = structlog.get_logger(__name__)

LAUNCHER = Path(__file__).resolve().parent.parent / "stealth_launcher.py"
MARKER = b"GFLOW_STEALTH "
START_TIMEOUT_S = 120.0  # clip_fixer's setup: chromedriver, then Chrome, on a cold machine
QUIT_TIMEOUT_S = 30.0
CLOSE_TIMEOUT_S = QUIT_TIMEOUT_S + 15.0  # for a caller's bounded teardown step


class StealthChrome:
    """One clip_fixer stealth Chrome on one profile, owned by its launcher process."""

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._browser: Any = None
        self._browser_pid: int | None = None
        self._page_cdp: list[list[Any]] = []
        self._sessions: list[Any] = []  # kept open: a CDP session's scripts go when it does

    async def open(
        self, pw: Any, profile_dir: Path, *, visible: bool = False, proxy: str | None = None
    ) -> BrowserContext:
        """Start the stealth Chrome on ``profile_dir``; its default context, attached over CDP.

        Off-screen unless ``visible`` (a person signing in needs to see it); through
        ``proxy`` (GFLOW_CLI_BROWSER_PROXY) when one is set.
        """
        log_path = profile_dir.parent / "stealth_launcher.log"
        python = os.environ.get("GFLOW_CLI_STEALTH_PYTHON", "python3")
        with log_path.open("ab") as log:
            self._proc = await asyncio.create_subprocess_exec(
                python,
                str(LAUNCHER),
                str(profile_dir),
                *(["--visible"] if visible else []),
                *(["--proxy-server", proxy] if proxy else []),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=log,
            )
        info = await asyncio.wait_for(self._read_info(log_path), START_TIMEOUT_S)
        self._browser_pid = info.get("browser_pid")
        self._page_cdp = info["page_cdp"]
        logger.info("stealth_chrome.started", browser_pid=self._browser_pid, visible=visible)
        self._browser = await pw.chromium.connect_over_cdp(f"http://{info['cdp']}")
        context: BrowserContext = self._browser.contexts[0]
        new_page = context.new_page

        async def cloaked_new_page() -> Page:
            page = await new_page()
            await self._cloak(context, page)
            return page

        context.new_page = cloaked_new_page  # type: ignore[method-assign]
        return context

    async def _read_info(self, log_path: Path) -> dict[str, Any]:
        assert self._proc is not None and self._proc.stdout is not None
        while line := await self._proc.stdout.readline():
            if line.startswith(MARKER):
                return json.loads(line[len(MARKER) :])
        raise RuntimeError(f"clip_fixer's stealth Chrome didn't start; see {log_path}")

    async def _cloak(self, context: BrowserContext, page: Page) -> None:
        session = await context.new_cdp_session(page)
        for method, params in self._page_cdp:
            await session.send(method, params)
        self._sessions.append(session)

    async def close(self) -> None:
        """Detach Playwright and have the launcher quit Chrome, killing both if it hangs."""
        if self._browser is not None:
            with contextlib.suppress(Exception):
                await self._browser.close()  # a CDP attach only disconnects; Chrome is the launcher's
            self._browser = None
        proc, self._proc = self._proc, None
        if proc is None or proc.returncode is not None:
            return
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), QUIT_TIMEOUT_S)
        except TimeoutError:
            logger.warning("stealth_chrome.quit_timeout", browser_pid=self._browser_pid)
            proc.kill()
            if self._browser_pid:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(self._browser_pid, signal.SIGKILL)
