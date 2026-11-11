"""BDD bindings: a refusal on flow.google.com's wire is reported as that refusal."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from gflow_cli.api.image import GenerateImageRequest
from gflow_cli.api.transports.migrated_composer import MigratedComposer
from gflow_cli.errors import ContentPolicyError, TransportTimeoutError, WafRejectionError
from tests.api.transports.test_batchexecute import REFUSAL
from tests.api.transports.test_migrated_composer import PROJ, FakePage, _batch_url

scenarios("migrated_refusal_envelope.feature")

#: Budget the video observer gets in these scenarios. A refusal must beat it by a wide
#: margin; the no-reason case is expected to consume it.
POLL_S = 1.5


def refusal_body(rpcid: str, code: int, reason: str | None) -> str:
    """The reply shape captured 2026-09-27 on ``ogiZ0b`` with a tampered reCAPTCHA token."""
    status: list[Any] = [code]
    if reason is not None:
        status += [None, [["type.googleapis.com/google.rpc.ErrorInfo", [reason]]]]
    frame = [["wrb.fr", rpcid, None, None, None, status, "generic"], ["di", 240]]
    return ")]}'\n\n192\n" + json.dumps(frame) + '\n25\n[["e",4,null,null,228]]\n'


@pytest.fixture
def world() -> dict[str, Any]:
    return {}


def _page(rpcid: str, body: str) -> FakePage:
    page = FakePage()
    page.dom.prompt = "a calm lake at dawn"
    page.scripted_responses = [(_batch_url(rpcid), body)]
    return page


@given("the migrated host refuses an image submit for unusual activity")
def _image_unusual(world: dict[str, Any]) -> None:
    world["kind"] = "image"
    world["page"] = _page("ogiZ0b", REFUSAL)  # the 2026-09-27 capture, byte for byte


@given("the migrated host refuses a video submit for unusual activity")
def _video_unusual(world: dict[str, Any]) -> None:
    world["kind"] = "video"
    world["page"] = _page("YhhmEf", refusal_body("YhhmEf", 7, "PUBLIC_ERROR_UNUSUAL_ACTIVITY"))


@given(parsers.parse("the migrated host refuses an image submit with {reason}"))
def _image_reason(world: dict[str, Any], reason: str) -> None:
    world["kind"] = "image"
    world["page"] = _page("ogiZ0b", refusal_body("ogiZ0b", 3, reason))


@given("the migrated host answers a video submit with a bare status-5 envelope")
def _video_bare(world: dict[str, Any]) -> None:
    # The #723 shape: an entity-bound submit Flow QUEUED, whose reply still reads [5].
    world["kind"] = "video"
    world["page"] = _page("MZZa6b", refusal_body("MZZa6b", 5, None))


@when("the image submit is observed")
@when("the video submit is observed")
def _observe(world: dict[str, Any]) -> None:
    composer = MigratedComposer()
    page = world["page"]
    if world["kind"] == "image":
        run = composer.submit_images_and_observe(page, GenerateImageRequest(prompt="a lake"))
    else:
        run = composer.submit_and_observe(
            page, poll_timeout_s=POLL_S, on_started=None, project_id=PROJ
        )
    started = time.monotonic()
    try:
        asyncio.run(run)
    except Exception as exc:  # noqa: BLE001 — the raised error is what the Then checks
        world["error"] = exc
    world["elapsed"] = time.monotonic() - started


@then(parsers.parse("gflow raises a WAF rejection naming {reason}"))
def _waf(world: dict[str, Any], reason: str) -> None:
    err = world.get("error")
    assert isinstance(err, WafRejectionError), repr(err)
    assert reason in err.detail


@then("it does not wait out the submit budget")
def _fast(world: dict[str, Any]) -> None:
    assert world["elapsed"] < POLL_S / 2


@then(parsers.parse("gflow raises a content-policy refusal naming {reason}"))
def _policy(world: dict[str, Any], reason: str) -> None:
    err = world.get("error")
    assert isinstance(err, ContentPolicyError), repr(err)
    assert reason in err.detail


@then("the run is not reported as a refusal")
def _not_refusal(world: dict[str, Any]) -> None:
    err = world.get("error")
    assert not isinstance(err, (WafRejectionError, ContentPolicyError)), repr(err)
    assert isinstance(err, TransportTimeoutError), repr(err)
