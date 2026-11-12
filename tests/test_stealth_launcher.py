"""stealth_launcher.main with clip_fixer's modules faked: nothing launches Chrome."""

from __future__ import annotations

import io
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from gflow_cli import stealth_launcher


class _FakeDriver:
    def __init__(self) -> None:
        self.capabilities = {"goog:chromeOptions": {"debuggerAddress": "127.0.0.1:9333"}}
        self.browser_pid = 777
        self.quit_called = False

    def quit(self) -> None:
        self.quit_called = True


@pytest.fixture
def clip_fixer(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """Fake ``scraper.config`` and ``scraper.browser_setup``; ``seen`` holds what setup_driver saw."""
    driver = _FakeDriver()
    seen: dict[str, Any] = {}
    config = types.ModuleType("scraper.config")
    config.get_hardware_profile = lambda: {"screen": {"width": 1920}}  # type: ignore[attr-defined]
    config.get_chrome_args = lambda: ["--lang=en-US"]  # type: ignore[attr-defined]
    browser_setup = types.ModuleType("scraper.browser_setup")

    def setup_driver() -> _FakeDriver:
        seen["profile"] = browser_setup._get_profile_path()  # type: ignore[attr-defined]
        seen["args"] = config.get_chrome_args()  # type: ignore[attr-defined]
        seen["frame"] = browser_setup._get_macos_top_right_screen_frame()  # type: ignore[attr-defined]
        seen["download_dir"] = browser_setup._download_dir  # type: ignore[attr-defined]
        seen["cwd"] = os.getcwd()
        if seen.get("fail"):
            raise RuntimeError("chromedriver went missing")
        return driver

    def apply_stealth(target: Any) -> None:
        target.execute_cdp_cmd("Browser.grantPermissions", {"permissions": ["geolocation"]})
        target.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "stealth()"})

    browser_setup.setup_driver = setup_driver  # type: ignore[attr-defined]
    browser_setup._apply_additional_stealth_cdp = apply_stealth  # type: ignore[attr-defined]
    browser_setup._get_macos_top_right_screen_frame = lambda: (0, 0, 2560, 1440)  # type: ignore[attr-defined]
    scraper = types.ModuleType("scraper")
    scraper.config = config  # type: ignore[attr-defined]
    scraper.browser_setup = browser_setup  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scraper", scraper)
    monkeypatch.setitem(sys.modules, "scraper.config", config)
    monkeypatch.setitem(sys.modules, "scraper.browser_setup", browser_setup)
    return types.SimpleNamespace(driver=driver, config=config, seen=seen)


def _run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *argv: str) -> str:
    """main() with ``argv``; what it printed for gflow."""
    monkeypatch.chdir(tmp_path)  # main() moves into its own work dir; this puts the cwd back
    monkeypatch.setattr(sys, "argv", ["stealth_launcher.py", *argv])
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    stealth_launcher.main()
    return out.getvalue()


def test_prints_the_cdp_address_and_the_per_tab_stealth_commands(
    clip_fixer: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    printed = _run(monkeypatch, tmp_path, "/profiles/profile_someone")

    assert printed.startswith(stealth_launcher.MARKER)
    info = json.loads(printed[len(stealth_launcher.MARKER) :])
    assert info == {
        "cdp": "127.0.0.1:9333",
        "browser_pid": 777,
        "page_cdp": [["Page.addScriptToEvaluateOnNewDocument", {"source": "stealth()"}]],
    }
    assert clip_fixer.driver.quit_called


def test_opens_the_gflow_profile_out_of_incognito_and_off_screen(
    clip_fixer: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(monkeypatch, tmp_path, "/profiles/profile_someone")

    seen, config = clip_fixer.seen, clip_fixer.config
    assert (config.SITE_NAME, config.USE_INCOGNITO, config.VISIBLE_BROWSER) == (
        "bot_sannysoft",
        False,
        True,
    )
    assert seen["profile"] == "/profiles/profile_someone"
    assert seen["args"] == ["--lang=en-US", "--password-store=basic", "--use-mock-keychain"]
    assert seen["frame"] == (stealth_launcher.OFF_SCREEN, stealth_launcher.OFF_SCREEN, 1920, 0)


def test_visible_leaves_clip_fixers_on_screen_placement(
    clip_fixer: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(monkeypatch, tmp_path, "/profiles/profile_someone", "--visible")

    assert clip_fixer.seen["frame"] == (0, 0, 2560, 1440)


def test_a_proxy_reaches_chrome_as_its_proxy_server_flag(
    clip_fixer: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(
        monkeypatch, tmp_path, "/profiles/profile_someone", "--proxy-server", "http://127.0.0.1:7897"
    )

    assert clip_fixer.seen["args"][-1] == "--proxy-server=http://127.0.0.1:7897"


def test_works_in_its_own_temp_dir_and_removes_it(
    clip_fixer: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(monkeypatch, tmp_path, "/profiles/profile_someone")

    work_dir = Path(clip_fixer.seen["cwd"])
    assert work_dir.resolve() != tmp_path.resolve()
    assert Path(clip_fixer.seen["download_dir"]).parent.resolve() == work_dir.resolve()
    assert not work_dir.exists()
    assert not (tmp_path / "downloaded_files").exists()


def test_removes_its_temp_dir_when_chrome_fails_to_start(
    clip_fixer: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clip_fixer.seen["fail"] = True

    with pytest.raises(RuntimeError, match="chromedriver"):
        _run(monkeypatch, tmp_path, "/profiles/profile_someone")

    assert not Path(clip_fixer.seen["cwd"]).exists()
