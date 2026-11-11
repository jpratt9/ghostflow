# Live verification — v0.87.0

> Evidence for this release, gathered on 2026-10-22 (PRs #1024, #1025, and the #995, #997,
> #986/#1003, #1013, #1014 wave). Every row below was a run someone watched, not an
> inference. Where a check could not be run, the blocker is named.

## Environment

| | |
|---|---|
| Profiles | `ffroliva` (real-browser Chrome strategy) |
| Host Flow served | `flow.google.com`, classic composer |
| Transport | `ui_automation` → migrated composer / migrated upscale |
| OS | Windows 11 (Google Chrome installed) |
| Tree | release branch `chore/release-v0.87.0`, cut from `develop@6d0d839b` |
| Veo credits spent | Veo lite clips under the standing e2e grant: the #1010 video body-loss twin (twice on the release tree, once on its PR), the #986 out-dir t2v, and the 1080p/GIF video upscale exports |

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| `auth status` / `auth login --browser chrome` verify again now that labs' session URL answers 410 (#1023) | `gflow auth status`, MCP `gflow_auth_status`, `gflow auth renew` | ✅ `test_auth_verification_e2e.py` + `test_auth_renew_e2e.py` + `test_auth_status_mcp_e2e.py`: all non-skipped passed on the release tree (on `develop` before the fix, 3 of 4 verification tests failed) | $0 |
| No second submit after a lost image submit reply (#1010) | `gflow image t2i` on flow.google.com | ✅ `test_migrated_submit_body_loss_bdd.py` image scenario passed on the release tree: exactly one `ogiZ0b`, exit 9 `retryable: false` with the check-the-project hint (red on unfixed code: two submits) | quota |
| A lost video submit reply is reported as possibly billed, not retryable (#1010) | `gflow video t2v` on flow.google.com | ✅ the video twin passed on the release tree: exactly one `YhhmEf`, `retryable: false` | 1 lite clip |
| MCP image results report the seed Flow used; `seed` param removed (#1013) | `gflow_generate_image` | ✅ `test_e2e_mcp_t2i_reports_the_seed_flow_used` passed | quota |
| `image i2i --ref <uuid>` of an earlier run's image, in place (#995) | `gflow image i2i`, MCP i2i | ✅ `test_earlier_run_ref_in_place_bdd.py` and `test_e2e_mcp_i2i_runs_on_the_migrated_host` passed | quota |
| The 4th `@` reference keeps its order (#997) | image prompt mentions | ✅ `test_mention_chip_order_bdd.py` passed (4 existing project images) | $0 |
| Without `--out-dir`, a flow.google.com clip saves under `tmp/` (#986) | `gflow video t2v` | ✅ `test_t2v_without_out_dir_saves_under_tmp` passed | 1 clip |
| Video upscale no longer reports a working export as failed (#1014) | `gflow video upscale` 1080p, 270p GIF | ✅ `test_migrated_video_upscale_1080p_e2e` and `test_migrated_video_export_270p_gif_e2e` passed | export |
| Classic regression on the migrated host | t2i, Nano 2 Lite, refusals, kill switch, warm client | ✅ `test_migrated_host_e2e.py`: 11 passed (video arms deselected) | quota |

Runs on the release tree (`ffroliva`, `GFLOW_CLI_E2E_PROJECT` set for the project-bound tests):
- auth + ref-in-place, `-m "e2e and not e2e_video"` → **9 passed**, 15 skipped (12 needed a project id, re-run below; 2 renew cases need a stale or `/about` profile, not configured)
- `test_migrated_submit_body_loss_bdd.py` → **2 passed in 44 s**
- `test_migrated_host_e2e.py` + `test_mention_chip_order_bdd.py` + `test_t2v_without_out_dir_saves_under_tmp` → **13 passed** in 404 s
- `test_migrated_upscale_e2e.py` → **3 passed, 1 failed**: the CLI 2K image upscale lost its `SPrCad` reply body (see below)

## 5-layer ledger

| Layer | #1010 body loss | #1023 session | Image regression |
|---|---|---|---|
| File count | none written (the run is reported, not retried), asserted | — | ≥ 1 image per CLI/MCP run, asserted |
| Magic bytes | — | — | size > 10 kB asserted |
| Duration / dimensions | — | — | not asserted |
| structlog | one submit request per rpcid counted on the context | `auth_labs_session_gone`, verdict `authenticated` via the myaccount check | `migrated.image_submit_guarded outcome=passed` |
| User-confirmable artifact | the generation in the project on `ffroliva`, made once | `gflow auth status` exit 0 "Flow session verified" | images in project `339f65ee…` on `ffroliva` |

## Observed, not changed

- **The 2K image upscale intermittently loses its `SPrCad` reply body** (Chrome's
  `Network.getResponseBody`, the #1009/#1014 class). It failed on the MCP arm in the first
  pass, and on the CLI arm in the second, where the MCP arm passed. `migrated_upscale.py` is
  unchanged since v0.86.0, so this is not a regression; filed as
  [#1027](https://github.com/ffroliva/gflow-cli/issues/1027). The first pass's filtered log
  does not name its other failures; every test in that batch passed when re-run.

## Verified after the tag, by the #1023 reporter

- **Interactive `auth login` and Linux** (2026-10-22, [comment](https://github.com/ffroliva/gflow-cli/issues/1023#issuecomment-6341075836),
  branch at `031c33a5`, Linux, real Chrome 155): `auth status` on a Google-only profile reported
  "Signed in to Google, but not to the Flow app" instead of the 410 error; an interactive
  `gflow auth login --browser chrome` completed with "Flow session verified", exit 0, and
  `auth status` then verified; one `image t2i` produced a 1024x1024 image. Not run there:
  `credits`, video, and the 410 path in `auth renew` (that one is covered by the e2e above).

## Not verified

- **`gflow credits`**: cannot read a balance on any account since labs' session URL answers
  410 (#795). Documented, not fixed.
- **`auth login --browser internal`**: cannot finish (#1026); `--browser chrome` is verified.
- **The agent-only composer (#1012)**: external blocker, no account we hold is in that cohort.
- **A cloud `GFLOW_CLI_STORAGE_URI` (#1003)**: needs a local S3 bucket, not running this
  session; verified when #1007 merged.
- **Accounts served labs**: blocker, every profile here is redirected to flow.google.com.

## Pre-tag gates

| Gate | Result |
|---|---|
| `/gflow:check` on the release tree | ✅ hygiene, website PII, website mirror, council memory, ruff, ruff format, pyright (0 errors) pass; offline suite **5234 passed, 11 skipped**, coverage 93%. The one failure on the first run (a remediation test that needs "flow.google.com" in the hint the doc-review edit reworded) was fixed and re-run green |
| E2E + live verification (this ledger) | ✅ as above, except #1027 (pre-existing, filed) |
| `/gflow:doc-review` | Council verdict before fixes: all three auditors **YELLOW**, none RED. T1/T2 fixed in the release-prep commit: README quickstart and llms.txt still promised a credits balance; #1026 missing from the CHANGELOG and AUTHENTICATION; stale `--refresh` advice in MCP, USER_GUIDE, the gflow-cli skill, the MCP `gflow_get_credits` description and the CLI help; a CHANGELOG sentence implying an MCP video seed. One finding was a false positive (`auth renew` does not exit 1 on a 410: it returns `stale=False` and the live renew e2e reported `authenticated`). Deferred: the unreachable no-token and 401 hints in `api/credits.py` (rewritten with #795). Reports were returned in-session. |
| `check_release_artifacts.py` | ✅ |

## Post-tag evidence

| | |
|---|---|
| Signed tag | `v0.87.0` on `f8ef90c5` (SSH signature present) |
| Release workflow | run `39779889040`: **success** (`build-and-publish` ✅, `mcp-registry / publish` ✅) |
| PyPI | `gflow-cli` latest = **0.87.0** |
| GitHub Release | https://github.com/ffroliva/gflow-cli/releases/tag/v0.87.0, stable (not a prerelease), published 2026-10-22T12:38:36Z |
