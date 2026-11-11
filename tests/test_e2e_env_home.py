"""`e2e_env` hands the child the developer's REAL ``GFLOW_CLI_HOME`` (#745 item 12).

The autouse `_isolate_settings` points ``GFLOW_CLI_HOME`` at an empty tmp dir, and a
child that inherits it finds no profiles. Dropping the variable fixes that only for a
developer on the default home; one with a custom home loses it, and the child reports
"No session for profile" again. So the real value is captured before any fixture runs.

Lives in ``tests/`` because everything under ``tests/e2e/`` is deselected by default.
"""

from __future__ import annotations

import os

import pytest

from tests.e2e import conftest as e2e_conftest


def test_the_real_home_is_captured_before_isolation_overwrites_it() -> None:
    # `_isolate_settings` has already run: the live value is its tmp dir, never the capture.
    assert os.environ.get("GFLOW_CLI_HOME") != e2e_conftest._REAL_GFLOW_CLI_HOME  # noqa: SLF001


def test_a_custom_home_is_restored_in_the_child(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(e2e_conftest, "_REAL_GFLOW_CLI_HOME", "D:/gflow-home")
    env = {"GFLOW_CLI_HOME": "C:/tmp/isolated"}
    e2e_conftest._restore_real_home(env)  # noqa: SLF001
    assert env["GFLOW_CLI_HOME"] == "D:/gflow-home"


def test_no_custom_home_drops_the_isolated_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(e2e_conftest, "_REAL_GFLOW_CLI_HOME", None)
    env = {"GFLOW_CLI_HOME": "C:/tmp/isolated"}
    e2e_conftest._restore_real_home(env)  # noqa: SLF001
    assert "GFLOW_CLI_HOME" not in env
