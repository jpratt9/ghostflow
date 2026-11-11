"""#481: every MCP tool that takes ``wait`` must explain it in the schema agents read.

The tool docstring's ``Args:`` block never reaches ``tools/list`` (the explicit
``description=`` wins and parameter descriptions come only from the schema), so the
check is on the listed ``inputSchema`` — the one surface an agent actually sees.
"""

from __future__ import annotations

from typing import Any

import pytest


def _tools_with_wait(mcp_server: Any) -> dict[str, dict[str, Any]]:
    return {
        name: tool.parameters["properties"]["wait"]
        for name, tool in mcp_server._tool_manager._tools.items()
        if "wait" in tool.parameters.get("properties", {})
    }


def test_both_generation_tools_take_wait(mcp_server: Any) -> None:
    assert set(_tools_with_wait(mcp_server)) >= {"gflow_generate_image", "gflow_generate_video"}


@pytest.mark.parametrize(
    "phrase",
    [
        "task_id",  # what wait=false returns
        "tasks/get",  # status read-back (SEP-2663 Tasks extension)
        "result field",  # the finished job's files ride on tasks/get (#1102)
        "isError",  # a failed generation reads completed (SEP-2663, #1102)
        "tasks/cancel",  # stops the job, not only the row (#1097)
        "pending",  # what the call returns at once
        "tool timeout",  # why an agent would reach for it at all
    ],
)
def test_wait_description_names_the_queued_contract(mcp_server: Any, phrase: str) -> None:
    for name, prop in _tools_with_wait(mcp_server).items():
        description = prop.get("description", "")
        assert phrase in description, f"{name}: `wait` schema description lacks {phrase!r}"


def test_wait_default_stays_true(mcp_server: Any) -> None:
    for name, prop in _tools_with_wait(mcp_server).items():
        assert prop.get("default") is True, f"{name}: `wait` default changed"


def test_wait_description_does_not_send_agents_to_tasks_result(mcp_server: Any) -> None:
    """SEP-2663 removes tasks/result; the server answers it -32601 (#1102)."""
    for name, prop in _tools_with_wait(mcp_server).items():
        assert "tasks/result" not in prop.get("description", ""), name


def test_wait_description_no_longer_says_the_job_never_runs(mcp_server: Any) -> None:
    """#1097 made wait=false jobs run; the old warning would now be false."""
    for name, prop in _tools_with_wait(mcp_server).items():
        assert "never generated" not in prop.get("description", ""), name
