# Live verification — v0.87.1

> Evidence for this release, gathered on 2026-10-22 (PRs #1029, #1031, #1033, #1034). Every
> row below was a run someone watched, not an inference. Where a check could not be run, the
> blocker is named.

## Environment

| | |
|---|---|
| Profiles | `ffroliva` and `denon82` (real-browser Chrome strategy), two Google accounts |
| Host Flow served | `flow.google.com`, classic composer |
| Transport | `ui_automation` → migrated composer / migrated upscale |
| OS | Windows 11 (Google Chrome installed) |
| Tree | release branch `chore/release-v0.87.1`, cut from `develop@29646c30` |
| Veo credits spent | one Veo lite clip on `denon82` to tell the two balance fields apart (#795 spike); the video-without-a-project tests abort the submit, and video upscale exports are $0 |

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| `gflow credits` reads the balance from flow.google.com (#795) | `gflow credits user`, MCP `gflow_get_credits` (one profile and `all_profiles`) | ✅ on the release tree, on **both** profiles: `test_credits_on_flow_bdd.py` runs `gflow credits user --json`, then opens Flow's account menu and asserts the two numbers are equal; `test_credits_mcp_e2e.py` 3 of 3 (one profile, all profiles with partial results kept, unknown profile refused) | $0 |
| `gflow credits list` across every saved profile (#795) | `gflow credits list` | ✅ run by hand on the PR head (d9856b7f), 11 profiles: 4 read a balance, 7 returned per-profile errors (5 `/about` landings, 2 `ProfileEngineDowngradeError`) and the list kept the partial results. The `/about` hint was reworded after this run | $0 |
| Project create/rename through the shared `_rpc_reply` (changed by #1034) | `gflow project create`, generation without `--project`, CLI and MCP | ✅ `test_project_create_e2e.py` 5 of 5 on the release tree (`denon82`) | quota (video submits aborted) |
| 2K image upscale survives a lost `SPrCad` reply (#1027) | `gflow image upscale`, MCP upscale | ✅ `test_migrated_upscale_e2e.py` image tests passed on the release tree (`ffroliva`); on the PR, 10 of 10 across 5 runs. Spike: the reply was lost on 6 of 12 upscales and the page's blob held identical bytes on 12 of 12 | $0 |
| Video upscale still works with the moved capture hook (#1027) | `gflow video upscale` 1080p, 270p GIF | ✅ both passed on the release tree (`GFLOW_CLI_E2E_RUN_VIDEO=1`) | $0 |
| A video run into an existing project keeps its catalog title (#1022) | local catalog only | not a Flow surface: offline tests (`tests/data/test_repository.py`, `test_recorder.py`) | — |
| `opentelemetry-api` 1.45.1 (CVE-2026-114603) | lockfile | `pip-audit` clean on #1033; MCP tests 247 passed | — |

## Not verified

- **`gflow credits --refresh` live**: blocker, no account here is stale in the way `auth renew`
  fixes. `tests/e2e/test_credits_refresh_e2e.py` needs such profiles in
  `GFLOW_CLI_E2E_STALE_PROFILES`; the stale-looking profiles from the `credits list` run land
  on `/about` (no session, or Google's re-verification), which renewal cannot fix. Offline
  tests cover the renew path.
- **What `nzlxg[0]` means on a paid plan**: blocker, no account on a paid plan. On both
  measured accounts `[0]` and `[5]` were equal and moved together; a paid plan may put a
  different bucket in `[0]`, which would give a wrong number without an error.
- **4K image upscale**: blocker, no account with a Flow Ultra subscription; both offer 4K
  only as a disabled menu item (exit 22).

## Not in this release

- **#1026 (`auth login --browser internal`)**: PR #1032 is reviewed but not merged. It has not
  been run against a live bundled-Chromium sign-in, which needs a person at the keyboard.

## Pre-tag gates

- `/gflow:check` on the release tree: hygiene, doc links, website PII, website mirror, council
  memory, ruff, ruff format, pyright 0 errors; offline suite 5228 passed / 29 skipped (re-run;
  a first run had one failure in `tests/composition/test_handoff.py`, which passes alone and on
  the re-run: the version bump was written while that run was in progress).
- `/gflow:doc-review`:
  _Council verdict: YELLOW across all 3 auditors. No Tier 1 findings, no fictional claims.
  Tier 2 fixed in the release-prep commit: the account count for #795 (two accounts, neither on
  a paid plan) in CHANGELOG, PROJECT_STATUS and KNOWN_ISSUES; exit 7 and the paid-plan limit
  in USAGE; the stale "credits returns 401" route in INDEX; the exit-3 row in USAGE; the
  KNOWN_ISSUES version; a spike script still calling the deleted `routes.CREDITS`; the
  `GFLOW_CLI_E2E_STALE_PROFILES` row; credits exit codes in the agent skill. Tier 3 deferred:
  USER_GUIDE's labs.google credits-badge pointer, consolidating the 2026-10-20/21/22 body-loss
  spikes. Council reports at `tmp/council/0{1,2,3}-*.md` (local-only)._
