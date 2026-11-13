"""stealth_launcher with clip_fixer's modules faked: nothing launches Chrome."""

from __future__ import annotations

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
        self.window_rect: dict[str, int] | None = None

    def set_window_rect(self, **rect: int) -> None:
        self.window_rect = rect

    def quit(self) -> None:
        self.quit_called = True


@pytest.fixture
def clip_fixer(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """Fake ``scraper.config`` and ``scraper.browser_setup``; ``seen`` holds what setup_driver
    saw and the state file and wait the launcher went into."""
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

    def wait_while_used(users_dir: Path, idle: float, browser_pid: Any, stopped: list) -> str:
        state = Path(str(users_dir).removesuffix(".users"))
        seen["state"] = json.loads(state.read_text())
        seen["wait"] = (users_dir, idle, browser_pid)
        return "idle"

    browser_setup.setup_driver = setup_driver  # type: ignore[attr-defined]
    browser_setup._apply_additional_stealth_cdp = apply_stealth  # type: ignore[attr-defined]
    browser_setup._get_macos_top_right_screen_frame = lambda: (0, 0, 2560, 1440)  # type: ignore[attr-defined]
    scraper = types.ModuleType("scraper")
    scraper.config = config  # type: ignore[attr-defined]
    scraper.browser_setup = browser_setup  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scraper", scraper)
    monkeypatch.setitem(sys.modules, "scraper.config", config)
    monkeypatch.setitem(sys.modules, "scraper.browser_setup", browser_setup)
    monkeypatch.setattr(stealth_launcher, "wait_while_used", wait_while_used)
    monkeypatch.setattr(stealth_launcher.signal, "signal", lambda *_args: None)
    return types.SimpleNamespace(driver=driver, config=config, seen=seen)


def _run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *options: str) -> Path:
    """main() for /profiles/profile_someone with `options`; the state file it was given."""
    state = tmp_path / "stealth_profile_someone.json"
    monkeypatch.chdir(tmp_path)  # main() moves into its own work dir; this puts the cwd back
    argv = ["stealth_launcher.py", "/profiles/profile_someone", "--state", str(state), *options]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    stealth_launcher.main()
    return state


def test_writes_its_state_waits_and_quits_chrome(
    clip_fixer: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = _run(monkeypatch, tmp_path, "--idle", "600")

    assert clip_fixer.seen["state"] == {
        "launcher_pid": os.getpid(),
        "browser_pid": 777,
        "cdp": "127.0.0.1:9333",
        "page_cdp": [["Page.addScriptToEvaluateOnNewDocument", {"source": "stealth()"}]],
        "visible": False,
        "proxy": None,
    }
    assert clip_fixer.seen["wait"] == (Path(f"{state}.users"), 600.0, 777)
    assert not state.exists()
    assert clip_fixer.driver.quit_called


def test_opens_the_gflow_profile_out_of_incognito_and_off_screen(
    clip_fixer: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(monkeypatch, tmp_path)

    seen, config = clip_fixer.seen, clip_fixer.config
    assert (config.SITE_NAME, config.USE_INCOGNITO, config.VISIBLE_BROWSER) == (
        "bot_sannysoft",
        False,
        True,
    )
    assert seen["profile"] == "/profiles/profile_someone"
    assert seen["args"] == ["--lang=en-US", "--password-store=basic", "--use-mock-keychain"]
    assert seen["frame"] == (stealth_launcher.OFF_SCREEN, stealth_launcher.OFF_SCREEN, 1920, 0)
    # Chrome puts a wholly off-screen launch back on a screen, so the window is moved off once up.
    assert clip_fixer.driver.window_rect == {"x": stealth_launcher.OFF_SCREEN_X, "y": 0}


def test_visible_leaves_clip_fixers_on_screen_placement(
    clip_fixer: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(monkeypatch, tmp_path, "--visible")

    assert clip_fixer.seen["frame"] == (0, 0, 2560, 1440)
    assert clip_fixer.seen["state"]["visible"] is True
    assert clip_fixer.driver.window_rect is None


def test_a_proxy_reaches_chrome_as_its_proxy_server_flag(
    clip_fixer: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(monkeypatch, tmp_path, "--proxy-server", "http://127.0.0.1:7897")

    assert clip_fixer.seen["args"][-1] == "--proxy-server=http://127.0.0.1:7897"
    assert clip_fixer.seen["state"]["proxy"] == "http://127.0.0.1:7897"


def test_works_in_its_own_temp_dir_and_removes_it(
    clip_fixer: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run(monkeypatch, tmp_path)

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
        _run(monkeypatch, tmp_path)

    assert not Path(clip_fixer.seen["cwd"]).exists()


# --- how long Chrome stays open ---------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _wait(users_dir: Path, idle: float, clock: _Clock, **kwargs: Any) -> str:
    return stealth_launcher.wait_while_used(
        users_dir,
        idle,
        kwargs.get("browser_pid"),
        kwargs.get("stopped", []),
        sleep=kwargs.get("sleep", clock.sleep),
        now=clock.now,
    )


def test_unused_it_closes_after_the_idle_time(tmp_path: Path) -> None:
    clock = _Clock()

    assert _wait(tmp_path, 600, clock) == "idle"
    assert clock.t >= 600


def test_a_live_user_keeps_it_open_until_it_leaves(tmp_path: Path) -> None:
    clock, user = _Clock(), tmp_path / str(os.getpid())
    user.touch()

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        if clock.t >= 1000:
            user.unlink(missing_ok=True)

    assert _wait(tmp_path, 600, clock, sleep=sleep) == "idle"
    assert (
        clock.t >= 1000 - stealth_launcher.CHECK_EVERY_S + 600
    )  # idle counts from its last sighting


def test_a_dead_users_file_is_cleared_and_does_not_hold_it_open(tmp_path: Path) -> None:
    clock, dead = _Clock(), tmp_path / "999999999"
    dead.touch()

    assert _wait(tmp_path, 0, clock) == "idle"
    assert not dead.exists()


def test_it_stops_when_chrome_exits(tmp_path: Path) -> None:
    (tmp_path / str(os.getpid())).touch()

    assert _wait(tmp_path, 600, _Clock(), browser_pid=999999999) == "chrome"


def test_it_stops_on_sigterm(tmp_path: Path) -> None:
    assert _wait(tmp_path, 600, _Clock(), stopped=[True]) == "stopped"
