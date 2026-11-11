"""#984: a profile held by the user's own Chrome is exit 11, not an UnexpectedError.

The message is Playwright's own, captured 2026-10-23 on Windows (Chrome 141) while a
plain `chrome.exe --user-data-dir=<profile>` held the directory. It matches none of
the #293 target-closed markers, so it escaped as `error_unhandled` (exit 1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gflow_cli.api.client import FlowApiClient
from gflow_cli.browser_manager import profile_in_use_error
from gflow_cli.config import Settings
from gflow_cli.errors import ProfileLockedError

_IN_USE = (
    "BrowserType.launch_persistent_context: Opening in existing browser session. "
    "This usually means that the profile is already in use by another instance of "
    "Chromium.\nCall log:\n  - <launching> chrome.exe ..."
)


class Error(Exception):
    """Stands in for ``playwright._impl._errors.Error``: matched by message, not class."""


def test_profile_in_use_message_is_a_profile_lock(tmp_path: Path) -> None:
    err = profile_in_use_error(Error(_IN_USE), tmp_path)

    assert isinstance(err, ProfileLockedError)
    assert str(tmp_path) in err.detail
    assert "Close" in err.remediation_hint


def test_other_launch_errors_are_not_reclassified(tmp_path: Path) -> None:
    assert profile_in_use_error(Error("Executable doesn't exist at chrome.exe"), tmp_path) is None


@pytest.mark.asyncio
async def test_client_launch_raises_profile_locked_for_a_held_profile(tmp_path: Path) -> None:
    client = FlowApiClient(tmp_path / "profile", settings=Settings(home=tmp_path))

    class _Chromium:
        async def launch_persistent_context(self, **_kw: Any) -> None:
            raise Error(_IN_USE)

    class _Pw:
        chromium = _Chromium()

    client._pw = _Pw()  # type: ignore[assignment]  # noqa: SLF001
    with pytest.raises(ProfileLockedError, match="already in use"):
        await client._launch_persistent_context({})  # noqa: SLF001


@pytest.mark.asyncio
async def test_a_read_only_profile_stays_an_access_error(tmp_path: Path) -> None:
    """Chrome uses the same "already in use" header when it cannot write the lock file."""
    from gflow_cli.errors import ProfileAccessError

    client = FlowApiClient(tmp_path / "profile", settings=Settings(home=tmp_path))
    denied = (
        "Failed to create a ProcessSingleton for your profile directory. This usually "
        "means that the profile is already in use by another instance of Chromium.\n"
        "Lock file can not be created: Access is denied. (0x5)"
    )

    class _Chromium:
        async def launch_persistent_context(self, **_kw: Any) -> None:
            raise Error(denied)

    class _Pw:
        chromium = _Chromium()

    client._pw = _Pw()  # type: ignore[assignment]  # noqa: SLF001
    with pytest.raises(ProfileAccessError):
        await client._launch_persistent_context({})  # noqa: SLF001


@pytest.mark.asyncio
async def test_a_target_closed_launch_keeps_the_293_hint(tmp_path: Path) -> None:
    """#293's stale-Chrome shape carries the same header; it keeps its own hint."""

    class TargetClosedError(Exception):  # noqa: N818 - mimics Playwright's class name
        pass

    client = FlowApiClient(tmp_path / "profile", settings=Settings(home=tmp_path))

    class _Chromium:
        async def launch_persistent_context(self, **_kw: Any) -> None:
            raise TargetClosedError(_IN_USE)

    class _Pw:
        chromium = _Chromium()

    client._pw = _Pw()  # type: ignore[assignment]  # noqa: SLF001
    with pytest.raises(ProfileLockedError) as info:
        await client._launch_persistent_context({})  # noqa: SLF001
    assert "crashed at startup for another reason" in info.value.remediation_hint


@pytest.mark.parametrize(
    "lock_line",
    [
        "Lock file can not be created: Access is denied. (0x5)",
        "Lock file can not be created: 拒绝访问。 (0x5)",  # zh-CN, see test_concurrency
        "Lock file can not be created: Acesso negado. (0x5)",  # pt-BR
        "Lock file can not be created: Zugriff verweigert (0x5)",  # de-DE
        "Lock file can not be created! Error code: 5",  # older Chrome wording
    ],
)
def test_a_read_only_lock_line_is_not_a_profile_in_use(tmp_path: Path, lock_line: str) -> None:
    """The helper excludes it itself, for call sites without an access check (#1059);
    Chrome's prefix stays English, only the OS text after it is translated."""
    assert profile_in_use_error(Error(f"{_IN_USE}\n{lock_line}"), tmp_path) is None
