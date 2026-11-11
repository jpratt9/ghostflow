r"""Which references does the ``ogiZ0b`` image submit really carry after a character
mention? ($0 — the submit is ABORTED in the browser before it leaves.)

Drives the same steps as ``run_images`` up to the click — settings, optional local
references, ``attach_character_entities`` for ``--character``, the prompt — then routes
``ogiZ0b``: records the form-decoded body and aborts it, so Flow generates nothing and
no quota is spent. Prints every UUID in the body with its surrounding JSON, so you can
see which slot each reference rides in and whether anything not on the prompt rode
along (#723: chips deleted from the prompt still went into the generation).

    uv run python scripts/dev/spike_image_submit_references.py \
        --profile <profile> --project <uuid> --character Sussy [--ref local.png]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gflow_cli.api.image import Aspect, GenerateImageRequest  # noqa: E402
from gflow_cli.api.transports.migrated_composer import (  # noqa: E402
    COMPOSER,
    IMAGE_SUBMIT_RPC,
    MigratedComposer,
    _image_body_problem,
    _image_body_references,
    request_body,
    url_rpcid,
)

from _spike_common import build_client, default_out_path, resolve_profile_dir, step  # noqa: E402, isort: skip

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--character", required=True)
    ap.add_argument("--ref", action="append", default=[])
    ap.add_argument(
        "--trial-media",
        type=int,
        default=0,
        help="Reproduce the old trial-and-delete gesture first: commit the first option "
        "for the name N times and delete each chip with two Backspaces (chip + space).",
    )
    args = ap.parse_args()
    composer = MigratedComposer()
    findings: dict[str, Any] = {"character": args.character, "refs": args.ref}
    bodies: list[str] = []
    request = GenerateImageRequest(
        prompt=f"{args.character} reading by a window",
        aspect=Aspect.LANDSCAPE,
        reference_entity_names=(args.character,),
    )
    async with build_client(resolve_profile_dir(args.profile)) as client:
        page = client._page  # noqa: SLF001 - dev instrument
        assert page is not None
        await composer.ensure_editor(page, args.project)
        await composer.apply_image_settings(page, request)
        ref_ids: tuple[str, ...] = ()
        if args.ref:
            ref_ids = await composer.attach_references(
                page, args.project, tuple(Path(p) for p in args.ref)
            )
        if not ref_ids:
            await composer.clear_composer(page)
        for _ in range(args.trial_media):
            await page.locator(COMPOSER).first.click(timeout=5000)
            await page.keyboard.type("@", delay=120)
            await page.wait_for_timeout(2200)
            await page.keyboard.type(args.character, delay=100)
            await page.wait_for_timeout(2500)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2500)
            findings.setdefault("trial_chips", []).append(await composer.read_chips(page))
            for _ in range(2):
                await page.keyboard.press("Backspace")
                await page.wait_for_timeout(800)
        findings["chips_after_trials"] = await composer.read_chips(page)
        t0 = time.monotonic()
        entity_ids = await composer.attach_character_entities(
            page, entity_ids=(), names=(args.character,), clear=False
        )
        findings["attach_seconds"] = round(time.monotonic() - t0, 1)
        findings["chips"] = await composer.read_chips(page)
        await composer.send_prompt(page, request.prompt, append=True)

        async def capture(route: Any, req: Any) -> None:
            bodies.append(request_body(req))
            await route.abort()

        def is_submit(url: str) -> bool:
            return url_rpcid(url) == IMAGE_SUBMIT_RPC

        await page.route(is_submit, capture)
        submit = await composer._pre_submit_gate(page)  # noqa: SLF001 - dev instrument
        deadline = time.monotonic() + 30
        while not await submit.is_enabled() and time.monotonic() < deadline:
            await asyncio.sleep(0.5)
        await submit.click(timeout=5000)
        for _ in range(40):
            if bodies:
                break
            await page.wait_for_timeout(500)
        await page.unroute(is_submit, capture)
        await composer.clear_composer(page)

    findings["expected"] = {"refs": list(ref_ids), "entities": list(entity_ids)}
    findings["bodies"] = bodies
    out = default_out_path("spike_image_submit_references")
    out.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    step("trial chips", str(findings.get("trial_chips")))
    step("chips after trials", str(findings["chips_after_trials"]))
    step("attach", f"{findings['attach_seconds']} s, chips={findings['chips']}")
    step("expected", json.dumps(findings["expected"]))
    for body in bodies:
        ids = list(dict.fromkeys(_UUID.findall(body)))
        step("body", f"{len(body)} chars, {len(ids)} distinct uuid(s)")
        step("  slots (media, characters)", str(_image_body_references(body)))
        step(
            "  guard verdict",
            str(_image_body_problem(body, ref_ids, None, tuple(e for e in entity_ids if e))),
        )
        for uid in ids:
            i = body.index(uid)
            step(f"  {uid}", body[max(0, i - 90) : i + 60].replace("\n", " "))
    step("done", f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
