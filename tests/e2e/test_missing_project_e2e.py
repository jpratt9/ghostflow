"""#974: a --project id Flow will not open fails fast with exit 11, not drift (exit 23).

Needs GFLOW_CLI_E2E_PROFILE on a profile Flow serves at flow.google.com. $0: Flow answers
the navigation with /404?reason=project, so nothing reaches a submit.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from gflow_cli.config import reset_settings
from gflow_cli.mcp import tools as mcp_tools

from .test_image_uuid_ref_e2e import _run_gflow

pytestmark = pytest.mark.e2e

_NO_SUCH_PROJECT = "00000000-0000-0000-0000-000000000000"


@pytest.mark.e2e_auth
def test_e2e_cli_t2i_into_a_missing_project_exits_11_fast(e2e_env: dict[str, str]) -> None:
    started = time.monotonic()
    proc = _run_gflow(["image", "t2i", "a paper boat", "--project", _NO_SUCH_PROJECT], e2e_env)
    elapsed = time.monotonic() - started

    assert proc.returncode == 11, proc.stderr[-800:]
    assert "reason=project" in proc.stdout + proc.stderr
    # Measured before the fix: exit 23 after ~40 s (the 30 s drift wait plus startup).
    assert elapsed < 20, elapsed  # a fall-back to the 30 s wait would exceed this


@pytest.mark.e2e_auth
def test_e2e_mcp_image_into_a_missing_project_is_a_configuration_error(
    e2e_env: dict[str, str], e2e_profile_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del e2e_profile_dir  # selects the real authenticated gflow home
    for key in ("GFLOW_CLI_DB_PATH", "GFLOW_CLI_OUTPUT_DIR"):
        monkeypatch.setenv(key, e2e_env[key])
    reset_settings()

    result = asyncio.run(
        mcp_tools.gflow_generate_image(
            prompt="a paper boat",
            profile=e2e_env["GFLOW_CLI_PROFILE"],
            project=_NO_SUCH_PROJECT,
            wait=True,
        )
    )

    assert result["status"] in {"failed", "error"}, result
    error = result["error"]
    assert error["type"].endswith("/configuration"), error
    assert error["retryable"] is False, error
    assert "reason=project" in error["detail"] and _NO_SUCH_PROJECT in error["detail"], error
