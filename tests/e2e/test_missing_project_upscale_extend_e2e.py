"""#1053: upscale and extend into a --project Flow will not open stop with exit 11.

Needs GFLOW_CLI_E2E_PROFILE on a profile Flow serves at flow.google.com. $0: Flow answers
the project navigation with /404?reason=project, so nothing is exported or submitted.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from gflow_cli.config import reset_settings
from gflow_cli.mcp import tools as mcp_tools

from .test_image_uuid_ref_e2e import _run_gflow

pytestmark = pytest.mark.e2e

_NO_SUCH_PROJECT = "00000000-0000-0000-0000-000000000000"
_ANY_MEDIA = "11111111-1111-1111-1111-111111111111"


@pytest.mark.e2e_auth
@pytest.mark.parametrize(
    "args",
    [
        ["image", "upscale", _ANY_MEDIA, "--scale", "2k"],
        ["video", "upscale", _ANY_MEDIA, "--scale", "1080p"],
        ["video", "extend", _ANY_MEDIA, "keep going", "--yes"],
    ],
    ids=["image-upscale", "video-upscale", "video-extend"],
)
def test_e2e_missing_project_is_exit_11(e2e_env: dict[str, str], args: list[str]) -> None:
    proc = _run_gflow([*args, "--project", _NO_SUCH_PROJECT], e2e_env)

    assert proc.returncode == 11, proc.stderr[-800:]
    assert "reason=project" in proc.stdout + proc.stderr


@pytest.mark.e2e_auth
def test_e2e_mcp_image_upscale_missing_project_is_a_configuration_error(
    e2e_env: dict[str, str], e2e_profile_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del e2e_profile_dir  # selects the real authenticated gflow home
    for key in ("GFLOW_CLI_DB_PATH", "GFLOW_CLI_OUTPUT_DIR"):
        monkeypatch.setenv(key, e2e_env[key])
    reset_settings()

    result = asyncio.run(
        mcp_tools.gflow_upscale_image(
            media_id=_ANY_MEDIA,
            scale="2k",
            project=_NO_SUCH_PROJECT,
            profile=e2e_env["GFLOW_CLI_PROFILE"],
        )
    )

    assert result["status"] in {"failed", "error"}, result
    assert result["error"]["type"].endswith("/configuration"), result
