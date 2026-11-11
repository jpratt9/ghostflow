"""#995 — the worker marks a catalogued image ref ``in_project`` for its own project.

The MCP layer records each image ref's catalog project in ``ref_meta`` (see
``mcp.tools._ref_meta_entry``); ``build_image_request`` compares it with the task's
``project_id`` so the CLI and MCP surfaces route the same ref the same way.
"""

from __future__ import annotations

from gflow_cli.worker.codec import build_image_request

_UUID = "550e8400-e29b-41d4-a716-446655440000"


def _payload(*, project_id: str | None, recorded: str | None) -> dict[str, object]:
    meta: dict[str, str] = {"display_name": "Clay sun"}
    if recorded is not None:
        meta["flow_project_id"] = recorded
    payload: dict[str, object] = {
        "prompt": "the sun waves",
        "refs": [_UUID],
        "ref_meta": {_UUID: meta},
    }
    if project_id is not None:
        payload["project_id"] = project_id
    return payload


def test_ref_recorded_in_task_project_is_in_project() -> None:
    request = build_image_request(_payload(project_id="proj-1", recorded="proj-1"))
    assert request.refs[0].in_project is True
    assert request.refs[0].display_name == "Clay sun"


def test_ref_from_another_project_is_not_in_project() -> None:
    request = build_image_request(_payload(project_id="proj-1", recorded="proj-2"))
    assert request.refs[0].in_project is False


def test_task_without_project_is_not_in_project() -> None:
    request = build_image_request(_payload(project_id=None, recorded="proj-1"))
    assert request.refs[0].in_project is False


def test_ref_without_recorded_project_is_not_in_project() -> None:
    request = build_image_request(_payload(project_id="proj-1", recorded=None))
    assert request.refs[0].in_project is False
