"""GFLOW_CLI_BROWSER_PROXY routes every browser gflow launches through one proxy (#1036).

Opt-in: unset changes nothing. The value is validated when settings load (proxy
credentials are refused: Flow does not load through Playwright's proxy auth, see
tests/e2e/test_browser_proxy_e2e.py), and every non-experimental launch site carries it.
"""

from __future__ import annotations

import ast
import contextlib
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from gflow_cli.browser_manager import browser_proxy_kwargs
from gflow_cli.config import Settings, get_settings, reset_settings
from gflow_cli.data.redaction import redact_error_detail
from gflow_cli.errors import ConfigurationError

SRC = Path(__file__).resolve().parents[1] / "src" / "gflow_cli"
PROXY = "http://127.0.0.1:7897"
EXPECTED = {"server": PROXY}


# --- the pure helper -------------------------------------------------------


def test_unset_adds_nothing() -> None:
    assert browser_proxy_kwargs(None) == {}


def test_plain_proxy_is_the_server() -> None:
    assert browser_proxy_kwargs("socks5://127.0.0.1:1080") == {
        "proxy": {"server": "socks5://127.0.0.1:1080"}
    }


# --- validation at settings load -------------------------------------------


@pytest.mark.parametrize(
    "good",
    ["http://127.0.0.1:7897", "https://proxy.example:443", "socks5://127.0.0.1:1080"],
)
def test_valid_values_load(good: str) -> None:
    assert Settings(browser_proxy=good).browser_proxy is not None


def test_empty_means_unset() -> None:
    assert Settings(browser_proxy="").browser_proxy is None


@pytest.mark.parametrize(
    "bad",
    [
        "127.0.0.1:7897",  # no scheme
        "ftp://127.0.0.1:21",
        "http://",
        "http://h:notaport",
        "http://h:1/path",
        "http://h:1?x=1",
        "http://:pw@h:1",
        "http://127.0.0.1",  # no port: required, so the message's scheme://host:port is true
        "http://user:s3cretPW@127.0.0.1:7897",  # credentials: Flow never loads through them
        "socks5://user:s3cretPW@127.0.0.1:1080",
    ],
)
def test_malformed_values_are_refused_without_echoing_them(bad: str) -> None:
    with pytest.raises(ValidationError) as info:
        Settings(browser_proxy=bad)
    assert "browser_proxy" in str(info.value)
    assert "invalid proxy" in str(info.value)
    assert "s3cretPW" not in str(info.value)


def test_cli_names_the_setting_once_without_pydantic_noise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from click.testing import CliRunner

    from gflow_cli.cli import main

    monkeypatch.setenv("GFLOW_CLI_BROWSER_PROXY", "socks5://user:s3cretPW@127.0.0.1:1080")
    reset_settings()
    result = CliRunner().invoke(main, ["doctor"])
    assert result.exit_code == 11
    assert "GFLOW_CLI_BROWSER_PROXY — invalid proxy:" in result.output
    assert "Value error" not in result.output
    assert "s3cretPW" not in result.output


def test_credentials_message_says_why_and_what_to_use() -> None:
    with pytest.raises(ValidationError) as info:
        Settings(browser_proxy="http://user:s3cretPW@127.0.0.1:7897")
    assert "not supported" in str(info.value)
    assert "127.0.0.1:7897" in str(info.value)  # the suggested local client, not the value


# --- every launch site carries it -----------------------------------------

_STOP = RuntimeError("stop after launch")


def _recording_playwright(seen: list[dict[str, Any]]) -> MagicMock:
    async def _launch(*args: object, **kwargs: Any) -> None:
        seen.append(kwargs)
        raise _STOP

    pw = MagicMock(name="pw")
    pw.chromium.launch_persistent_context = AsyncMock(side_effect=_launch)
    cm = MagicMock(name="cm")
    cm.__aenter__ = AsyncMock(return_value=pw)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(name="async_playwright", return_value=cm)


async def _client(profile: Path, mp: pytest.MonkeyPatch) -> dict[str, Any]:
    from gflow_cli.api.client import FlowApiClient

    return FlowApiClient(profile_dir=profile, settings=get_settings())._persistent_context_kwargs()  # noqa: SLF001


async def _ui_automation(profile: Path, mp: pytest.MonkeyPatch) -> None:
    from gflow_cli.api.transports.ui_automation import UiAutomationTransport

    await UiAutomationTransport().setup(profile)


async def _internal_login(profile: Path, mp: pytest.MonkeyPatch) -> None:
    from gflow_cli.auth.internal_chromium import InternalChromiumStrategy

    await InternalChromiumStrategy().login(profile, headless=False)


async def _chrome_owned_login(profile: Path, mp: pytest.MonkeyPatch) -> None:
    from gflow_cli.auth.real_chrome import RealChromeStrategy

    await RealChromeStrategy()._login_owned_browser(profile, headless=False)  # noqa: SLF001


async def _renew(profile: Path, mp: pytest.MonkeyPatch) -> None:
    from gflow_cli.auth.renew import renew_profile

    await renew_profile(profile)


async def _verify_session(profile: Path, mp: pytest.MonkeyPatch) -> None:
    from gflow_cli.auth.verification import verify_flow_session

    await verify_flow_session(profile, channel=None, source="test")


async def _verify_migrated(profile: Path, mp: pytest.MonkeyPatch) -> None:
    from gflow_cli.auth.verification import _verify_migrated_host_fallback  # noqa: PLC2701

    await _verify_migrated_host_fallback(profile, source="test")


async def _cookie_read(profile: Path, mp: pytest.MonkeyPatch) -> None:
    from gflow_cli.auth import cookies

    mp.setattr(cookies, "channel_for_profile", lambda _p: "chrome")
    await cookies._get_chrome_cookies_playwright(profile)  # noqa: SLF001


SITES = {
    "api/client.py": _client,
    "api/transports/ui_automation.py": _ui_automation,
    "auth/internal_chromium.py": _internal_login,
    "auth/real_chrome.py": _chrome_owned_login,
    "auth/renew.py": _renew,
    "auth/verification.py#session": _verify_session,
    "auth/verification.py#migrated": _verify_migrated,
    "auth/cookies.py": _cookie_read,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("proxy_set", [True, False], ids=["set", "unset"])
@pytest.mark.parametrize("site", list(SITES))
async def test_every_launch_site_carries_the_proxy(
    site: str, proxy_set: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    if proxy_set:
        monkeypatch.setenv("GFLOW_CLI_BROWSER_PROXY", PROXY)
    reset_settings()
    seen: list[dict[str, Any]] = []
    fake = _recording_playwright(seen)
    monkeypatch.setattr("gflow_cli.auth.strategies.async_playwright", fake)
    monkeypatch.setattr("gflow_cli.api.transports.ui_automation.async_playwright", fake)
    monkeypatch.setattr("gflow_cli.browser_manager.channel_for_profile", lambda _p: None)
    monkeypatch.setattr(
        "gflow_cli.browser_manager.ensure_profile_engine_compatible", lambda _p, _c: None
    )
    profile = get_settings().home / "profile_proxy"
    profile.mkdir(parents=True)

    with contextlib.suppress(Exception):
        direct = await SITES[site](profile, monkeypatch)
        if direct is not None:
            seen.append(direct)

    assert len(seen) == 1, f"{site} never reached its launch"
    if proxy_set:
        assert seen[0]["proxy"] == EXPECTED
    else:
        assert "proxy" not in seen[0]
    # Never the flag form: one kwarg, carried the same way by every site.
    assert not any("proxy" in str(a) for a in seen[0].get("args", []))


def test_the_site_table_covers_every_launch_in_src() -> None:
    """A new launch_persistent_context call must be added to SITES (drift guard, cf. #222)."""
    counts: dict[str, int] = {}
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("api/transports/experimental/"):
            continue  # opt-in experimental transports are out of scope for #1036
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr == "launch_persistent_context":
                if isinstance(getattr(node, "ctx", None), ast.Load):
                    counts[rel] = counts.get(rel, 0) + 1
    expected: dict[str, int] = {}
    for site in SITES:
        rel = site.split("#")[0]
        expected[rel] = expected.get(rel, 0) + 1
    # client.py builds its kwargs in _persistent_context_kwargs; the call itself is elsewhere.
    assert counts == expected


# --- raw real-Chrome login (a subprocess, not Playwright) -------------------


def test_raw_chrome_gets_the_server_flag_only() -> None:
    from gflow_cli.auth.real_chrome import _build_chrome_args  # noqa: PLC2701

    args = _build_chrome_args("chrome", Path("p"), False, PROXY)
    assert "--proxy-server=http://127.0.0.1:7897" in args
    assert args[-1].startswith("http")  # the start URL stays last


def test_raw_chrome_without_proxy_is_unchanged() -> None:
    from gflow_cli.auth.real_chrome import _build_chrome_args  # noqa: PLC2701

    assert not any("proxy" in a for a in _build_chrome_args("chrome", Path("p"), False, None))


# --- redaction --------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "launch failed: --proxy-server=http://user:s3cretPW@127.0.0.1:7897",
        "socks5://user:s3cretPW@proxy.example.com:1080 refused",
        "HTTPS://user:s3cretPW@[::1]:3128",
        "http://user:s3cretPW@ss@127.0.0.1:7897",  # unencoded "@" inside the password
    ],
)
def test_url_userinfo_is_redacted(text: str) -> None:
    out = redact_error_detail(text)
    assert "s3cretPW" not in out
    assert "user:" not in out
    assert "<redacted:secret>@" in out
    assert out.count("@") == 1  # nothing of the password survives past the redaction


# --- launch log -------------------------------------------------------------


def test_launch_log_names_the_proxy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from structlog.testing import capture_logs

    from gflow_cli.api.client import FlowApiClient

    monkeypatch.setattr(
        "gflow_cli.browser_manager.ensure_profile_engine_compatible", lambda *_: None
    )
    monkeypatch.setattr("gflow_cli.browser_manager.chrome_strategy_requested", lambda _p: False)
    client = FlowApiClient(profile_dir=tmp_path, settings=Settings(browser_proxy=PROXY))
    with capture_logs() as logs:
        client._log_and_guard_launch(client._persistent_context_kwargs())  # noqa: SLF001
    event = next(e for e in logs if e["event"] == "client.persistent_context_launch")
    assert event["proxy"] == PROXY


# --- dead proxy -------------------------------------------------------------


@pytest.mark.parametrize(
    "net_error", ["net::ERR_PROXY_CONNECTION_FAILED", "net::ERR_TUNNEL_CONNECTION_FAILED"]
)
@pytest.mark.asyncio
async def test_unreachable_proxy_names_the_setting(tmp_path: Path, net_error: str) -> None:
    from playwright.async_api import Error as PlaywrightError

    from gflow_cli.api.client import FlowApiClient

    client = FlowApiClient(profile_dir=tmp_path, settings=Settings(browser_proxy=PROXY))
    page = MagicMock()
    page.goto = AsyncMock(side_effect=PlaywrightError(f"Page.goto: {net_error} at https://x"))
    client._page = page  # noqa: SLF001
    with pytest.raises(ConfigurationError) as info:
        await client._bootstrap_and_resolve_locale()  # noqa: SLF001
    assert "GFLOW_CLI_BROWSER_PROXY" in (info.value.remediation_hint or "")


@pytest.mark.asyncio
async def test_other_navigation_errors_pass_through(tmp_path: Path) -> None:
    from playwright.async_api import Error as PlaywrightError

    from gflow_cli.api.client import FlowApiClient

    client = FlowApiClient(profile_dir=tmp_path, settings=Settings(browser_proxy=PROXY))
    page = MagicMock()
    page.goto = AsyncMock(side_effect=PlaywrightError("Page.goto: net::ERR_ABORTED"))
    client._page = page  # noqa: SLF001
    with pytest.raises(PlaywrightError):
        await client._bootstrap_and_resolve_locale()  # noqa: SLF001
