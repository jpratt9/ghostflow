"""Credit balance on flow.google.com: the app's own ``nzlxg`` reply (#795).

Measured in docs/superpowers/spikes/2026-10-22-credits-balance-on-nzlxg.md: the app fetches
``nzlxg`` with no arguments on every load; the reply is
``[balance, a, b, c, null, balance', [refresh_epoch_s, nanos]]`` and ``[0]`` matched the
account menu in 5/5 reads, including a read after a 10-credit spend.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from gflow_cli.api.client import FlowApiClient
from gflow_cli.api.dto import CreditsInfo
from gflow_cli.api.transports import migrated_composer as mc
from gflow_cli.errors import AuthExpiredError, FlowAppError, WireFormatError

_REPLY = [37, 3, 8, 1, None, 37, [1793000000, 0]]


def _body(rpcid: str, payload: Any) -> str:
    frame = [["wrb.fr", rpcid, json.dumps(payload), None, None, None, "generic"]]
    return ")]}'\n\n10\n" + json.dumps(frame) + "\n"


class _Response:
    def __init__(self, rpcid: str, payload: Any) -> None:
        self.url = (
            f"https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids={rpcid}"
        )
        self._text = _body(rpcid, payload)

    async def text(self) -> str:
        return self._text


class _Page:
    """Loads a URL and replays what the app would receive while loading it."""

    def __init__(self, *, replies: list[_Response], land_on: str = mc.MIGRATED_ROOT_URL) -> None:
        self.url = "about:blank"
        self.replies, self.land_on = replies, land_on
        self.gotos: list[str] = []
        self._handlers: list[Any] = []

    def on(self, event: str, handler: Any) -> None:
        self._handlers.append(handler)

    def remove_listener(self, event: str, handler: Any) -> None:
        self._handlers.remove(handler)

    async def goto(self, url: str, **_: Any) -> None:
        self.gotos.append(url)
        self.url = self.land_on
        for reply in self.replies:
            for handler in list(self._handlers):
                await handler(reply)


def test_balance_is_index_zero_of_the_nzlxg_reply() -> None:
    assert CreditsInfo.from_nzlxg(_REPLY) == CreditsInfo(credits=37)


@pytest.mark.parametrize("payload", [None, [], {"credits": 5}, [True], ["5"], [-1]])
def test_a_reply_without_a_non_negative_balance_is_rejected(payload: object) -> None:
    with pytest.raises(ValueError, match="nzlxg"):
        CreditsInfo.from_nzlxg(payload)


async def test_read_credits_returns_the_balance_the_app_loaded() -> None:
    page = _Page(replies=[_Response("o30O0e", [1]), _Response(mc.CREDITS_RPC, _REPLY)])

    assert await mc.read_credits(page, timeout_s=1) == CreditsInfo(credits=37)  # type: ignore[arg-type]
    assert page.gotos == [mc.MIGRATED_ROOT_URL]


async def test_a_page_that_never_sends_nzlxg_is_a_flow_app_error_not_an_auth_error() -> None:
    page = _Page(replies=[_Response("o30O0e", [1])])

    with pytest.raises(FlowAppError) as caught:
        await mc.read_credits(page, timeout_s=0.1)  # type: ignore[arg-type]

    assert not isinstance(caught.value, AuthExpiredError)
    assert caught.value.route == f"batchexecute:{mc.CREDITS_RPC}"
    hint = caught.value.remediation_hint
    assert "auth login" not in hint and "SAPISID" not in hint, hint


async def test_a_signed_out_landing_is_named_as_such() -> None:
    page = _Page(replies=[], land_on="https://accounts.google.com/v3/signin/identifier")

    with pytest.raises(AuthExpiredError):
        await mc.read_credits(page, timeout_s=0.1)  # type: ignore[arg-type]


async def test_a_malformed_reply_is_a_wire_format_error() -> None:
    page = _Page(replies=[_Response(mc.CREDITS_RPC, ["x"])])

    with pytest.raises(WireFormatError, match="nzlxg"):
        await mc.read_credits(page, timeout_s=1)  # type: ignore[arg-type]


async def test_client_get_credits_reads_nzlxg_on_a_pooled_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    client = FlowApiClient(profile_dir=tmp_path / "profile")
    page = object()
    client._page = page  # type: ignore[assignment]  # mock-injected page, see _checkout_page
    read = AsyncMock(return_value=CreditsInfo(credits=5))
    monkeypatch.setattr(mc, "read_credits", read)

    assert await client.get_credits() == CreditsInfo(credits=5)
    read.assert_awaited_once_with(page)


class _Unreadable(_Response):
    async def text(self) -> str:
        raise RuntimeError("Network.getResponseBody: No resource with given identifier found")


class _Refusal(_Response):
    def __init__(self, rpcid: str) -> None:
        super().__init__(rpcid, None)
        frame = [["wrb.fr", rpcid, None, None, None, [7, None, [["x", ["PERMISSION"]]]], "generic"]]
        self._text = ")]}'\n\n10\n" + json.dumps(frame) + "\n"


async def test_a_lost_nzlxg_body_is_logged_and_named_not_called_absent(install_log_capture) -> None:
    page = _Page(replies=[_Unreadable(mc.CREDITS_RPC, None)])

    with pytest.raises(FlowAppError) as caught:
        await mc.read_credits(page, timeout_s=0.1)  # type: ignore[arg-type]

    assert "no readable nzlxg reply" in caught.value.detail
    assert "1 batchexecute bodies unreadable" in caught.value.detail
    events = [e for e in install_log_capture.entries if e["event"].endswith("body_unreadable")]
    assert events and events[0]["carries_rpcid"] is True
    assert "identifier" not in str(events)  # the class name only, never the message


async def test_an_nzlxg_refusal_raises_at_once_and_is_not_called_a_missing_fetch() -> None:
    page = _Page(replies=[_Refusal(mc.CREDITS_RPC)])

    with pytest.raises(WireFormatError, match="refused nzlxg") as caught:
        await mc.read_credits(page, timeout_s=5)  # type: ignore[arg-type]

    assert "prompt" not in caught.value.remediation_hint  # not the generation-payload default


async def test_an_about_landing_from_credits_names_googles_reverification() -> None:
    page = _Page(replies=[], land_on="https://flow.google.com/about")

    with pytest.raises(FlowAppError) as caught:
        await mc.read_credits(page, timeout_s=0.1)  # type: ignore[arg-type]

    hint = caught.value.remediation_hint
    # Both measured causes (live `credits list`, 2026-10-22): no Google session at all,
    # and a signed-in account Google holds at /about for re-verification.
    assert "gflow auth status --profile" in hint
    assert "gflow auth login --browser chrome --profile" in hint
    assert "Confirm it's you" in hint
    assert "--user-data-dir" in hint
    assert "project" not in hint
    assert "project" not in caught.value.detail
    assert caught.value.retryable is False
