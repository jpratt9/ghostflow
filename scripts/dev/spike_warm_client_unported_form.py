"""Spike: after a SUCCESSFUL image run, does an unported form on the same warm
client get exit 36 — or a misleading RecaptchaError? (#891 / #781)

The hypothesis assembled by reading the code:

    client.py:783   self._page = self._pages[0]              # pool slot 0
    client.py:1182  transport.setup(page=self._page)         # transport drives slot 0
    config          concurrency defaults to 1                # the pool IS that one page

    ui_automation:3190  SUCCESS -> park page to about:blank immediately
    ui_automation:3174  FAILURE -> defer the park (#792, for incident capture)

    _common         flow_host_kind("about:blank") is None    # measured
                    -> raise_if_migrated() stays silent      # measured
                    -> TokenMinter raises RecaptchaError     # measured (spike_mint_on_about_blank)

so an unported form issued AFTER a success should surface `RecaptchaError`
instead of the precise exit-36 `FlowHostMigratedError`, while the same request
on a fresh client gets exit 36 (observed three times in the #639 sweep today).

A single CLI invocation cannot produce this: it needs two generations on ONE
warm client. Hence a script.

**Cost:** the first generation consumes Flow's DAILY IMAGE CAP. Zero Veo
credits. The second call is refused before submit and costs nothing.

Run:
    uv run python scripts/dev/spike_warm_client_unported_form.py --profile ffroliva --project <id>
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

OUT = Path(__file__).parent / "_spike_out"


def _page_url(client: Any) -> str:
    page = getattr(client, "_page", None)
    return str(getattr(page, "url", "<no page>"))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--project", required=True)
    args = ap.parse_args()

    from gflow_cli.api.client import FlowApiClient
    from gflow_cli.api.image import Aspect, GenerateImageRequest, Model
    from gflow_cli.profile_store import profile_dir as profile_dir_for
    from gflow_cli.profile_store import resolve_profile

    profile_dir = profile_dir_for(resolve_profile(args.profile))
    result: dict[str, Any] = {
        "spike": "warm_client_unported_form",
        "issue": "#891",
        "profile": args.profile,
    }

    async with FlowApiClient(profile_dir=profile_dir) as client:
        result["url_before_any_run"] = _page_url(client)

        # --- Call 1: a PORTED form. Should succeed on the migrated composer. ---
        ported = GenerateImageRequest(
            prompt="a plain matte grey cube on a white background",
            aspect=Aspect.LANDSCAPE,
            model=Model.NARWHAL,
        )
        try:
            img = await client.generate_image(project_id=args.project, req=ported)
            result["call1"] = "SUCCEEDED"
            result["call1_media"] = getattr(img, "media_name", None)
        except Exception as exc:  # noqa: BLE001 - reporting
            result["call1"] = f"{type(exc).__name__}: {str(exc)[:200]}"

        # THE load-bearing observation: where did the transport leave pool slot 0?
        result["url_after_call1"] = _page_url(client)
        transport = getattr(client, "transport", None)
        result["served_migrated_latch"] = getattr(transport, "_served_migrated_host", None)
        cap = getattr(transport, "uses_page_owned_image_recaptcha", None)
        result["page_owned_recaptcha"] = cap() if callable(cap) else None

        # --- Call 2: an UNPORTED form (ref by Flow media UUID) on the SAME client. ---
        # Expected-correct: FlowHostMigratedError (exit 36).
        # Hypothesised-actual:  RecaptchaError, because the mint runs on about:blank.
        from gflow_cli.api.image import ImageRef

        unported = GenerateImageRequest(
            prompt="a plain matte grey cube on a white background",
            aspect=Aspect.LANDSCAPE,
            model=Model.NARWHAL,
            refs=(ImageRef("2373d074-a61f-4a3c-846e-fb375c558d32"),),
        )
        try:
            await client.generate_image(project_id=args.project, req=unported)
            result["call2"] = "SUCCEEDED (neither expected outcome!)"
        except Exception as exc:  # noqa: BLE001 - the whole point
            result["call2_error_class"] = type(exc).__name__
            result["call2_exit_code"] = getattr(exc, "exit_code", None)
            result["call2_error"] = str(exc)[:300]

        result["url_after_call2"] = _page_url(client)

    verdict_ok = result.get("call2_error_class") == "FlowHostMigratedError"
    result["verdict"] = (
        "CORRECT — exit 36, hypothesis refuted"
        if verdict_ok
        else f"DEFECT CONFIRMED — got {result.get('call2_error_class')} instead of "
        f"FlowHostMigratedError"
    )

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "warm_client_unported_form.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
