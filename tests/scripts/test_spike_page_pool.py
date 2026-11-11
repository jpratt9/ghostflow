"""Every dev script that checks a Page out of the pool must check it back in.

`FlowApiClient._checkout_page` is documented as blocking forever
(`api/client.py`: *"Waits indefinitely if the pool is exhausted (no Pages
available). Callers that need a deadline must wrap the call themselves"*), and
the pool is an `asyncio.Queue(maxsize=n)` that defaults to one page. So a script
that takes the only page and never returns it has not leaked a resource — it has
armed a deadlock that fires the moment anything else needs a page.

Nothing else usually does, which is why this sat latent in seven scripts. Every
`client.<verb>()` that talks to Flow goes through `_post_json` / `_patch_json`,
and those check a page out themselves. On 2026-09-07 `spike_character_prompt_format.py`
added a `client.delete_characters(...)` cleanup call in its `finally` — obeying
`skills/spike/SKILL.md`'s "delete anything the spike created" — and the script
stopped exiting. It had completed all of its work: the capture and all three
screenshots were on disk. It hung in teardown, holding the `denon82` profile
lease, with no error and no traceback, because `contextlib.suppress(Exception)`
cannot rescue a block.

A wedged process holding a profile lease is also what sends an operator to the
process list; see `test_spike_profile_lease.py` for the other half of that.

The 17 scripts that already pair the calls are the reference; `_post_json`'s own
`attempt()` in `api/client.py` is the canonical shape:

    page = await self._checkout_page()
    try:
        ...
    finally:
        self._checkin_page(page)

Offline and text-level on purpose: milliseconds, no browser, fires before a
spike is ever run. Watched failing against all seven scripts before the fix.
"""

from __future__ import annotations

from pathlib import Path

_DEV_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "dev"

_CHECKOUT = "_checkout_page"
_CHECKIN = "_checkin_page"

# Enough to prove the scan still resolves. Without it, renaming the pool API
# silently empties the offender set and the guard passes forever — the
# enumeration gap `test_workflow_hardening.py` records as its own near-miss, and
# which `test_spike_profile_lease.py` guards the same way.
_MIN_EXPECTED_BORROWERS = 15


def _borrower_scripts() -> list[Path]:
    return sorted(
        path for path in _DEV_SCRIPTS.glob("*.py") if _CHECKOUT in path.read_text(encoding="utf-8")
    )


def test_the_scan_still_finds_the_page_borrowers() -> None:
    """A guard that matches nothing passes for the wrong reason."""
    found = _borrower_scripts()
    assert len(found) >= _MIN_EXPECTED_BORROWERS, (
        f"only {len(found)} script(s) call {_CHECKOUT}() under {_DEV_SCRIPTS} — "
        "the page-pool API was probably renamed, which would empty this guard "
        "silently. Update _CHECKOUT/_CHECKIN."
    )


def test_every_page_borrower_returns_the_page() -> None:
    offenders = [
        path.name
        for path in _borrower_scripts()
        if _CHECKIN not in path.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"these scripts take a Page from the pool and never return it: {offenders}. "
        "The pool defaults to ONE page and `_checkout_page()` waits forever, so the "
        "next call that needs a page — including any `client.<verb>()`, which check "
        "one out internally — deadlocks in silence while holding the profile lease. "
        "Pair it: `page = await client._checkout_page()` / "
        "`finally: client._checkin_page(page)`."
    )


# A third way to get a Page, used by the agent-only and migrated spikes (#745): a raw
# tab on the client's context, outside the pool. It cannot exhaust the pool, but it is
# only released by an explicit close or by the client's teardown, which closes the
# context and every page on it — so it must be opened inside `async with build_client`.
_OPEN = "_context.new_page("
_RELEASES = ("async with build_client(", "async with FlowApiClient(", ".close()")
_MIN_EXPECTED_OPENERS = 7


def _opener_scripts() -> list[Path]:
    return sorted(
        path for path in _DEV_SCRIPTS.glob("*.py") if _OPEN in path.read_text(encoding="utf-8")
    )


def _releases_its_page(source: str) -> bool:
    return any(release in source for release in _RELEASES)


def test_the_scan_still_finds_the_raw_page_openers() -> None:
    """Same canary as the borrowers', for the API the borrower scan cannot see."""
    found = _opener_scripts()
    assert len(found) >= _MIN_EXPECTED_OPENERS, (
        f"only {len(found)} script(s) call {_OPEN}) under {_DEV_SCRIPTS} — the API was "
        "probably renamed, which would empty this guard silently. Update _OPEN."
    )


def test_a_raw_page_outside_the_client_is_an_offender() -> None:
    leaked = "client = build_client(p)\npage = await client._context.new_page()\n"
    assert not _releases_its_page(leaked)
    assert _releases_its_page("async with build_client(p) as client:\n    " + leaked)


def test_every_raw_page_opener_releases_the_page() -> None:
    offenders = [
        path.name
        for path in _opener_scripts()
        if not _releases_its_page(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"these scripts open a raw Page on the client's context and never release it: "
        f"{offenders}. Open it inside `async with build_client(...) as client:` (teardown "
        "closes it) or `await page.close()` it in a `finally`."
    )
