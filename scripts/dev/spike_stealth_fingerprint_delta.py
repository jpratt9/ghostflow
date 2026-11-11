"""Spike: what does playwright-stealth change on top of gflow's own generation context?

**Question (#906 / PR #907).** A contributor reports Flow refusing every Playwright-driven
video submit with an "unusual activity" card, and that applying `playwright-stealth`
(`Stealth().apply_stealth_async(context)`) makes it succeed. gflow's generation context
already drops `--enable-automation`, passes `--disable-blink-features=AutomationControlled`
and overrides `navigator.webdriver` (`api/client.py`). So which properties does stealth
still change? That delta is the only place a stealth-vs-bare difference can come from.

**Method.** Through `FlowApiClient` (profile lease held, the page is gflow's own).
Arm `bare`: probe the fingerprint on flow.google.com. Arm `stealth`: apply stealth to
the SAME context, reload, probe again. Bare runs first because init scripts cannot be
removed. Also records request headers of the document load in each arm.

**Cost.** $0 — navigation and property reads only. Nothing is submitted.

**Pre-registered reading.**

- No field differs, or only cosmetic ones: stealth cannot explain a pass/fail flip on
  this machine. #906's A/B is then unexplained by fingerprint; it needs repeated arms
  and a control for its isolated-desktop launcher.
- A known automation tell differs (`webdriver`, `__pw*`/`cdc_` globals, missing
  `window.chrome`, empty `plugins`, `HeadlessChrome` in UA/brands): that one property is
  the candidate, and the fix is that property, not a dependency.
- `visibilityState`/`hasFocus` differ: an artefact of the window, not of stealth. Rerun
  with the window focused.

Neither outcome says anything about reCAPTCHA scoring on the contributor's account:
this measures the delta, not Google's reaction to it.

    uv run --with playwright-stealth python \
        scripts/dev/spike_stealth_fingerprint_delta.py --profile ffroliva
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _spike_common import (  # noqa: E402, isort: skip
    build_client,
    default_out_path,
    resolve_profile_dir,
    step,
)

FLOW = "https://flow.google.com/"

_PROBE_JS = r"""
async () => {
  const out = {};
  const n = navigator;
  out.webdriver = n.webdriver;
  out.userAgent = n.userAgent;
  out.appVersion = n.appVersion;
  out.platform = n.platform;
  out.vendor = n.vendor;
  out.languages = n.languages;
  out.hardwareConcurrency = n.hardwareConcurrency;
  out.deviceMemory = n.deviceMemory;
  out.plugins = Array.from(n.plugins || []).map(p => p.name);
  out.mimeTypes = (n.mimeTypes || []).length;
  if (n.userAgentData) {
    out.uaData = {brands: n.userAgentData.brands, mobile: n.userAgentData.mobile,
                  platform: n.userAgentData.platform};
    try {
      const h = await n.userAgentData.getHighEntropyValues(
        ['fullVersionList', 'platformVersion', 'architecture', 'bitness', 'model']);
      out.uaHigh = h;
    } catch (e) { out.uaHigh = String(e); }
  }
  out.windowChrome = typeof window.chrome === 'object' ? Object.keys(window.chrome).sort() : null;
  out.automationGlobals = Object.getOwnPropertyNames(window)
    .filter(k => /playwright|__pw|cdc_|webdriver|domAutomation|_selenium|callPhantom/i.test(k));
  out.notificationPermission = typeof Notification !== 'undefined' ? Notification.permission : null;
  try {
    out.permissionsQueryNotifications =
      (await n.permissions.query({name: 'notifications'})).state;
  } catch (e) { out.permissionsQueryNotifications = String(e); }
  out.window = {outerW: window.outerWidth, outerH: window.outerHeight,
                innerW: window.innerWidth, innerH: window.innerHeight,
                screenW: screen.width, screenH: screen.height, dpr: window.devicePixelRatio};
  out.visibilityState = document.visibilityState;
  out.hasFocus = document.hasFocus();
  out.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  try {
    const gl = document.createElement('canvas').getContext('webgl');
    const d = gl && gl.getExtension('WEBGL_debug_renderer_info');
    out.webgl = d ? [gl.getParameter(d.UNMASKED_VENDOR_WEBGL),
                     gl.getParameter(d.UNMASKED_RENDERER_WEBGL)] : null;
  } catch (e) { out.webgl = String(e); }
  out.toStringNative = Function.prototype.toString.call(
    Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver')?.get || (() => 0));
  return out;
}
"""

_HEADERS = ("user-agent", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform", "accept-language")


async def _probe(page: Any, label: str) -> dict[str, Any]:
    doc_headers: dict[str, str] = {}

    def _on_request(req: Any) -> None:
        if req.resource_type == "document" and req.frame == page.main_frame and not doc_headers:
            h = req.headers
            doc_headers.update({k: h[k] for k in _HEADERS if k in h})

    page.on("request", _on_request)
    await page.goto(FLOW, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(3_000)
    await page.bring_to_front()
    props = await page.evaluate(_PROBE_JS)
    page.remove_listener("request", _on_request)
    step(label, f"webdriver={props.get('webdriver')} globals={props.get('automationGlobals')}")
    return {"props": props, "doc_request_headers": doc_headers}


def _diff(a: Any, b: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[dict[str, Any]] = []
        for k in sorted(set(a) | set(b)):
            out += _diff(a.get(k), b.get(k), f"{path}.{k}" if path else k)
        return out
    return [] if a == b else [{"field": path, "bare": a, "stealth": b}]


async def _run(profile: str) -> int:
    from playwright_stealth import Stealth

    profile_dir = resolve_profile_dir(profile)
    out = default_out_path("spike_stealth_fingerprint_delta", ".json")
    record: dict[str, Any] = {"profile": profile}
    try:
        async with build_client(profile_dir) as client:
            page = client._page  # noqa: SLF001 — dev instrument
            ctx = client._context  # noqa: SLF001
            record["bare"] = await _probe(page, "bare")
            await Stealth().apply_stealth_async(ctx)
            record["stealth"] = await _probe(page, "stealth")
            record["delta"] = _diff(record["bare"], record["stealth"])
    finally:
        out.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        step("out", str(out))
    for d in record.get("delta", []):
        step("delta", json.dumps(d, default=str)[:300])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", default="ffroliva")
    return asyncio.run(_run(ap.parse_args().profile))


if __name__ == "__main__":
    raise SystemExit(main())
