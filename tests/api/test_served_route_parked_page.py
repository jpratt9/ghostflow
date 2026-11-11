"""#914: after a migrated image run the pool page is parked on about:blank, so its URL
no longer names the host. The route must come from the host the run was served, or an
upscale/extend on the same warm client mints reCAPTCHA on about:blank (measured
2026-10-23: `RecaptchaError … the page the mint ran on is not a Flow page`)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from gflow_cli.api.client import FlowApiClient
from gflow_cli.config import Settings


def _client(tmp_path: Path, url: str, parked: bool, flow_host: str = "auto") -> FlowApiClient:
    client = FlowApiClient(
        tmp_path / "profile", settings=Settings(home=tmp_path, flow_host=flow_host)
    )
    client._page = SimpleNamespace(url=url)  # type: ignore[assignment]  # noqa: SLF001
    client.transport = SimpleNamespace(parked_after_migrated=parked)  # type: ignore[assignment]
    return client


def test_a_parked_page_routes_to_the_host_the_last_run_was_served(tmp_path: Path) -> None:
    client = _client(tmp_path, "about:blank", parked=True)
    assert client.served_route(prefer_migrated=False) == "migrated"


def test_a_page_never_parked_keeps_the_old_answer(tmp_path: Path) -> None:
    client = _client(tmp_path, "about:blank", parked=False)
    assert client.served_route(prefer_migrated=False) == "labs"


def test_a_live_flow_page_still_decides(tmp_path: Path) -> None:
    client = _client(tmp_path, "https://labs.google/fx/tools/flow", parked=True)
    assert client.served_route(prefer_migrated=False) == "labs"


def test_the_labs_kill_switch_still_blocks_a_parked_migrated_page(tmp_path: Path) -> None:
    client = _client(tmp_path, "about:blank", parked=True, flow_host="labs.google")
    assert client.served_route(prefer_migrated=False) == "blocked"
