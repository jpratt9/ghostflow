"""E2E: a multi-prompt `gflow image t2i` with `--project ID` or `--project-name` (#975).

    GFLOW_CLI_E2E_PROFILE=<profile> uv run pytest -m e2e_image \
        tests/e2e/test_t2i_batch_project_e2e.py -v -o addopts=""

Cost: $0 in credits; two images from Flow's daily image quota. The project is titled
``gflow-e2e-t2i-project-*``; there is no delete route, so remove it in Flow when convenient.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_image]


def _gflow(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own CLI
        [sys.executable, "-m", "gflow_cli", *args],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    return proc


def test_multi_prompt_t2i_runs_every_prompt_in_the_given_project(
    e2e_env: dict[str, str], tmp_path: Path
) -> None:
    title = f"gflow-e2e-t2i-project-{uuid.uuid4().hex[:6]}"
    created = _gflow(e2e_env, "project", "create", "--title", title, "--json").stdout
    project_id = json.loads(created[created.index("{") :])["project_id"]

    out = tmp_path / "out"
    _gflow(
        e2e_env,
        "image",
        "t2i",
        "a paper boat on a pond",
        "a kite above a green hill",
        "--project",
        project_id,
        "--out",
        str(out),
    )

    images = sorted(p for p in out.iterdir() if p.is_file())
    assert len(images) >= 2 and all(p.stat().st_size > 10_000 for p in images), images
    with sqlite3.connect(e2e_env["GFLOW_CLI_DB_PATH"]) as con:
        projects = con.execute("SELECT flow_project_id, title FROM projects").fetchall()
        asset_projects = {r[0] for r in con.execute("SELECT flow_project_id FROM assets")}
    # No project was created, and the one we made keeps its title.
    assert projects == [(project_id, title)], projects
    assert asset_projects == {project_id}, asset_projects


def test_multi_prompt_t2i_titles_its_new_project_with_project_name(
    e2e_env: dict[str, str], tmp_path: Path
) -> None:
    # #975: the name was accepted and dropped; the project was titled `gflow-cli t2i`.
    title = f"gflow-e2e-t2i-name-{uuid.uuid4().hex[:6]}"
    out = tmp_path / "out"
    _gflow(
        e2e_env,
        "image",
        "t2i",
        "a paper boat on a pond",
        "a kite above a green hill",
        "--project-name",
        title,
        "--out",
        str(out),
    )

    assert len([p for p in out.iterdir() if p.is_file()]) >= 2
    with sqlite3.connect(e2e_env["GFLOW_CLI_DB_PATH"]) as con:
        titles = [r[0] for r in con.execute("SELECT title FROM projects")]
    assert titles == [title], titles
