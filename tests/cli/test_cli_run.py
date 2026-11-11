"""Tests for `gflow run` — JSON-described batch image generation.

Covers the spec from AUDIT_E1 Section D:
- 8 unit tests (schema validation, output_dir resolution, error-handling
  semantics, experimental-transport gating, CLI override beats config).
- 1 integration test (session reuse: one setup/teardown across N prompts).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from gflow_cli.api.dto import GeneratedImage
from gflow_cli.cli import main as cli_main
from gflow_cli.cli_run import (
    BatchConfig,
    _check_transport_gated,
)
from gflow_cli.errors import ConfigurationError, WafRejectionError
from gflow_cli.paths import resolve_batch_output_dir

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, payload: dict[str, Any]) -> Path:
    """Write `payload` to <tmp>/flow.json and return the path."""
    p = tmp_path / "flow.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _minimal_config(**overrides: Any) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "prompts": [{"text": "a calm forest at dawn"}],
    }
    cfg.update(overrides)
    return cfg


def _fake_generated_image(seed: int = 42) -> GeneratedImage:
    return GeneratedImage(
        media_name=f"projects/p/assets/asset-{seed}",
        workflow_id=f"wf-{seed}",
        seed=seed,
        prompt="any",
        model_name_type="NARWHAL",
        aspect_ratio="IMAGE_ASPECT_RATIO_PORTRAIT",
        fife_url=f"https://lh3.googleusercontent.com/{seed}",
        dimensions=(576, 1024),
    )


# ---------------------------------------------------------------------------
# Unit 1 — BatchConfig.from_json_path: valid minimal config
# ---------------------------------------------------------------------------


class TestBatchConfigFromJson:
    def test_minimal_config_parses(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, _minimal_config())
        cfg = BatchConfig.from_json_path(path)
        assert len(cfg.prompts) == 1
        assert cfg.prompts[0].text == "a calm forest at dawn"
        # Defaults applied.
        assert cfg.prompts[0].aspect_ratio == "9:16"
        assert cfg.prompts[0].model == "nano2"
        assert cfg.prompts[0].count == 1
        assert cfg.profile is None
        assert cfg.transport is None
        assert cfg.output_dir is None

    def test_full_config_parses(self, tmp_path: Path) -> None:
        path = _write_config(
            tmp_path,
            {
                "profile": "example-profile",
                "transport": "ui_automation",
                "output_dir": "custom/out",
                "prompts": [
                    {
                        "text": "first",
                        "aspect_ratio": "16:9",
                        "model": "nano-pro",
                        "count": 2,
                        "output_filename": "first_scene",
                    },
                    {"text": "second"},
                ],
            },
        )
        cfg = BatchConfig.from_json_path(path)
        assert cfg.profile == "example-profile"
        assert cfg.transport == "ui_automation"
        assert cfg.output_dir == "custom/out"
        assert len(cfg.prompts) == 2
        assert cfg.prompts[0].count == 2
        assert cfg.prompts[0].output_filename == "first_scene"


class TestBatchConfigProject:
    def test_project_key_parses(self, tmp_path: Path) -> None:
        cfg = BatchConfig.from_json_path(
            _write_config(tmp_path, _minimal_config(project="abc-123")),
        )
        assert cfg.project == "abc-123"

    def test_project_defaults_to_none(self, tmp_path: Path) -> None:
        cfg = BatchConfig.from_json_path(_write_config(tmp_path, _minimal_config()))
        assert cfg.project is None

    @pytest.mark.parametrize("bad", ["", "has space", "a/b", 7])
    def test_invalid_project_raises(self, tmp_path: Path, bad: Any) -> None:
        with pytest.raises(ConfigurationError, match="project"):
            BatchConfig.from_json_path(_write_config(tmp_path, _minimal_config(project=bad)))


class TestBatchConfigValidation:
    """Schema validation — each rule from AUDIT_E1 D.1."""

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError, match="not found"):
            BatchConfig.from_json_path(tmp_path / "nope.json")

    def test_malformed_json_raises_with_position(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="Failed to parse"):
            BatchConfig.from_json_path(bad)

    def test_unknown_top_level_key_raises(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, _minimal_config(extra_key="x"))
        with pytest.raises(ConfigurationError, match="extra_key"):
            BatchConfig.from_json_path(path)

    def test_empty_prompts_raises(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, {"prompts": []})
        with pytest.raises(ConfigurationError, match="between 1 and 50"):
            BatchConfig.from_json_path(path)

    def test_invalid_aspect_ratio_raises_with_valid_list(self, tmp_path: Path) -> None:
        path = _write_config(
            tmp_path,
            {"prompts": [{"text": "x", "aspect_ratio": "21:9"}]},
        )
        with pytest.raises(ConfigurationError) as exc:
            BatchConfig.from_json_path(path)
        msg = str(exc.value)
        assert "21:9" in msg
        assert "9:16" in msg  # valid options listed

    def test_invalid_model_raises_with_valid_list(self, tmp_path: Path) -> None:
        path = _write_config(
            tmp_path,
            {"prompts": [{"text": "x", "model": "stable-diffusion"}]},
        )
        with pytest.raises(ConfigurationError) as exc:
            BatchConfig.from_json_path(path)
        msg = str(exc.value)
        assert "stable-diffusion" in msg
        assert "nano2" in msg

    def test_count_too_large_raises(self, tmp_path: Path) -> None:
        path = _write_config(
            tmp_path,
            {"prompts": [{"text": "x", "count": 5}]},
        )
        with pytest.raises(ConfigurationError, match="between 1 and 4"):
            BatchConfig.from_json_path(path)

    def test_count_zero_raises(self, tmp_path: Path) -> None:
        path = _write_config(
            tmp_path,
            {"prompts": [{"text": "x", "count": 0}]},
        )
        with pytest.raises(ConfigurationError, match="between 1 and 4"):
            BatchConfig.from_json_path(path)

    def test_empty_prompt_text_raises(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, {"prompts": [{"text": ""}]})
        with pytest.raises(ConfigurationError, match="length must be between"):
            BatchConfig.from_json_path(path)


# ---------------------------------------------------------------------------
# Unit — output dir resolution + experimental transport gating
# ---------------------------------------------------------------------------


class TestResolveOutputDir:
    def test_cli_override_wins(self) -> None:
        result = resolve_batch_output_dir(
            cli_override=Path("/cli"), config_value="config", output_root=Path("/root")
        )
        assert result == Path("/cli")

    def test_config_value_used_when_no_cli(self) -> None:
        result = resolve_batch_output_dir(
            cli_override=None, config_value="cfg", output_root=Path("/root")
        )
        assert result == Path("cfg")

    def test_default_when_neither_set(self) -> None:
        from datetime import date

        today = date.today().isoformat()
        result = resolve_batch_output_dir(
            cli_override=None, config_value=None, output_root=Path("/root")
        )
        # Unified format: <root>/images/<YYYY-MM-DD>
        assert result == Path("/root/images") / today


class TestCheckTransportGated:
    def test_ui_automation_always_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GFLOW_CLI_EXPERIMENTAL_TRANSPORTS", raising=False)
        _check_transport_gated("ui_automation")  # no raise
        _check_transport_gated(None)  # no raise

    def test_experimental_rejected_without_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GFLOW_CLI_EXPERIMENTAL_TRANSPORTS", raising=False)
        with pytest.raises(ConfigurationError, match="experimental"):
            _check_transport_gated("bearer")

    def test_experimental_allowed_with_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GFLOW_CLI_EXPERIMENTAL_TRANSPORTS", "1")
        _check_transport_gated("evaluate_fetch")  # no raise


# ---------------------------------------------------------------------------
# Integration tests — `gflow run` Click command via CliRunner
# ---------------------------------------------------------------------------


def _patched_client_factory(
    *,
    image_for_prompt: AsyncMock | None = None,
    download_side_effect: Any = None,
):
    """Build a (CtxManager-conformant) async client mock."""
    inst = MagicMock()
    inst.__aenter__ = AsyncMock(return_value=inst)
    inst.__aexit__ = AsyncMock(return_value=None)
    inst.create_project = AsyncMock(return_value=MagicMock(project_id="proj-uuid"))
    if image_for_prompt is None:
        # One distinct media id per generation, as Flow returns: successful rows are
        # recorded (#913), and the catalog's attribution guard rejects a reused id.
        inst.generate_image = AsyncMock(
            side_effect=[_fake_generated_image(seed=s) for s in range(100, 150)]
        )
    else:
        inst.generate_image = image_for_prompt
    inst.generate_images_batch = AsyncMock(
        return_value=[_fake_generated_image(seed=i) for i in (1, 2)]
    )

    async def _dl(img: GeneratedImage, target: Path) -> Path:
        if download_side_effect is not None:
            raise download_side_effect
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x89PNG fake")
        return target

    inst.download_image = AsyncMock(side_effect=_dl)
    return inst


class TestGflowRunCommand:
    def test_happy_path_three_prompts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GFLOW_CLI_PROFILE", "example-profile")
        cfg_path = _write_config(
            tmp_path,
            {
                "prompts": [
                    {"text": "p1"},
                    {"text": "p2", "aspect_ratio": "16:9"},
                    {"text": "p3"},
                ]
            },
        )
        out = tmp_path / "out"
        fake_client = _patched_client_factory()
        with (
            patch("gflow_cli.cli_run.FlowApiClient", return_value=fake_client),
            patch("gflow_cli.cli_run._resolve_profile", return_value="example-profile"),
            patch(
                "gflow_cli.cli_run._make_provider_dir",
                return_value=tmp_path / "profiles" / "example-profile",
            ),
        ):
            result = CliRunner().invoke(
                cli_main,
                ["run", "--config", str(cfg_path), "--output-dir", str(out)],
                catch_exceptions=False,
            )
        assert result.exit_code == 0, result.output
        assert fake_client.generate_image.call_count == 3
        assert "3/3 succeeded" in result.output
        # Files written.
        assert (out / "prompt_0_0.png").exists()
        assert (out / "prompt_1_0.png").exists()
        assert (out / "prompt_2_0.png").exists()

    def test_continue_on_error_returns_max_exit_code(self, tmp_path: Path) -> None:
        """One prompt raises WafRejection (exit 10), others succeed → exit 10."""
        cfg_path = _write_config(
            tmp_path,
            {"prompts": [{"text": "p1"}, {"text": "p2"}, {"text": "p3"}]},
        )
        out = tmp_path / "out"
        call_count = {"n": 0}

        async def _gen_with_middle_fail(**_kwargs: Any) -> GeneratedImage:
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise WafRejectionError("simulated WAF block")
            return _fake_generated_image(seed=call_count["n"])

        fake_client = _patched_client_factory(
            image_for_prompt=AsyncMock(side_effect=_gen_with_middle_fail)
        )
        with (
            patch("gflow_cli.cli_run.FlowApiClient", return_value=fake_client),
            patch("gflow_cli.cli_run._resolve_profile", return_value="x"),
            patch("gflow_cli.cli_run._make_provider_dir", return_value=tmp_path / "p"),
        ):
            result = CliRunner().invoke(
                cli_main,
                ["run", "--config", str(cfg_path), "--output-dir", str(out)],
                catch_exceptions=False,
            )
        # WafRejection → exit code 10.
        assert result.exit_code == 10
        # All 3 prompts attempted.
        assert fake_client.generate_image.call_count == 3
        # Prompts 1 and 3 wrote files; prompt 2 did not.
        assert (out / "prompt_0_0.png").exists()
        assert not (out / "prompt_1_0.png").exists()
        assert (out / "prompt_2_0.png").exists()
        assert "2/3 succeeded" in result.output

    def test_fail_fast_halts_immediately(self, tmp_path: Path) -> None:
        cfg_path = _write_config(
            tmp_path,
            {"prompts": [{"text": "p1"}, {"text": "p2"}, {"text": "p3"}]},
        )
        out = tmp_path / "out"
        call_count = {"n": 0}

        async def _gen_with_middle_fail(**_kwargs: Any) -> GeneratedImage:
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise WafRejectionError("simulated WAF block")
            return _fake_generated_image(seed=call_count["n"])

        fake_client = _patched_client_factory(
            image_for_prompt=AsyncMock(side_effect=_gen_with_middle_fail)
        )
        with (
            patch("gflow_cli.cli_run.FlowApiClient", return_value=fake_client),
            patch("gflow_cli.cli_run._resolve_profile", return_value="x"),
            patch("gflow_cli.cli_run._make_provider_dir", return_value=tmp_path / "p"),
        ):
            result = CliRunner().invoke(
                cli_main,
                [
                    "run",
                    "--config",
                    str(cfg_path),
                    "--output-dir",
                    str(out),
                    "--fail-fast",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 10
        # Halted after prompt 2's failure.
        assert fake_client.generate_image.call_count == 2
        # Only prompt 1 wrote a file.
        assert (out / "prompt_0_0.png").exists()
        assert not (out / "prompt_2_0.png").exists()
        assert "1/3 succeeded" in result.output
        assert "1 skipped" in result.output

    def test_cli_output_dir_beats_config(self, tmp_path: Path) -> None:
        cfg_path = _write_config(
            tmp_path,
            {"output_dir": str(tmp_path / "from_cfg"), "prompts": [{"text": "x"}]},
        )
        cli_out = tmp_path / "from_cli"
        fake_client = _patched_client_factory()
        with (
            patch("gflow_cli.cli_run.FlowApiClient", return_value=fake_client),
            patch("gflow_cli.cli_run._resolve_profile", return_value="x"),
            patch("gflow_cli.cli_run._make_provider_dir", return_value=tmp_path / "p"),
        ):
            result = CliRunner().invoke(
                cli_main,
                ["run", "--config", str(cfg_path), "--output-dir", str(cli_out)],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert (cli_out / "prompt_0_0.png").exists()
        assert not (tmp_path / "from_cfg").exists()

    def test_experimental_transport_rejected_without_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GFLOW_CLI_EXPERIMENTAL_TRANSPORTS", raising=False)
        cfg_path = _write_config(
            tmp_path,
            {"transport": "bearer", "prompts": [{"text": "x"}]},
        )
        result = CliRunner().invoke(
            cli_main, ["run", "--config", str(cfg_path)], catch_exceptions=False
        )
        assert result.exit_code == 11
        assert "experimental" in result.output.lower()

    def test_single_session_across_prompts(self, tmp_path: Path) -> None:
        """Integration assertion: ONE __aenter__/__aexit__ for a 3-prompt batch."""
        cfg_path = _write_config(
            tmp_path,
            {"prompts": [{"text": "p1"}, {"text": "p2"}, {"text": "p3"}]},
        )
        out = tmp_path / "out"
        fake_client = _patched_client_factory()
        with (
            patch("gflow_cli.cli_run.FlowApiClient", return_value=fake_client),
            patch("gflow_cli.cli_run._resolve_profile", return_value="x"),
            patch("gflow_cli.cli_run._make_provider_dir", return_value=tmp_path / "p"),
        ):
            result = CliRunner().invoke(
                cli_main,
                ["run", "--config", str(cfg_path), "--output-dir", str(out)],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert fake_client.__aenter__.call_count == 1
        assert fake_client.__aexit__.call_count == 1
        assert fake_client.create_project.call_count == 1


class TestGflowRunProject:
    """`--project` / `"project"`: generate every row into an existing project."""

    def _invoke(self, tmp_path: Path, payload: dict[str, Any], *args: str) -> tuple[Any, Any]:
        cfg_path = _write_config(tmp_path, payload)
        fake_client = _patched_client_factory()
        with (
            patch("gflow_cli.cli_run.FlowApiClient", return_value=fake_client),
            patch("gflow_cli.cli_run._resolve_profile", return_value="x"),
            patch("gflow_cli.cli_run._make_provider_dir", return_value=tmp_path / "p"),
        ):
            result = CliRunner().invoke(
                cli_main,
                ["run", "--config", str(cfg_path), "--output-dir", str(tmp_path / "out"), *args],
                catch_exceptions=False,
            )
        return result, fake_client

    def test_cli_project_reuses_it_and_creates_none(self, tmp_path: Path) -> None:
        result, client = self._invoke(
            tmp_path, {"prompts": [{"text": "p1"}, {"text": "p2"}]}, "--project", "proj-existing"
        )
        assert result.exit_code == 0, result.output
        assert client.create_project.call_count == 0
        used = [c.kwargs["project_id"] for c in client.generate_image.call_args_list]
        assert used == ["proj-existing", "proj-existing"]

    def test_config_project_is_used(self, tmp_path: Path) -> None:
        result, client = self._invoke(
            tmp_path, {"project": "proj-config", "prompts": [{"text": "p1"}]}
        )
        assert result.exit_code == 0, result.output
        assert client.create_project.call_count == 0
        assert client.generate_image.call_args.kwargs["project_id"] == "proj-config"

    def test_cli_project_beats_config(self, tmp_path: Path) -> None:
        result, client = self._invoke(
            tmp_path,
            {"project": "proj-config", "prompts": [{"text": "p1"}]},
            "--project",
            "proj-cli",
        )
        assert result.exit_code == 0, result.output
        assert client.generate_image.call_args.kwargs["project_id"] == "proj-cli"

    def test_invalid_cli_project_is_a_usage_error(self, tmp_path: Path) -> None:
        result, client = self._invoke(
            tmp_path, {"prompts": [{"text": "p1"}]}, "--project", "bad id"
        )
        assert result.exit_code == 2
        assert client.generate_image.call_count == 0


class TestGflowRunResume:
    """#934: `--resume` re-uses rows a previous run already made in the same project."""

    def _invoke(
        self,
        tmp_path: Path,
        payload: dict[str, Any],
        *args: str,
        first_seed: int = 200,
        jpeg: bool = False,
    ) -> tuple[Any, Any]:
        cfg_path = _write_config(tmp_path, payload)
        # Each run gets its own media ids, as Flow does: the catalog rejects a reused one.
        fake_client = _patched_client_factory(
            image_for_prompt=AsyncMock(
                side_effect=[
                    replace(_fake_generated_image(seed=s), display_name=f"Run image {s}")
                    for s in range(first_seed, first_seed + 20)
                ]
            )
        )

        async def _download(img: GeneratedImage, target: Path) -> Path:
            # Bytes per image, as Flow serves: an overwritten file must hash differently.
            # With `jpeg` the file is named by its bytes, as the real download does (#96).
            saved = target.with_suffix(".jpg") if jpeg else target
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(b"\xff\xd8\xff " + img.media_name.encode())
            return saved

        fake_client.download_image = AsyncMock(side_effect=_download)
        with (
            patch("gflow_cli.cli_run.FlowApiClient", return_value=fake_client),
            patch("gflow_cli.cli_run._resolve_profile", return_value="x"),
            patch("gflow_cli.cli_run._make_provider_dir", return_value=tmp_path / "p"),
        ):
            result = CliRunner().invoke(
                cli_main,
                ["run", "--config", str(cfg_path), "--output-dir", str(tmp_path / "out"), *args],
                catch_exceptions=False,
            )
        return result, fake_client

    _CHAIN: dict[str, Any] = {
        "prompts": [{"text": "a red kite"}, {"text": "the kite at dusk", "ref": "batch:0"}]
    }

    def test_resume_needs_the_run_s_project(self, tmp_path: Path) -> None:
        result, client = self._invoke(tmp_path, self._CHAIN, "--resume")
        assert result.exit_code == 11, result.output
        assert "--project" in result.output
        assert client.generate_image.call_count == 0

    def test_a_done_parent_is_reused_and_its_child_references_it(self, tmp_path: Path) -> None:
        first, _ = self._invoke(tmp_path, self._CHAIN, "--project", "proj-a")
        assert first.exit_code == 0, first.output
        (tmp_path / "out" / "prompt_1_0.png").unlink()  # the child's file is lost

        result, client = self._invoke(
            tmp_path, self._CHAIN, "--project", "proj-a", "--resume", first_seed=300
        )

        assert result.exit_code == 0, result.output
        assert client.generate_image.call_count == 1  # only the child
        ref = client.generate_image.call_args.kwargs["req"].refs[0]
        assert ref.name == "projects/p/assets/asset-200"
        assert ref.display_name == "Run image 200"
        assert ref.in_project
        assert "RESUMED" in result.output

    def test_a_row_recorded_in_another_project_is_regenerated(self, tmp_path: Path) -> None:
        first, _ = self._invoke(tmp_path, self._CHAIN, "--project", "proj-a")
        assert first.exit_code == 0, first.output

        result, client = self._invoke(
            tmp_path, self._CHAIN, "--project", "proj-b", "--resume", first_seed=300
        )

        assert result.exit_code == 0, result.output
        assert client.generate_image.call_count == 2

    def test_a_file_the_catalog_does_not_know_is_regenerated(self, tmp_path: Path) -> None:
        out = tmp_path / "out"
        out.mkdir()
        (out / "prompt_0_0.png").write_bytes(b"\x89PNG not ours")

        result, client = self._invoke(
            tmp_path, {"prompts": [{"text": "a red kite"}]}, "--project", "proj-a", "--resume"
        )

        assert result.exit_code == 0, result.output
        assert client.generate_image.call_count == 1


def test_resume_finds_a_row_whose_image_was_saved_as_jpeg(tmp_path: Path) -> None:
    """Live 2026-10-24: Flow's images download as JPEG and are saved `prompt_0_0.jpg`, so
    a lookup for `.png` resumed nothing and regenerated every row."""
    runner = TestGflowRunResume()
    first, client = runner._invoke(  # noqa: SLF001
        tmp_path, {"prompts": [{"text": "a red kite"}]}, "--project", "proj-a", jpeg=True
    )
    assert first.exit_code == 0, first.output
    assert (tmp_path / "out" / "prompt_0_0.jpg").is_file()

    result, client = runner._invoke(  # noqa: SLF001
        tmp_path,
        {"prompts": [{"text": "a red kite"}]},
        "--project",
        "proj-a",
        "--resume",
        first_seed=300,
        jpeg=True,
    )

    assert result.exit_code == 0, result.output
    assert client.generate_image.call_count == 0
    assert "RESUMED" in result.output


class TestGflowRunResumeNeverReusesTheWrongImage:
    """Review of #934: a file name and a project are not enough to say a row is done."""

    _CHAIN: dict[str, Any] = TestGflowRunResume._CHAIN  # noqa: SLF001

    def test_a_row_whose_prompt_changed_is_regenerated_and_so_is_its_child(
        self, tmp_path: Path
    ) -> None:
        runner = TestGflowRunResume()
        first, _ = runner._invoke(tmp_path, self._CHAIN, "--project", "proj-a")  # noqa: SLF001
        assert first.exit_code == 0, first.output
        edited = {
            "prompts": [{"text": "a GREEN kite"}, {"text": "the kite at dusk", "ref": "batch:0"}]
        }

        result, client = runner._invoke(  # noqa: SLF001
            tmp_path, edited, "--project", "proj-a", "--resume", first_seed=300
        )

        assert result.exit_code == 0, result.output
        # The parent's prompt changed, and a child of a regenerated parent is stale too.
        assert client.generate_image.call_count == 2

    def test_an_overwritten_file_resolves_to_the_image_now_on_disk(self, tmp_path: Path) -> None:
        runner = TestGflowRunResume()
        args = ("--project", "proj-a")
        assert runner._invoke(tmp_path, self._CHAIN, *args)[0].exit_code == 0  # noqa: SLF001
        # A plain re-run overwrites both files with new images (300, 301).
        again, _ = runner._invoke(tmp_path, self._CHAIN, *args, first_seed=300)  # noqa: SLF001
        assert again.exit_code == 0, again.output
        (tmp_path / "out" / "prompt_1_0.png").unlink()

        result, client = runner._invoke(  # noqa: SLF001
            tmp_path, self._CHAIN, *args, "--resume", first_seed=400
        )

        assert result.exit_code == 0, result.output
        assert client.generate_image.call_count == 1
        assert client.generate_image.call_args.kwargs["req"].refs[0].name.endswith("asset-300")
