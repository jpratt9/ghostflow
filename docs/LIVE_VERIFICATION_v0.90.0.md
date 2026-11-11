# Live verification — v0.90.0

> Evidence for this release, gathered on 2026-10-24 and 2026-10-25 (PRs #1084–#1098). Every
> row below was a run someone watched, not an inference. Where a check could not be run, the
> blocker is named.

## Environment

| | |
|---|---|
| Profile | `denon82` (real-browser Chrome strategy, 50 Veo credits) for the release run; `ffroliva` for the 2026-10-24 PR runs |
| Host Flow served | `flow.google.com`, classic composer |
| Transport | `ui_automation` → migrated composer |
| OS | Windows 11 (Google Chrome installed) |
| Tree | release branch `chore/release-v0.90.0`, cut from `develop@293b4e6c` |
| Veo credits spent | none in the release run; one `veo-lite` clip on the #941 PR run (2026-10-24). Image daily quota: about 11 images in the release run, about 15 across today's PR runs |

## Release e2e on the release tree

`-m e2e` on `denon82`, project `fd75972d-…`, one pytest process per file:
**15 passed, 0 skipped, 0 failed.**

| File | Result |
|---|---|
| `test_standalone_window_position_e2e.py` | 2 passed (11 s) |
| `test_incident_quality_e2e.py::test_a_failed_generation_bundle_is_not_hollow` | 1 passed (41 s) |
| `test_migrated_selector_drift_e2e.py` | 1 passed (9 s) |
| `test_insufficient_credits_e2e.py` (denon82 at 50 credits, `veo-quality` costs 100) | 1 passed (10 s) |
| `test_auth_verification_e2e.py` | 4 passed (23 s) |
| `test_image_download_failure_records_bdd.py` | 2 passed (75 s) |
| `test_local_ref_uploaded_once_bdd.py` | 3 passed (397 s) |
| `test_run_resume_e2e.py` | 1 passed (106 s) |

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| `gflow run --resume` (#934) | `gflow run` (CLI only, by design) | ✅ `test_run_resume_e2e.py`: only the missing child row is submitted. 1/1 on the PR (#1087) and 1/1 on the release tree | 3 images |
| A local `--ref` is uploaded into a project once (#772) | `image i2i`, MCP `gflow_generate_image` (worker) | ✅ `test_local_ref_uploaded_once_bdd.py`, three scenarios. CLI: the second run emits `reference_uploads.reused` with the first upload's id, attaches exactly that id in place, and **no** upload event fires. MCP twin: the same. A recorded image the project no longer holds: the in-place search misses, the file is uploaded once more, the new copy is recorded, and the submit guard passes. 3/3 on the PR branch, 3/3 on the release tree | 6 images |
| An unwritable output folder is exit 11 (#1091) | image downloads (CLI + MCP) | ✅ `test_image_download_failure_records_bdd.py`: exit 11, "Configuration error: Could not write the output file", no "Unexpected error", no path in the message, media id kept. 2/2 on the PR and on the release tree | 2 images |
| A corrupt cookie store is not a network problem (#796, part) | `auth status`, MCP `gflow_auth_status` | ✅ on the PR (#1096): a copy of denon82's profile with its `Cookies` file overwritten. develop said "Check network connectivity" (MCP 503, retryable); the branch says the cookie store is corrupt and to close Chrome and log in again (MCP 409, not retryable), 2/2. No browser launched. Regression on the release tree: `test_auth_verification_e2e.py` 4/4 | $0 |
| MCP `wait` described in `tools/list` (#481) | MCP schema | ✅ on the PR (#1095): real `gflow mcp run` over stdio, isolated home. `tools/list` shows the description on both generation tools, and a `wait=false` call stayed pending while `tasks/get` answered `working` (the gap now filed as #1097) | $0 |
| `movie.toml` entity + `variants` refused (#724) | manifest parsing | ✅ on the PR (#1094): `gflow movie run` on a sample manifest exits 11 with the fix in the message, before any browser starts. No Flow surface | $0 |
| Credit shortfall recognised in every UI language (#745) | migrated submit, exit 37 | ✅ `test_insufficient_credits_e2e.py` 1/1 on the PR (#1088) and on the release tree (denon82 cannot afford `veo-quality`) | $0 |
| Selector drift watched on flow.google.com (#1083) | selector registry, canary | ✅ `test_migrated_selector_drift_e2e.py` 1/1 on the PR (#1086) and on the release tree ("0 need attention") | $0 |
| Chip-count refusal states its numbers (#745 item 9) | refusal message | out of scope: message change at an existing raise site; offline | $0 |
| A signed URL that answers an HTTP error is exit 6 (#941, part 2) | video download, `data download` | ✅ `test_signed_url_http_error_e2e.py` (a hook forces a 403) 1/1 on the PR (#1084, 2026-10-24). Not re-run on the release tree: it spends Veo credits and no file it covers changed since | 1 `veo-lite` clip |
| Canary: two stale tests re-armed (#559, PR #1093) | e2e suite | ✅ both files on the PR and on the release tree (rows 1–2 above) | $0 |

## Not verified

- **#796's remaining half** (marker rollback after a `GOOGLE_SESSION_ONLY` login): not in this
  release; the issue stays open.
- **That a fresh login repairs a corrupt cookie database** (#796's new advice): not run. The
  login hint names the fallback (delete `Default/Network/Cookies`) for when it does not.
- **#1097 (`wait=false` never runs)**: documented, not fixed; filed for the next cycle.
- **#772 on labs**: blocker, every profile here is served flow.google.com (labs answers 308).

## Observed, not changed

- The #772 e2e first skipped silently: its events are INFO, which the default log level hides
  since #1041, and the host check read "no migrated events" as labs. The test now raises the
  child's log level and skips only on positive evidence of labs. The older
  `test_earlier_run_ref_in_place_bdd.py` reads INFO events the same way and was not re-run
  here.
- The canary had gone RED on two `$0` tests that a deliberate fix (#974) and a Windows change
  (the -30000 window offset is no longer clamped) had made stale; PR #1093 re-armed both.

## Pre-tag gates

- `/gflow:check` on the release tree: the five `scripts/ci` gates, ruff, format and
  `pyright src` all green; `pytest -n 8 --cov` **5499 passed, 29 skipped**, coverage 93%.
- `scripts/ci/check_release_artifacts.py`: OK.
- `/gflow:doc-review`: mechanical pass (sections 1–7) clean, apart from findings that predate this release (old ledgers not listed in INDEX). Council: completeness YELLOW, drift YELLOW, cross-reference RED (the `website/docs/` mirror lagged the release-prep edits; regenerated). 14 findings: the release-blocking ones fixed in the release-prep commit (USAGE still said an OS-refused write is exit 1; the `gflow_auth_status` tool description still named a daemon; the stale mirror), plus the Tier 2 gaps (exit-11 and exit-37 rows, `auth status` cookie-store shape, MCP `reference_images` reuse and #1091, `--resume` in the agent skill, #772 host scope, an MCP.md self-contradiction about `profile_marker_missing`). Reports at `tmp/council/0{1,2,3}-*.md` (local only).

## Post-tag evidence

- Signed tag `v0.90.0` (SSH signature present) on `164b8d26`, pushed 2026-10-25.
- `Release` workflow run 40191081861: **success** (`build-and-publish`, `mcp-registry / publish`).
- PyPI `gflow-cli` reports `0.90.0` as the latest version.
- GitHub Release: https://github.com/ffroliva/gflow-cli/releases/tag/v0.90.0 (not a prerelease).
- Release PR #1099 merged into `main` (merge commit `c073c531`); back-merge into `develop` `427d39cc`.
