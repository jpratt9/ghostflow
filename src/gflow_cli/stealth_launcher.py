"""Keep clip_fixer's stealth Chrome open on a gflow profile for gflow to attach to.

gflow's own environment doesn't carry clip_fixer's requirements, so gflow starts this file,
detached, under the Python that does (GFLOW_CLI_STEALTH_PYTHON, python3 by default), with
clip_fixer at GFLOW_CLI_CLIP_FIXER (~/dev/clip_fixer by default):

    python3 stealth_launcher.py <profile_dir> --state <file> [--idle <s>] [--visible]
        [--proxy-server <url>]

Once Chrome is up it writes <file>: {"launcher_pid", "browser_pid", "cdp", "page_cdp",
"visible", "proxy"}. page_cdp holds the CDP commands clip_fixer's stealth setup sends to its
first tab (the stealth JS, the visibility and screenX/Y patches), for gflow to send to every
tab it opens. Each gflow process using the browser keeps a file named for its pid in
<file>.users: Chrome stays open while one of them is alive and quits once none has been for
--idle seconds (0: as soon as the last one leaves), when Chrome itself exits, or on SIGTERM.
This file must not import gflow_cli: it runs outside gflow's environment.
"""

# pyright: basic
# Basic, not strict: this runs under clip_fixer's Python, against its untyped scraper package.

import json
import os
import shutil
import signal
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# The window's x and y unless --visible: headed, as Google turns headless away, but out of sight.
OFF_SCREEN = -30000
# Chrome puts a window launched wholly off every screen back on one, so it's moved off once up, as
# dialstream's stealth browser does (scrape/stealth_browser.OFF_SCREEN_X): macOS keeps a sliver of
# it on the leftmost screen's edge.
OFF_SCREEN_X = -10000
CHECK_EVERY_S = 5.0


class _CdpRecorder:
    """Takes the driver's place to capture the commands clip_fixer's stealth setup sends to a
    tab."""

    def __init__(self) -> None:
        self.calls: list[list[Any]] = []

    def execute_cdp_cmd(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append([method, params])
        return {}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _users(users_dir: Path) -> list[int]:
    """The pids in `users_dir` still running; the files of any that aren't are removed."""
    alive: list[int] = []
    for entry in users_dir.glob("*"):
        if entry.name.isdigit() and _alive(int(entry.name)):
            alive.append(int(entry.name))
        else:
            entry.unlink(missing_ok=True)
    return alive


def wait_while_used(
    users_dir: Path,
    idle: float,
    browser_pid: int | None,
    stopped: list[bool],
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> str:
    """Wait while the browser is wanted, then say why it no longer is: "stopped" (SIGTERM),
    "chrome" (Chrome exited) or "idle" (no user alive in `users_dir` for `idle` seconds)."""
    last_used = now()
    while True:
        if stopped:
            return "stopped"
        if browser_pid and not _alive(browser_pid):
            return "chrome"
        if _users(users_dir):
            last_used = now()
        elif now() - last_used >= idle:
            return "idle"
        sleep(CHECK_EVERY_S)


def _write_state(state: Path, info: dict[str, Any]) -> None:
    """Write the state file whole, through a temp file, so nobody reads half of it."""
    written = state.with_name(f"{state.name}.{os.getpid()}.tmp")
    written.write_text(json.dumps(info))
    written.replace(state)


def _forget_state(state: Path) -> None:
    """Remove the state file if it is still this launcher's: before Chrome goes, so nobody
    attaches to it on the way out."""
    try:
        if json.loads(state.read_text()).get("launcher_pid") == os.getpid():
            state.unlink()
    except (OSError, ValueError):
        pass


def main() -> None:
    profile_dir, options = sys.argv[1], sys.argv[2:]

    def option(name: str, default: str | None = None) -> str | None:
        return options[options.index(name) + 1] if name in options else default

    visible, proxy = "--visible" in options, option("--proxy-server")
    state, idle = Path(str(option("--state"))), float(str(option("--idle", "0")))
    users_dir = Path(f"{state}.users")
    sys.stdout = sys.stderr  # clip_fixer's prints go to the log
    stopped: list[bool] = []
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stopped.append(True))
    work_dir = tempfile.mkdtemp(prefix="gflow_stealth_")
    try:
        # SeleniumBase writes its downloaded_files/ lock files into the working directory.
        os.chdir(work_dir)
        sys.path.insert(
            0, os.environ.get("GFLOW_CLI_CLIP_FIXER", str(Path.home() / "dev" / "clip_fixer"))
        )
        from scraper import browser_setup, config  # pyright: ignore[reportMissingImports]

        # A site with no VPN or proxy entry, as dialstream's stealth browser picks.
        config.SITE_NAME = "bot_sannysoft"
        config.USE_INCOGNITO = False  # the profile keeps its Google sign-in
        config.VISIBLE_BROWSER = True  # never minimized: a minimized window takes no clicks
        browser_setup._get_profile_path = lambda: profile_dir
        browser_setup._download_dir = os.path.join(work_dir, "downloads")  # not clip_fixer's NAS
        os.makedirs(browser_setup._download_dir)
        if not visible:
            width = config.get_hardware_profile()["screen"]["width"]
            browser_setup._get_macos_top_right_screen_frame = lambda: (
                OFF_SCREEN,
                OFF_SCREEN,
                width,
                0,
            )
        chrome_args = config.get_chrome_args
        # gflow's sign-in sealed the profile's cookies with the basic store and mock keychain
        # (Playwright's flags).
        extra_args = ["--password-store=basic", "--use-mock-keychain"]
        if proxy:
            extra_args.append(f"--proxy-server={proxy}")
        config.get_chrome_args = lambda: [*chrome_args(), *extra_args]

        driver = browser_setup.setup_driver()
        try:
            if not visible:
                driver.set_window_rect(x=OFF_SCREEN_X, y=0)
            recorder = _CdpRecorder()
            browser_setup._apply_additional_stealth_cdp(recorder)
            browser_pid = getattr(driver, "browser_pid", None)
            info = {
                "launcher_pid": os.getpid(),
                "browser_pid": browser_pid,
                "cdp": driver.capabilities["goog:chromeOptions"]["debuggerAddress"],
                "page_cdp": [call for call in recorder.calls if not call[0].startswith("Browser.")],
                "visible": visible,
                "proxy": proxy,
            }
            users_dir.mkdir(parents=True, exist_ok=True)
            _write_state(state, info)
            reason = wait_while_used(users_dir, idle, browser_pid, stopped)
            print(f"Stealth Chrome closing: {reason}")  # noqa: T201 - stdout is its log
        finally:
            _forget_state(state)
            driver.quit()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
