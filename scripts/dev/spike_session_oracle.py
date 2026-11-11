r"""Which signal still tells a signed-in Flow session from a signed-out one? ($0, #1023)

#1023: since 2026-10-22 ``https://labs.google/fx/api/auth/session`` answers **HTTP 410
Gone**, even without cookies. That URL is gflow's only session oracle
(``auth/verification.py::SESSION_API_URL``), so ``auth login`` rolls back its marker and
``auth status`` reports "could not verify" on a session that may be healthy. The
2026-09-06 spike (``docs/superpowers/spikes/2026-09-06-labs-vs-migrated-session-credential.md``,
Q4) predicted exactly this and calibrated a DOM signal on ``flow.google.com/``.

This re-measures that signal today, and records what the app itself fetches on load,
with two arms:

  ``profile``    the real profile (persistent context, real Chrome, as gflow runs it)
  ``anonymous``  a fresh bundled-Chromium context with no cookies (the control)

Per arm and run it records: where ``flow.google.com/`` lands, the avatar / sign-in CTA
counts, whether the profile's recorded account email (``.gflow_account``) appears in the
rendered DOM (a bool, never the value), every JSON-ish XHR/fetch the page makes (host +
path + status, no query, no body), and ``request.get`` probes of the candidate session
URLs (status + content type + top-level JSON keys only).

**Pre-registered readings** (written before the first run):

| Observation | Reading |
|---|---|
| labs URL 410 in both arms | #1023 confirmed: the oracle is gone, independent of the account |
| profile: lands on ``/``, avatar>0, email in DOM; anonymous: ``/about``, no email | the DOM oracle separates the states; candidate replacement |
| both arms look the same on every signal | no DOM oracle today; the replacement needs another source |
| some flow.google.com JSON endpoint carries ``user``/``email`` only in the profile arm | a wire oracle exists; name it |
| raw ``GET flow.google.com/`` (no render) carries the email under a stable ``WIZ_global_data`` key in the profile arm only | a no-render oracle exists that also READS the email; name the key |
| profile arm lands on ``/about`` | the profile is signed out OR in Google's re-verify state (#902); this run cannot tell which, report unmeasured |

**Cost:** page loads only; no submit, zero credits, zero quota.

    uv run python scripts/dev/spike_session_oracle.py <profile> [--runs 2]
"""

# ruff: noqa: E501 - the outcome table reads better unwrapped
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.async_api import async_playwright  # noqa: E402

from gflow_cli.profile_store import ACCOUNT_FILE  # noqa: E402

from _spike_common import build_client, default_out_path, resolve_profile_dir, step  # noqa: E402, isort: skip

PROBES = (
    "https://labs.google/fx/api/auth/session",
    "https://flow.google.com/fx/api/auth/session",
    "https://flow.google.com/api/auth/session",
)
_DOM_JS = """() => ({
  path: location.pathname,
  avatar: document.querySelectorAll("img[src*='googleusercontent']").length,
  signin_cta: document.querySelectorAll("a[href*='ServiceLogin'], a[href*='accounts.google.com']").length,
})"""


async def _probe(request: Any, url: str) -> dict[str, Any]:
    try:
        resp = await request.get(url, max_redirects=0, timeout=20_000)
    except Exception as exc:  # noqa: BLE001 - an unreachable probe is data
        return {"url": url, "error": type(exc).__name__}
    ctype = resp.headers.get("content-type", "")
    keys: list[str] | None = None
    if "json" in ctype:
        try:
            body = await resp.json()
            keys = sorted(body) if isinstance(body, dict) else [type(body).__name__]
        except Exception:  # noqa: BLE001
            keys = ["<unparsed>"]
    return {"url": url, "status": resp.status, "ctype": ctype.split(";")[0], "json_keys": keys}


_WIZ = re.compile(r'"(\w{4,8})":"([^"]*)"')


async def _shell(request: Any, email: str | None) -> dict[str, Any]:
    """The un-rendered page: does it carry the email, and under which WIZ_global_data key?"""
    resp = await request.get("https://flow.google.com/", timeout=30_000)
    text = await resp.text()
    keys = sorted({k for k, v in _WIZ.findall(text) if email and v.lower() == email.lower()})
    return {
        "status": resp.status,
        "final_path": urlsplit(resp.url).path,
        "bytes": len(text),
        "email_in_shell": None if email is None else email.lower() in text.lower(),
        "wiz_keys_holding_email": keys,
    }


async def _measure(page: Any, request: Any, email: str | None) -> dict[str, Any]:
    traffic: dict[str, dict[str, Any]] = {}

    async def on_response(response: Any) -> None:
        req = response.request
        if req.resource_type not in ("xhr", "fetch"):
            return
        parts = urlsplit(response.url)
        ctype = (await response.all_headers()).get("content-type", "").split(";")[0]
        has_email = None
        if email and ("json" in ctype or "javascript" in ctype or "text" in ctype):
            try:
                has_email = email.lower() in (await response.text()).lower()
            except Exception:  # noqa: BLE001 - an unreadable body is not a finding here
                has_email = None
        key = f"{parts.netloc}{parts.path}"
        if "batchexecute" in parts.path:
            query = dict(p.split("=", 1) for p in parts.query.split("&") if "=" in p)
            key += f"?rpcids={query.get('rpcids')}"
        row = traffic.setdefault(key, {"status": response.status, "ctype": ctype, "n": 0})
        row["n"] += 1
        row["has_email"] = bool(row.get("has_email")) or bool(has_email)

    page.on("response", on_response)
    await page.goto("https://flow.google.com/", wait_until="domcontentloaded")
    await page.wait_for_timeout(9_000)
    dom = await page.evaluate(_DOM_JS)
    html = await page.content()
    page.remove_listener("response", on_response)
    return {
        "dom": dom,
        "email_in_dom": None if email is None else email.lower() in html.lower(),
        "traffic": traffic,
        "probes": [await _probe(request, u) for u in PROBES],
        "shell": await _shell(request, email),
    }


async def _main(profile: str, runs: int, out: Path) -> int:
    profile_dir = resolve_profile_dir(profile)
    account = profile_dir / ACCOUNT_FILE
    email = account.read_text(encoding="utf-8").strip() if account.exists() else None
    step("account", f"recorded email present: {bool(email)}")
    findings: dict[str, Any] = {"profile": profile, "rows": []}

    async with build_client(profile_dir) as client:
        page = client._page  # noqa: SLF001 - dev instrument
        ctx = client._context  # noqa: SLF001
        assert page is not None and ctx is not None
        for i in range(runs):
            row = await _measure(page, ctx.request, email)
            findings["rows"].append({"arm": "profile", "run": i + 1, **row})
            step("profile", json.dumps({k: row[k] for k in ("dom", "email_in_dom", "shell")}))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        anon = await browser.new_context()
        page = await anon.new_page()
        row = await _measure(page, anon.request, email)
        findings["rows"].append({"arm": "anonymous", "run": 1, **row})
        step("anonymous", json.dumps({k: row[k] for k in ("dom", "email_in_dom", "shell")}))
        await browser.close()

    for r in findings["rows"]:
        carriers = [k for k, v in r["traffic"].items() if v.get("has_email")]
        step(f"{r['arm']} r{r['run']}", f"xhr/fetch carrying the email: {carriers}")
    out.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    step("out", str(out))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("profile")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = args.out or default_out_path("spike_session_oracle", ".json")
    return asyncio.run(_main(args.profile, args.runs, out))


if __name__ == "__main__":
    raise SystemExit(main())
