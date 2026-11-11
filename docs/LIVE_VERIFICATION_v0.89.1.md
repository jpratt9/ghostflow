# Live verification — v0.89.1

> Evidence for this release, gathered on 2026-10-24 (PRs #1071–#1080). Every row below was a
> run someone watched, not an inference. Where a check could not be run, the blocker is named.

## Environment

| | |
|---|---|
| Profile | `ffroliva` (real-browser Chrome strategy) |
| Host Flow served | `flow.google.com`, classic composer |
| Transport | `ui_automation` → migrated composer / migrated upscale |
| OS | Windows 11 (Google Chrome installed) |
| Tree | release branch `chore/release-v0.89.1`, cut from `develop@def08a7a` |
| Veo credits spent | none. Image daily quota: about 9 images across the PR runs and the release run |

## Release e2e on the release tree

`-m e2e` on `ffroliva`, project `9a9844dc-…`, one pytest process per file:
**9 passed, 1 skipped** (the video body-loss scenario, which spends credits and covers code this
release did not change).

| File | Result |
|---|---|
| `test_migrated_submit_body_loss_bdd.py` | 2 passed, 1 skipped (80 s) |
| `test_warm_client_upscale_e2e.py` (no pause) | 1 passed (53 s) |
| `test_auth_verification_e2e.py` | 4 passed (28 s) |
| `test_migrated_presubmit_gate_e2e.py` | 1 passed (10 s) |
| `test_migrated_host_e2e.py::test_e2e_t2i_binds_nano2_lite_on_the_migrated_host` | 1 passed (17 s) |

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| A lost image reply is recovered from the grid (#1075) | `image t2i/i2i`, MCP image tools (same client path) | ✅ `test_migrated_submit_body_loss_bdd.py`, t2i and i2i scenarios: the exact #1009 body-loss error is injected, **one** submit reaches Flow, the log shows `migrated.image_recovered_from_grid`, and the image downloads. The i2i scenario uses a local 256x256 reference and asserts the output is not the reference. Passed on the PR branch twice and on the release tree | 2 images per run |
| An upscale reloads the grid for a tile listed late (#1067) | `image upscale` live; `video upscale` and the MCP twins share the function (video: one reload in its 15 s budget, offline only) | ✅ `test_warm_client_upscale_e2e.py` with its 20 s pause **removed**: 3/3 on the PR branch, and in the 2 runs that logged it, `tile_not_listed_reloading` fired and the tile was then found; 1/1 on the release tree | 1 image, 2K upscale $0 |
| A hidden model picker is refused, with the Agent-chip hint (#788) | `--model` on image and video | ✅ visible-picker path: `test_e2e_t2i_binds_nano2_lite_on_the_migrated_host` 1/1 on the release tree (and the MCP alias test on the PR). The hidden-picker refusal itself: offline only, see blocker below | 1 image |
| `/about` names Google's identity re-check (#881 → #1080) | exit 31 remediation | offline only: message change at an existing raise site; see blocker | $0 |
| A declined upload says so (#755) | uploads on flow.google.com | offline only: on 2026-10-23 a live 1x1 PNG was **accepted**, so the refusal could not be produced; the measured envelope drives the unit test | $0 |
| `character create` keeps id and name in the catalog (#737) | local catalog | offline only: a local write after the create finishes; no Flow surface | $0 |
| Advisory CI check for gutted docs / orphaned references (#713) | CI | ✅ in CI on PR #1079 itself (Governance advisory), plus a backtest on the real deletion commit `c616e84f` | $0 |
| Spike clean-ups (#743, #759) | dev scripts | out of scope: dev instruments, no product surface | $0 |
| Regression: session checks, pre-submit gate | `auth status`, migrated submit | ✅ `test_auth_verification_e2e.py` 4/4, `test_migrated_presubmit_gate_e2e.py` 1/1 on the release tree | $0 |

## Not verified

- **#788's hidden-picker refusal live**: blocker, no account here shows Flow's agent-mode pane
  with the picker hidden on demand (the 2026-09-10 spike could not summon it either).
- **#1080's `/about` path live**: blocker, no profile here lands on `/about` today; `denon82`, the
  account that reproduced it, was cleared by hand after Google's re-check on 2026-09-23.
- **#755's refusal live**: blocker, Flow accepted the 1x1 PNG that the 2026-10-20 spike saw
  refused; the refusal cannot be produced on demand.
- **A natural (not injected) #1075 body loss**: intermittent, ~2 in 5 for the reporter; the
  injected loss raises the same Playwright error text #1009 captured.

## Observed, not changed

- The first release-tree attempt ran all five files in **one** pytest process and stalled after
  its first test with no output for ~30 minutes; it was stopped by PID. Re-run one process per
  file, everything passed in under 3 minutes total. Which test stalled was not recorded (`-q`),
  so this is noted rather than diagnosed.

## Pre-tag gates

- `/gflow:check` on the release tree: hygiene, doc links, PII, website mirror, council memory,
  release artifacts, ruff, format, pyright, offline suite (`5447 passed, 29 skipped`, `EXIT=0`
  before the doc-review fixes). Final tree: `5447 passed, 1 failed` — the failure was
  `test_overlay_precondition.py::test_dismissal_never_matches_on_text`, a real-Chromium
  `Page.goto` 30 s timeout under `-n 8`; it passed in the first full run and 18/18 alone on the
  final tree, and this release does not touch it.
- `/gflow:doc-review`: mechanical sections 1–7 pass. _Council verdict: YELLOW across all 3
  auditors (no RED, no Tier 1). 13 findings: 11 fixed in the release commit (exit 23/31 rows and
  the agent-mode table in `USAGE.md`/`KNOWN_ISSUES.md`, #1075 in the lost-reply-body entry, the
  stale `/about` text, the exit-31 detail that contradicted its own hint, the video-upscale
  wording plus an offline test for its one reload, a website-mirror link); 2 deferred (a
  `FlowAppError` row in `DEBUGGING.md`, and the mirror generator not rewriting `superpowers/`
  links, which predates this release). Council reports at `tmp/council/0{1,2,3}-*.md`
  (local-only)._

## Post-tag evidence

- `Release` workflow run `40075047500` on tag `v0.89.1`: **success**.
- GitHub Release `v0.89.1` published 2026-10-24T07:41:07Z (not a draft, not a prerelease).
- PyPI: `pip index versions gflow-cli` → `gflow-cli (0.89.1)`.
- Fresh install: `uvx --refresh --from "gflow-cli==0.89.1" gflow --version` → `gflow, version 0.89.1`.
- Release PR #1081 merged into `main` with a merge commit; `main` back-merged into `develop`.
