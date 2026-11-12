"""Open clip_fixer's stealth Chrome on a gflow profile and hand its CDP address to gflow.

gflow's own environment doesn't carry clip_fixer's requirements, so gflow runs this file under the Python
that does (GFLOW_CLI_STEALTH_PYTHON, python3 by default), with clip_fixer at GFLOW_CLI_CLIP_FIXER
(~/dev/clip_fixer by default):

    python3 stealth_launcher.py <profile_dir> [--visible] [--proxy-server <url>]

It prints one line, ``GFLOW_STEALTH {"cdp": "127.0.0.1:<port>", "browser_pid": <pid>, "page_cdp": [...]}``.
page_cdp holds the CDP commands clip_fixer's stealth setup sends to its first tab (the stealth JS, the
visibility and screenX/Y patches), for gflow to send to every tab it opens. Chrome quits when stdin closes.
This file must not import gflow_cli: it runs outside gflow's environment.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

MARKER = "GFLOW_STEALTH "
OFF_SCREEN = -30000  # the window's x and y unless --visible: headed, as Google turns headless away, but out of sight


class _CdpRecorder:
    """Takes the driver's place to capture the commands clip_fixer's stealth setup sends to a tab."""

    def __init__(self) -> None:
        self.calls: list[list] = []

    def execute_cdp_cmd(self, method: str, params: dict) -> dict:
        self.calls.append([method, params])
        return {}


def main() -> None:
    profile_dir, options = sys.argv[1], sys.argv[2:]
    visible = "--visible" in options
    proxy = options[options.index("--proxy-server") + 1] if "--proxy-server" in options else None
    out, sys.stdout = sys.stdout, sys.stderr  # clip_fixer's prints go to the log; stdout carries the one line
    work_dir = tempfile.mkdtemp(prefix="gflow_stealth_")
    try:
        os.chdir(work_dir)  # SeleniumBase writes its downloaded_files/ lock files into the working directory
        sys.path.insert(0, os.environ.get("GFLOW_CLI_CLIP_FIXER", str(Path.home() / "dev" / "clip_fixer")))
        from scraper import browser_setup, config

        config.SITE_NAME = "bot_sannysoft"  # a site with no VPN or proxy entry, as dialstream's stealth browser picks
        config.USE_INCOGNITO = False  # the profile keeps its Google sign-in
        config.VISIBLE_BROWSER = True  # never minimized: a minimized window takes no clicks
        browser_setup._get_profile_path = lambda: profile_dir
        browser_setup._download_dir = os.path.join(work_dir, "downloads")  # not clip_fixer's NAS
        os.makedirs(browser_setup._download_dir)
        if not visible:
            width = config.get_hardware_profile()["screen"]["width"]
            browser_setup._get_macos_top_right_screen_frame = lambda: (OFF_SCREEN, OFF_SCREEN, width, 0)
        chrome_args = config.get_chrome_args
        # gflow's sign-in sealed the profile's cookies with the basic store and mock keychain (Playwright's flags)
        extra_args = ["--password-store=basic", "--use-mock-keychain"]
        if proxy:
            extra_args.append(f"--proxy-server={proxy}")
        config.get_chrome_args = lambda: [*chrome_args(), *extra_args]

        driver = browser_setup.setup_driver()
        try:
            recorder = _CdpRecorder()
            browser_setup._apply_additional_stealth_cdp(recorder)
            info = {
                "cdp": driver.capabilities["goog:chromeOptions"]["debuggerAddress"],
                "browser_pid": getattr(driver, "browser_pid", None),
                "page_cdp": [call for call in recorder.calls if not call[0].startswith("Browser.")],
            }
            print(MARKER + json.dumps(info), file=out, flush=True)
            sys.stdin.read()  # gflow closes stdin once it's done with the browser
        finally:
            driver.quit()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
