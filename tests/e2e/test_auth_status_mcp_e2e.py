"""Live proof that the MCP auth-status twin verifies a real session (#1023).

`tests/e2e/test_auth_verification_e2e.py` proves `verify_flow_profile`. This proves the
tool an agent calls, `gflow_auth_status`: its profile resolution and the dict that
crosses the tool boundary. Since labs.google's session URL answers 410 (#1023) an
agent saw `verification_error` on a healthy profile, and nothing offline could show it.

Opt-in: ``-m e2e_auth`` with ``GFLOW_CLI_E2E_PROFILE`` set. Read-only; spends nothing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_auth]


async def test_mcp_auth_status_reports_a_live_profile_authenticated(
    e2e_profile_dir: Path,
) -> None:
    from gflow_cli.mcp import tools

    profile = os.environ["GFLOW_CLI_E2E_PROFILE"].strip()
    result: dict[str, Any] = await tools.gflow_auth_status(profile=profile)

    assert result.get("status") == "authenticated", f"MCP auth status failed: {result}"
    assert result["profile"] == profile
    assert result["user_email"], "an authenticated result must name the account"
