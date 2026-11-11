"""#934: `gflow run --resume` re-uses a parent row a previous run made in the project.

A `batch:N` child references its parent in place, by the handle Flow gave the parent.
Before #934 that handle existed only within the run, so a re-run regenerated the parent
too. This drives the real CLI twice against one project and one isolated catalog: the
second run with `--resume` must submit only the child, and the child must still reference
the parent in place.

Needs GFLOW_CLI_E2E_PROFILE and GFLOW_CLI_E2E_PROJECT. Costs 3 images of daily quota,
0 credits, and creates no project.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from .test_image_uuid_ref_e2e import _run_gflow

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_image]


def test_e2e_resume_submits_only_the_missing_child(e2e_env: dict[str, str], tmp_path: Path) -> None:
    project = os.environ.get("GFLOW_CLI_E2E_PROJECT", "").strip()
    if not project:
        pytest.skip("GFLOW_CLI_E2E_PROJECT must name an existing Flow project id")
    config = tmp_path / "run.json"
    config.write_text(
        json.dumps(
            {
                "project": project,
                "prompts": [
                    {"text": "a small red paper kite on a white table", "aspect_ratio": "1:1"},
                    {"text": "the same kite, now blue", "aspect_ratio": "1:1", "ref": "batch:0"},
                ],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "run-out"
    argv = ["run", "--config", str(config), "--output-dir", str(out)]

    first = _run_gflow(argv, e2e_env)
    assert first.returncode == 0, first.stderr[-1500:]
    # The saved extension is the bytes' (#96): Flow's images land as .jpg, not .png.
    (child,) = out.glob("prompt_1_0.*")
    child.unlink()

    second = _run_gflow([*argv, "--resume"], e2e_env)

    assert second.returncode == 0, second.stderr[-1500:]
    assert "RESUMED" in second.stdout, second.stdout[-1500:]
    assert list(out.glob("prompt_1_0.*")), sorted(p.name for p in out.iterdir())
    # The summary counts what ran: the child generated, the parent resumed, nothing else.
    assert "1/2 succeeded" in second.stdout and "1 resumed" in second.stdout, second.stdout[-800:]
