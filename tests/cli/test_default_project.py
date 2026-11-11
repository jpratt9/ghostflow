"""#1039: GFLOW_CLI_PROJECT pins the project a generation runs in when none is named."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import click
import pytest

from gflow_cli._cli_helpers import default_project
from gflow_cli.config import get_settings, reset_settings
from gflow_cli.data.models import ProjectRecord
from gflow_cli.data.repository import DataRepository
from gflow_cli.data.store import DataStore


@pytest.fixture
def pin(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("GFLOW_CLI_PROJECT", "proj-pinned")
    reset_settings()
    return "proj-pinned"


def _catalog(profile: str, project: str) -> None:
    with DataStore.open(get_settings().resolved_db_path()) as store:
        repo = DataRepository(store)
        repo.upsert_profile(profile, Path(f"profile_{profile}"))
        repo.upsert_project(
            ProjectRecord(
                id=f"{profile}-{project}",
                profile_name=profile,
                flow_project_id=project,
                title=None,
                source="t",
            )
        )


def test_unset_pin_changes_nothing() -> None:
    assert default_project(None, None, "acct") is None


def test_pin_used_when_no_project_given(pin: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert default_project(None, None, "acct") == pin
    # stderr, so --json stdout stays one JSON document
    assert "GFLOW_CLI_PROJECT" in capsys.readouterr().err


def test_explicit_project_beats_pin(pin: str) -> None:
    assert default_project("proj-cli", None, "acct") == "proj-cli"


def test_project_name_asks_for_a_new_project(pin: str) -> None:
    assert default_project(None, "fresh", "acct") is None


def test_pin_from_another_profile_is_refused(pin: str) -> None:
    _catalog("other-acct", pin)
    with pytest.raises(click.UsageError, match="other-acct"):
        default_project(None, None, "acct")


def test_pin_catalogued_for_this_profile_is_used(pin: str) -> None:
    _catalog("other-acct", pin)
    _catalog("acct", pin)
    assert default_project(None, None, "acct") == pin


def test_invalid_pin_fails_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GFLOW_CLI_PROJECT", "bad id")
    reset_settings()
    with pytest.raises(ValueError, match="GFLOW_CLI_PROJECT"):
        get_settings()


# --- wiring: every door that would otherwise create a project reads the pin ------


def test_t2i_generates_in_the_pinned_project(pin: str, tmp_path: Path) -> None:
    from click.testing import CliRunner

    from gflow_cli.cli import main
    from tests.cli.test_cli_image import _make_t2i_client

    client = _make_t2i_client()
    with (
        patch("gflow_cli.cli_image.FlowApiClient", return_value=client),
        patch("gflow_cli.cli_image._make_provider_dir", return_value=tmp_path / "prof"),
        patch("gflow_cli.cli_image._resolve_profile", return_value="default"),
    ):
        result = CliRunner().invoke(
            main, ["image", "t2i", "a cat", "--out", str(tmp_path / "o")], catch_exceptions=False
        )

    assert result.exit_code == 0, result.output
    client.create_project.assert_not_called()
    assert client.generate_image.await_args.kwargs["project_id"] == pin


@pytest.mark.parametrize("cmd", ["t2v", "i2v", "r2v"])
def test_video_generates_in_the_pinned_project(pin: str, tmp_path: Path, cmd: str) -> None:
    from click.testing import CliRunner

    from gflow_cli.cli_video import video

    captured: dict[str, Any] = {}

    async def _capture(request: object, **kwargs: object) -> None:
        captured.update(kwargs)

    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    args = {"t2v": ["t2v", "a sunset"], "i2v": ["i2v", str(img), "push in"]}.get(
        cmd, ["r2v", "a knight", "--ref", str(img)]
    )
    with (
        patch("gflow_cli.cli_video._resolve_profile", return_value="default"),
        patch("gflow_cli.cli_video._make_provider_dir", return_value=tmp_path),
        patch("gflow_cli.cli_video._generate_and_report", new=_capture),
    ):
        result = CliRunner().invoke(video, args)

    assert result.exit_code == 0, result.output
    assert captured["project_id"] == pin


def test_run_config_project_beats_pin_and_pin_beats_creation(pin: str, tmp_path: Path) -> None:
    from tests.cli.test_cli_run import TestGflowRunProject

    result, client = TestGflowRunProject()._invoke(tmp_path, {"prompts": [{"text": "p1"}]})
    assert result.exit_code == 0, result.output
    assert client.create_project.call_count == 0
    assert client.generate_image.call_args.kwargs["project_id"] == pin

    result, client = TestGflowRunProject()._invoke(
        tmp_path, {"project": "proj-config", "prompts": [{"text": "p1"}]}
    )
    assert client.generate_image.call_args.kwargs["project_id"] == "proj-config"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["gflow_generate_image", "gflow_generate_video"])
async def test_mcp_queues_the_pinned_project(pin: str, tool: str) -> None:
    from gflow_cli.mcp import tools as tools_mod

    captured: dict[str, Any] = {}

    async def _fake_run(*, profile: str, task_type: str, payload: dict[str, Any], **kw: Any):
        captured["payload"] = payload
        return {"status": "completed", "files": [], "flow_media_id": "m"}

    with (
        patch("gflow_cli.mcp.tools._rate_limiter", tools_mod._TokenBucket(8, 0.0)),
        patch("gflow_cli.mcp.tools._resolve_and_validate_profile", return_value="default"),
        patch.object(tools_mod, "_run_generation_task", _fake_run),
    ):
        await getattr(tools_mod, tool)(prompt="a cat")
        assert captured["payload"]["project_id"] == pin
        await getattr(tools_mod, tool)(prompt="a cat", project_name="fresh")
        assert "project_id" not in captured["payload"]


@pytest.mark.asyncio
async def test_mcp_refuses_a_pin_from_another_profile(pin: str) -> None:
    from gflow_cli.mcp import tools as tools_mod

    async def _never(**kw: Any) -> dict[str, Any]:
        raise AssertionError("a refused pin must not reach the worker")

    _catalog("other-acct", pin)
    with (
        patch("gflow_cli.mcp.tools._rate_limiter", tools_mod._TokenBucket(8, 0.0)),
        patch("gflow_cli.mcp.tools._resolve_and_validate_profile", return_value="default"),
        patch.object(tools_mod, "_run_generation_task", _never),
    ):
        result = await tools_mod.gflow_generate_image(prompt="a cat")
    assert result["status"] == "error"
    assert "other-acct" in str(result["error"])


def test_i2i_generates_in_the_pinned_project(pin: str, tmp_path: Path) -> None:
    from click.testing import CliRunner

    from gflow_cli.cli import main
    from tests.cli.test_cli_image import _make_i2i_client

    client = _make_i2i_client()
    uuid = "11111111-1111-1111-1111-111111111111"
    with (
        patch("gflow_cli.cli_image.FlowApiClient", return_value=client),
        patch("gflow_cli.cli_image._make_provider_dir", return_value=tmp_path / "prof"),
        patch("gflow_cli.cli_image._resolve_profile", return_value="default"),
    ):
        result = CliRunner().invoke(
            main,
            ["image", "i2i", "stylize", "--ref", uuid, "--out", str(tmp_path / "o")],
            catch_exceptions=False,
        )

    assert result.exit_code == 0, result.output
    client.create_project.assert_not_called()
    assert client.generate_image.await_args.kwargs["project_id"] == pin


def test_multiprompt_t2i_runs_the_batch_in_the_pinned_project(pin: str, tmp_path: Path) -> None:
    from click.testing import CliRunner

    from gflow_cli.cli import main

    async def _fake_run_batch(**_kwargs: object) -> list[object]:
        return []

    with (
        patch("gflow_cli.cli_image._resolve_profile", return_value="default"),
        patch("gflow_cli.cli_image._make_provider_dir", return_value=tmp_path / "p"),
        patch("gflow_cli.cli_image.run_image_batch", side_effect=_fake_run_batch) as run,
        patch("gflow_cli.cli_image.render_image_batch_summary", return_value=0),
    ):
        result = CliRunner().invoke(
            main, ["image", "t2i", "a", "b", "--out", str(tmp_path / "o")], catch_exceptions=False
        )
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["project_id"] == pin


def test_project_name_from_its_env_var_keeps_the_pin(
    pin: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GFLOW_CLI_PROJECT_NAME names the pinned project; only a typed --project-name asks
    for a new one."""
    from click.testing import CliRunner

    from gflow_cli.cli_video import video

    captured: dict[str, Any] = {}

    async def _capture(request: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setenv("GFLOW_CLI_PROJECT_NAME", "My Project")
    with (
        patch("gflow_cli.cli_video._resolve_profile", return_value="default"),
        patch("gflow_cli.cli_video._make_provider_dir", return_value=tmp_path),
        patch("gflow_cli.cli_video._generate_and_report", new=_capture),
    ):
        CliRunner().invoke(video, ["t2v", "a sunset"])
        assert captured["project_id"] == pin
        CliRunner().invoke(video, ["t2v", "a sunset", "--project-name", "fresh"])
        assert captured["project_id"] is None


def test_unreadable_catalog_uses_the_pin(pin: str) -> None:
    from gflow_cli.errors import DataStoreError

    with patch("gflow_cli.data.store.DataStore.open", side_effect=DataStoreError("locked")):
        assert default_project(None, None, "acct") == pin


def test_video_extend_never_reads_the_pin(pin: str) -> None:
    from click.testing import CliRunner

    from gflow_cli.cli import main

    def _never(*_a: Any, **_k: Any) -> None:
        raise AssertionError("extend must not consult GFLOW_CLI_PROJECT")

    media = "22222222-2222-2222-2222-222222222222"
    with patch("gflow_cli.cli_video.default_project", _never):
        result = CliRunner().invoke(main, ["video", "extend", media, "go", "--dry-run"])
    assert pin not in result.output
