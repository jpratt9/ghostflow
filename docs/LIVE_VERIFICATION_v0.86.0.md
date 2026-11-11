# Live verification — v0.86.0

> Evidence for this release, gathered on 2026-10-17/18 (PRs #989, #991, #982). Every row
> below was a run someone watched, not an inference. Where a check could not be run, the
> blocker is named.

## Environment

| | |
|---|---|
| Profiles | `ffroliva`, `denon82`, plus `flavio.oliva` for the `/about` case (real-browser Chrome strategy) |
| Host Flow served | `flow.google.com` on every profile here; the composer is classic on `ffroliva` and `denon82` |
| Transport | `ui_automation` → migrated composer / migrated extend |
| OS | Windows 11 (Google Chrome installed) |
| Tree | release branch `chore/release-v0.86.0`, cut from `develop@6600a36e` |
| Veo credits spent | **2 single-segment extends**, both owner-approved: one on #991 before its final refactor, one on the release tree |

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| `gflow video extend` runs on flow.google.com, one segment at a time (#991) | `gflow video extend <media> --project …` | ✅ e2e `test_e2e_one_paid_extend_downloads_an_mp4` passed **on the release tree**. `migrated.submit_observed rpc=fZytfe status=6`, with a new workflow `8433a5e4…`; mp4 downloaded | 1 extend |
| The page's own `fZytfe` carries the source **workflow** id, and `rqZuUc` carries the media id (#991 route guard) | the same | ✅ e2e `test_e2e_extend_submit_contract_at_zero_cost` passed (route aborted, nothing billed) | $0 |
| A media id that is not in the project is refused before any click (exit 11) | the same | ✅ e2e `test_e2e_a_media_not_in_the_project_is_refused_before_any_click` passed | $0 |
| A `--aspect` that disagrees with the source clip is aborted by the production guard (exit 36) | the same | ✅ e2e `test_e2e_a_foreign_aspect_is_aborted_by_the_production_guard` passed | $0 |
| Forms not ported yet (`-n 2`, `--seed`, `--scene`) are refused under the default `auto` host (exit 36), before anything is billed (#991 council fix) | `gflow video extend <media> "continue" --project … -n 2` / `--seed 7` / `--scene <id>` | ✅ run by hand on the release tree: each exited **36** with "not ported to flow.google.com yet (#639)"; no `fZytfe` was sent | $0 |
| `ensure_editor` now returns `"classic"`/`"agent_only"`; the classic composer is unchanged (#989 routing) | `gflow image t2i/i2i`, the MCP `gflow_generate_image` twins, and the refusals | ✅ `tests/e2e/test_migrated_host_e2e.py`: **11 passed** on the release tree (classic t2i, MCP t2i and MCP i2i through the queue, by-name refusals, the warm-client refusal, Nano 2 Lite) | quota only |
| t2i and t2v on the agent-only composer (#799, #989) | `gflow image t2i`, `gflow video t2v`, and the MCP twins | ⚠️ **External blocker:** no account we hold is in the agent-only cohort (spike `2026-10-17-agent-only-cohort-profiles.md`). The e2e skips here with that reason. Live runs by others: the contributor's `test_agent_only_composer_bdd.py` (3 passed, 2026-09-15), @Cstanish127 (`ru` UI, 2026-09-16), and @codtrance (3 accounts, t2i and t2v, 2026-10-17). | — |
| `gflow auth renew` refreshes saved sessions (#982) | `gflow auth renew` | ✅ `tests/e2e/test_auth_renew_e2e.py`: 4 passed on the release tree. A live profile verifies and stays readable; a held profile is skipped; **a stale profile becomes readable**; an `/about` profile is not reported as renewed | $0 |
| `gflow credits … --refresh` renews expired sessions (#982) | `gflow credits user --refresh`, `gflow_get_credits(refresh=true)` | ⚠️ Skipped on the release tree: neither `denon82` nor `ffroliva` was stale ("its fast path already reads a balance"), and the one stale profile was used up by the renew test. Proven live on 2026-10-16 at `9073ad7e` (stale→renewed, 2 passed); the code is unchanged since. | — |

Runs on the release tree:
- `GFLOW_CLI_E2E_RUN_VIDEO=1 GFLOW_CLI_E2E_PROFILE=ffroliva … pytest -m e2e tests/e2e/test_video_extend_migrated_e2e.py` → **4 passed in 264.85 s**
- `GFLOW_CLI_E2E_PROFILE=denon82 … pytest -m "e2e and not e2e_video" tests/e2e/test_migrated_host_e2e.py tests/e2e/test_agent_only_composer_bdd.py` → **11 passed, 2 skipped** (agent-only: "this project renders the classic composer; #799 needs an agent-only account")
- `pytest -m e2e tests/e2e/test_auth_renew_e2e.py tests/e2e/test_credits_refresh_e2e.py` → **3 passed, 3 skipped**; then the `/about` case with `GFLOW_CLI_E2E_ABOUT_PROFILE` set → **1 passed**

## 5-layer ledger

| Layer | Paid extend | Extend guard ($0) | Classic regression (#989) |
|---|---|---|---|
| File count | one new mp4 in the output directory, asserted | none written (refused or aborted), asserted | ≥ 1 image per CLI/MCP run, asserted |
| Magic bytes | `ftyp` asserted | — | not asserted; size > 10 kB asserted |
| Duration / dimensions | 6.5–8.5 s, asserted | — | not asserted |
| structlog | `migrated.submit_observed rpc=fZytfe`, a new media id ≠ source | the route guard's verdict, with the token never in the error (unit-tested) | `migrated.image_submit_guarded outcome=passed` |
| User-confirmable artifact | the extension clip in project `95763401…` on `ffroliva` | the aborted request bodies (redacted) | images in the e2e project on `denon82` |

## Observed, not changed

- **Every extend leaves a scene in the project**, as the UI does. gflow has no scene delete, so the spike and e2e runs left ~10 empty "Untitled Scene" entries in `95763401…`.
- **The first navigation timed out once** (`ui_automation.flow_initial_goto_failed`, `networkidle` 45 s) during the paid run's setup. It recovered, and the run passed.

## Not verified

- **The agent-only composer**: external blocker, as above. Reading the credit gate's clip count before approving it is tracked in #988.
- **Chained extends, `--scene`/`--resume-from` and `--seed` as working features**: not ported to flow.google.com yet (tracked under #639). Their refusal is verified live above; the features themselves are not.
- **Accounts served labs**: blocker. We hold no account that Flow serves from labs; every profile is redirected to flow.google.com.

## Pre-tag gates

| Gate | Result |
|---|---|
| `/gflow:check` on `develop@6600a36e` | ✅ hygiene, doc links, website PII, website mirror, plugin skills, council memory, ruff, ruff format, pyright (0 errors) all pass; offline suite **5162 passed, 25 skipped**, coverage 93% |
| E2E + live verification (this ledger) | ✅ as above: 4 + 11 + 4 e2e passed on the release tree; 3 refusals run by hand |
| `/gflow:doc-review` | Council verdict before fixes: Auditor 1 **RED**, Auditors 2–3 YELLOW. After fixes: GREEN. Findings: 2 T1 (a false `--output` sentence in the CHANGELOG; `video extend` missing from USAGE's exit-36 list) and ~10 T2 (extend and `--aspect` missing from README, KNOWN_ISSUES, CONFIGURATION and two skills; "before the browser opens" corrected to "before anything is billed"; the `GFLOW_CLI_AGENT_CONFIRM` caveat added to three places; llms.txt host qualifier). All T1 and T2 fixed in the release-prep commit. T3 (the `extend --dry-run` help still says "cost"; MCP.md does not mention extend is CLI-only) is deferred. Council reports at `tmp/council/0{1,2,3}-*.md` (local only). |
| `check_release_artifacts.py` | ✅ |

## Post-tag evidence

| | |
|---|---|
| Signed tag | `v0.86.0` on `d7ef85da` (SSH signature present) |
| Release workflow | run `39157226336`: **success** (`build-and-publish` ✅, `mcp-registry / publish` ✅) |
| PyPI | `gflow-cli` latest = **0.86.0** |
| GitHub Release | https://github.com/ffroliva/gflow-cli/releases/tag/v0.86.0, stable (not a prerelease), published 2026-10-18T19:07:10Z |
