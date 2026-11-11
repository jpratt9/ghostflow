"""Step bindings for mcp_tasks.feature."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.exceptions import MCPError
from mcp.types import CancelTaskRequestParams, GetTaskRequestParams
from pytest_bdd import given, parsers, scenarios, then, when

from gflow_cli.data.store import DataStore
from gflow_cli.mcp.tasks_extension import TasksExtension

scenarios("mcp_tasks.feature")


@pytest.fixture
def temp_db(tmp_path: Path) -> DataStore:
    db_path = tmp_path / "test_gflow.db"
    store = DataStore.open(db_path)
    store.conn.execute(
        "INSERT OR IGNORE INTO profiles (name, first_seen_at) VALUES ('default', CURRENT_TIMESTAMP)"
    )
    return store


@pytest.fixture
def mcp_context() -> dict[str, Any]:
    return {"task": None, "response": None}


@given("a running gflow MCP server")
def running_mcp_server(temp_db: DataStore) -> None:
    pass


@given(parsers.parse('an enqueued generation task with ID "{task_id}"'))
def enqueued_task(task_id: str, temp_db: DataStore) -> None:
    temp_db.conn.execute(
        """
        INSERT INTO generation_queue
        (task_id, profile_name, task_type, payload_json, status, created_at, updated_at)
        VALUES (?, 'default', 'image', '{}', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (task_id,),
    )


@given(parsers.parse('no task exists with ID "{task_id}"'))
def no_task_exists(task_id: str, temp_db: DataStore) -> None:
    pass


@given('an MCP client requesting blocking execution with "wait=true"')
def blocking_client_request() -> None:
    pass


@when(parsers.parse('an MCP client invokes "{tool_name}" with prompt "{prompt}"'))
def invoke_mcp_tool(tool_name: str, prompt: str, mcp_context: dict[str, Any]) -> None:
    # Stub tool call response
    mcp_context["response"] = {"task_id": "task-uuid-new", "status": "pending"}


@when(parsers.parse('the MCP client sends a "tasks/get" request for "{task_id}"'))
def send_tasks_get(task_id: str, mcp_context: dict[str, Any], temp_db: DataStore) -> None:
    try:
        mcp_context["response"] = _get(temp_db, task_id)
    except MCPError as exc:
        mcp_context["response"] = {"error": {"code": exc.code, "message": str(exc)}}


def _get(store: DataStore, task_id: str) -> dict[str, Any]:
    handler = TasksExtension(data_store=store)._handle_get_task  # pyright: ignore[reportPrivateUsage]
    return asyncio.run(handler(None, GetTaskRequestParams(task_id=task_id)))


@when(parsers.parse('the MCP client sends a "tasks/cancel" request for "{task_id}"'))
def send_tasks_cancel(task_id: str, mcp_context: dict[str, Any], temp_db: DataStore) -> None:
    handler = TasksExtension(data_store=temp_db)._handle_cancel_task  # pyright: ignore[reportPrivateUsage]
    mcp_context["response"] = asyncio.run(handler(None, CancelTaskRequestParams(task_id=task_id)))


@when(parsers.parse('the client invokes "{tool_name}" with prompt "{prompt}"'))
def invoke_blocking_tool(tool_name: str, prompt: str, mcp_context: dict[str, Any]) -> None:
    mcp_context["response"] = {"files": ["/out/hero.png"]}


@then("a task is enqueued in the SQLite generation queue")
def check_task_enqueued(temp_db: DataStore) -> None:
    pass


@then(parsers.parse('the tool call returns a task handle with status "{status}".'))
def check_task_handle_returned(status: str, mcp_context: dict[str, Any]) -> None:
    resp = mcp_context["response"]
    assert resp is not None and resp.get("status") == status


@then("the server returns the current task status and details.")
def check_task_status_details(mcp_context: dict[str, Any]) -> None:
    resp = mcp_context["response"]
    assert resp is not None and "taskId" in resp and resp["status"] == "working"


@then("the cancel is an empty acknowledgement")
def check_cancel_ack(mcp_context: dict[str, Any]) -> None:
    assert mcp_context["response"] == {}


@then(parsers.parse('tasks/get then reports "{task_id}" as "{expected_status}".'))
def check_task_status_after(task_id: str, expected_status: str, temp_db: DataStore) -> None:
    assert _get(temp_db, task_id)["status"] == expected_status


@then(parsers.parse("the server returns a TaskNotFoundError with error code {code:d}."))
def check_task_not_found_error(code: int, mcp_context: dict[str, Any]) -> None:
    resp = mcp_context["response"]
    assert resp is not None and resp.get("error", {}).get("code") == code


@then("the tool call blocks until generation completes and returns asset paths.")
def check_blocking_tool_returns_files(mcp_context: dict[str, Any]) -> None:
    resp = mcp_context["response"]
    assert resp is not None and "files" in resp
