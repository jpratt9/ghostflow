# Live verification — v0.91.0

> Evidence for this release, gathered on 2026-10-26 (PRs #1103, #1106, #1107, plus #1101
> merged after v0.90.0) and 2026-10-27 (#1109, #1115, each paid e2e on its PR head). Every row below was a run someone watched, not an inference. Where
> a check could not be run, the blocker is named.

## Environment

| | |
|---|---|
| Profile | `denon82` (real-browser Chrome strategy) |
| Host Flow served | `flow.google.com`, classic composer |
| Transport | `ui_automation` → migrated composer; MCP over stdio (`gflow mcp run`) |
| OS | Windows 11 (Google Chrome installed) |
| Tree | release branch `chore/release-v0.91.0`, cut from `develop@7b6b9054`, rebased onto `develop@31d6226a` |
| Veo credits spent | about 24 in the final release run (the two paid Pip rows). On the PRs: #1109 and #1115 ran paid `e2e_video` on `ffroliva` (about 24 credits each). Image daily quota: about 2 images in the release run, about 2 on the #1102 PR run |

## Release e2e on the release tree

Final run on 2026-10-28, on the release head `071f8bc6` (develop `ed2d9d7a` with #1104 and
#1113 merged in), one pytest process per file: **10 passed, 0 failed.**

| File | Profile | Result |
|---|---|---|
| `test_mcp_wait_false_bdd.py` | `denon82` | 2 passed (56 s) |
| `test_migrated_selector_drift_e2e.py` (project `02419c61-…`) | `denon82` | 1 passed (9 s). A first run without `GFLOW_CLI_E2E_PROJECT` skipped and was re-run with it |
| `test_auth_verification_e2e.py` | `denon82` | 4 passed (22 s) |
| `test_migrated_r2v_character_bdd.py` (character Pip) | `ffroliva` | **3 passed** (2 min 57 s): CLI r2v + Pip, MCP r2v + Pip through the queue, id-only refused before submit. Re-run here because #1115 changed `migrated_composer.py` after #1109's own run |

The first release run (2026-10-26, `develop@7b6b9054`, `denon82`) was 7/7 on the first three files.

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| MCP `wait=false` generations run (#1097) | MCP `gflow_generate_image` / `gflow_generate_video`, queued path | ✅ `test_mcp_wait_false_bdd.py`. A real `gflow mcp run` over stdio runs the job after the tool call returns, and closing stdin mid-job leaves a truthful row and no browser. 2/2 on PR #1101 (`6cc5c979`), on PR #1106 (`fdb2a765`) and on the release tree | 1 image per run |
| `tasks/get` / `tasks/cancel` follow SEP-2663; `tasks/result` gone (#1102) | MCP Tasks extension | ✅ same e2e, over the wire: `tasks/get` reaches `completed` with `ttlMs: null`, no `ttl`, and the image file inline in `result.structuredContent`. Both protocol eras (`legacy`, `2026-07-28`) are covered by in-process `mcp.Client` tests (`-32601` for `tasks/result`, the cancel ack) | $0 beyond the image above |
| The same over Streamable HTTP (#1102) | `gflow serve` on loopback | ✅ on the release tree: a real `gflow serve`, the SDK's HTTP client in both eras, against a completed task in the real catalog. `tasks/get` → `completed`, `ttlMs: null`, `result.isError: false` with 1 file (plus `resultType: "complete"` in `2026-07-28`); `tasks/result` → `-32601`; `tasks/cancel` → `{}` / `{resultType: "complete"}`. No browser started | $0 |
| The agent-only credit confirmation is read before approval (#988) | agent-only composer: `image t2i`, `video t2v`, and their MCP twins | ❌ **blocked**: no profile here is served the agent-only composer (spike `2026-10-17-agent-only-cohort-profiles.md`). Offline: driver tests against a fixture of the DOM a contributor captured on en and ru, including over-count, late title, two gates at once and an unreadable title. A $0 run on the contributor's account was requested on #988 / PR #1107 | — |
| Local-file r2v with a named character on flow.google.com (#723, PR #1109) | `video r2v --reference-entity` + `--reference-entity-name`; MCP `gflow_generate_video` | ✅ `test_migrated_r2v_character_bdd.py` on `ffroliva`, character Pip, head `a50b44ea`: **3 passed** (CLI clip downloaded with the entity attached; MCP the same; an id-only character refused before submit, exit 36, $0). Bound and refused cases are both e2e, CLI and MCP | 24 credits |
| A lost video submit reply is followed to its clip (#1112, PR #1115) | `video r2v` from local files, CLI and MCP (i2v: offline only, see below) | ✅ `-k` the two r2v rows (checked with `--collect-only` first) on `ffroliva`, head `b292ccc8`: **2 passed** in 137 s. On the MCP row Chrome lost the `MZZa6b` body, gflow adopted the status record carrying its uploaded id in the same second, and the clip reached status 3 and downloaded. The second-tab listing read is offline-only: it never fired live, because the status polls kept running | about 24 credits |
| Plugin-skills gate listed in the local routine (#1107) | contributor docs | out of scope: docs only | $0 |
| Session-hardening lessons (#1103) | docs | out of scope: docs only | $0 |

## Not verified

- **#1112 on i2v.** Only the two r2v rows ran live. The i2v and start+end (`nprQif`) arms
  share the same adoption code and are covered by offline tests; a lost reply cannot be
  forced live, so a paid i2v run would most likely not exercise the path at all.
- **#988 on a live agent-only account.** This is the external blocker named above. The fix
  fails closed: a video confirmation whose count cannot be read is never approved. Still
  unmeasured: the wording of a confirmation for several clips, and of an image confirmation.
- **Server-directed task creation** (`resultType: "task"`) and the `-32021` check for clients
  that did not declare the extension are not in this release: #1105.

## Pre-tag gates

- **Final tree (`071f8bc6`), 2026-10-28:** the six `scripts/ci` gates, ruff, format and
  `pyright src` green; full offline suite `-n 8`: **5566 passed, 29 skipped, 93% coverage**.
  `check_release_artifacts.py` OK. A delta council (3 auditors, on #1109/#1113/#1115/#1104)
  returned YELLOW, YELLOW, RED: the RED was one false sentence in `docs/MCP.md` (r2v with a
  character "exits 36"), fixed in `071f8bc6` with the other findings (`llms.txt`, README, USAGE
  exit 36, both skills, AGENTS, CHANGELOG deps line, this ledger's i2v scope).
- `/gflow:check` on the first release tree (2026-10-26): the six `scripts/ci` gates (now including
  `generate_plugin_skills.py --check`), ruff, format and `pyright src` are all green.
  `pytest -n 4` over `tests/mcp tests/api tests/features tests/worker` and the doc and config
  tests: **2726 passed, 6 skipped**. Each merged PR's head ran the full suite in CI.
- `scripts/ci/check_release_artifacts.py`: OK. Its first run failed this ledger for listing
  SEP-2663 over HTTP as "not run" with no blocker, which was correct. The check was then run
  live (the `gflow serve` row above) instead of being labelled.
- `/gflow:doc-review`:
  - Mechanical pass (sections 1–7) clean, apart from findings that predate this release:
    older ledgers are not listed in INDEX.
  - The council returned YELLOW from all three auditors (completeness, cross-reference,
    drift), with no RED and no Tier 1 finding. Their 9 Tier 2 findings are fixed in the
    release-prep commit:
    - `docs/MCP.md` now lists the two new exit-25 causes, says what happens to jobs queued
      by v0.90.0, and mentions `ttlMs: null`;
    - `config.py`, `.env.template` and `CONFIGURATION.md` now say the unreadable-video case
      is "not approved", not "rejected";
    - the old lead sentence in KNOWN_ISSUES is corrected;
    - the gate counts and their CI order now agree across AGENTS, CONTRIBUTING, DEVELOPMENT
      and `skills/check`.
  - Shipped plans removed: `2026-10-25-mcp-wait-false-runs`, `2026-10-26-mcp-tasks-sep2663`,
    `2026-10-26-agent-only-gate-count`.
  - Reports are at `tmp/council/0{1,2,3}-*.md` (local only).

## Post-tag evidence

- Signed tag `v0.91.0` (SSH signature present) on `bc532dc4`, pushed 2026-10-28.
- `Release` workflow run 40677690426: **success** (`build-and-publish`, `mcp-registry / publish`).
- PyPI `gflow-cli` reports `0.91.0` as the latest version.
- GitHub Release: https://github.com/ffroliva/gflow-cli/releases/tag/v0.91.0 (not a prerelease).
- Release PR #1116 into `main`.
