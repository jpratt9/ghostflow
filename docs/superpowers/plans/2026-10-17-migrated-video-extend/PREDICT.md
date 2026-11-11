# Predict: `gflow video extend` on flow.google.com — takeover of #882

**Proposal (design B).** Drive Flow's own extend UI on flow.google.com and observe the
wire passively, instead of #882's design A (gflow mints a reCAPTCHA token on a
`/project/` page and replays `fZytfe` via `page.request.post` with scraped `WIZ_global_data`
params and a synthesized project listing). Click path and wire measured at $0 by route-abort:
[spike 2026-10-17](../../spikes/2026-10-17-migrated-extend-ui-path.md).

## Verdict: CAUTION
**Confidence:** 7/10. The five personas averaged 7.0 and all independently chose B over A, which under the skill's formula would give 8 and GO. Every persona, however, attached mitigations it requires before execution, so the verdict is held at CAUTION.

## Summary

B removes everything that made A risky. The page mints its own token with the correct action, so there is no guessed `VIDEO_GENERATION` action and no relaxed mint guard. The page builds `inner[2]` itself, so the unmeasured `1`-vs-`2` question goes away. B sends no replayed request, carries no `SNlM0e` in a request body, and runs no second poller. It also matches every other port to the migrated host. What B does not yet cover is the chain: a second segment, extending from an existing scene, and resume are unmeasured, and the page creates the scene inside the submit, which breaks `_ExtendCapable`'s create-then-extend contract.

## Persona signals

| Persona | Signal | Conf. | Key point |
|---|---|---|---|
| Architect | CAUTION | 7 | New `transports/migrated_extend.py` like `migrated_video_upscale.py`; make composer's observer / `_await_terminal` / `_fetch_mp4` public and parametrised (`submit_rpcs`), never copy them; the page-created scene breaks `_ExtendCapable` |
| Security / reCAPTCHA | CAUTION→GO | 8 | A is STOP on this axis (guessed action, headers that mark the request as non-browser, relaxed guard, `at` handling). B's remaining risk is a wrong clip billed, so a $0 route guard on the `fZytfe` and `rqZuUc` bodies is required |
| Performance | CAUTION | 7 | B is faster than A on a single extend (A sleeps 90 s, then polls in parallel with the page). Chains are unmeasured. Use one checkout per link and remove listeners in `finally` |
| CLI / MCP UX | CAUTION | 7 | MCP exemption unchanged (`test_cli_parity.py:80-94`). Refusal matrix needed. The cost line has no price on this host. Docs to fix: USAGE:936, KNOWN_ISSUES:50, `--help`, llms.txt |
| Devil's Advocate | CAUTION | 6 | No simpler path. Keep #882's host-independent fixes (JSON `video_result`, the plan preamble that broke `--json`, single-segment direct download) with credit. One paid run is the only proof the server accepts the request |

## High-confidence risks (2+ personas)
1. **Chained extends are unmeasured** (Architect, Performance, UX, Devil's Advocate). Refuse `-n>1`, `--scene` and `--resume-from` until a spike measures them.
2. **A wrong id or wrong clip burns credits** (Security, UX, Devil's Advocate). Guard both before the click and at the wire.
3. **The REST-listing pre-flight (model, price, balance) is fiction on this host** (Architect, UX).

## Required mitigations before EXECUTE
1. **Single segment only** on the migrated arm. Refuse with exit 36 ("not ported to flow.google.com yet"), before the browser opens: `-n/--segments > 1`, `--scene`/`--resume-from`, `--seed`, and an `--aspect` that disagrees with the source clip.
2. **Media-in-project and video-kind guard** from the passive `Zzl0ze` read, run before any click. A media id not in the project gives exit 11 with the labs message. An image media id gives exit 11 with a #877/#878-style remediation.
3. **Wire guard at $0** (route): `fZytfe` slot 1 must equal the resolved workflow id, and `rqZuUc` must carry the media id. Otherwise `abort()` and raise a typed error. Never log request bodies, because they carry the page-minted token.
4. **Confirm the editor URL** `/project/<pid>/edit/<media>` before opening the extend menu. Measure whether a direct `goto` to that URL works ($0); if it does, it replaces the grid walk.
5. **Placement and reuse:** new module `migrated_extend.py`; reuse the composer's observer, terminal wait and mp4 fetch through public, parametrised names. Treat a 2xx `fZytfe` reply with no generation record as a failure.
6. **Delete design A:** its own mint, WIZ scraping, `page.request` replay, listing synthesis, the A-only `video_extend.py` helpers and the `/project/` exemption. Put develop's mint guard back unchanged.
7. **Cost line:** on this host the plan screen must not claim an exact price. Reword it, or source the price from a migrated credits read if one exists.
8. **Docs:** USAGE, KNOWN_ISSUES, `video extend --help` (each extend leaves a scene in Flow), llms.txt, and the skill header.
9. **One paid live extend** as the `e2e_video` test. Ask the owner first: it costs credits.

## Recommended next step
`/gflow:scenario` then `/gflow:plan` with the mitigations as tasks. The first task is a $0 spike on a direct `goto /edit/<media>` and on how a tile is anchored to its media id.
