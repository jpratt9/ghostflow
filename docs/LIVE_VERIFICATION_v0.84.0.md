# Live verification — v0.84.0

> Evidence for this release, gathered on 2026-10-12 (PRs #970, #971). Each row is a run
> someone watched, not an inference. Where a check could not be run, the blocker is named.

## Environment

| | |
|---|---|
| Profile | `denon82` (real-browser Chrome strategy) |
| Host Flow served | `flow.google.com` |
| Transport | `ui_automation` → migrated composer |
| OS | Windows 11 (Google Chrome installed) |
| Veo credits spent | 0 (images only, daily image quota) |

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| `gflow run --project ID` generates every row into an existing project (#970) | `gflow run --config … --project` | ✅ e2e `test_a_run_given_an_existing_project_generates_every_row_into_it_and_creates_none` passed on `develop` after the merge (63.6 s). The contributor also ran it, with the two existing `batch:N` / local-file scenarios, on their own account served flow.google.com | quota only |
| Multi-prompt `gflow image t2i --project ID` runs every prompt in that project (#971) | `gflow image t2i "a" "b" --project` | ✅ new e2e `test_multi_prompt_t2i_runs_every_prompt_in_the_given_project` passed on the branch (60.8 s), on a tree identical to the release tree. A first run failed on the test's own `*.png` glob (this host serves JPEG); the CLI had exited 0 with both images saved | quota only |

## 5-layer ledger

| Layer | `gflow run --project` e2e | `t2i --project` e2e |
|---|---|---|
| File count | 2 rows, a saved image each, asserted | 2 prompts, ≥ 2 files in `--out`, asserted |
| Magic bytes | not asserted; each file opens with Pillow (a real image) | not asserted; size > 10 kB asserted (files are `.jpg`) |
| Dimensions | short side ≥ 512 px, asserted | not asserted |
| structlog | run summary prints `(existing)` for the project, asserted | CLI exit 0, asserted |
| User-confirmable artifact | catalog holds exactly the created project, title unchanged; every asset's `flow_project_id` is that project | same two catalog assertions |

## Observed, not changed

- **A project id that does not exist.** Run on the release tree:
  `gflow image t2i "a paper boat" "a kite" --project 00000000-0000-0000-0000-000000000000
  --fail-fast`. Flow redirected to `flow.google.com/404?reason=project`; gflow waited 30 s
  for `.settings-trigger-button` and failed row 0 with **exit 23** (`UiSelectorDriftError`),
  row 1 skipped, no image, nothing billed. The run stops safely, but exit 23 names the wrong
  cause (a missing project, not selector drift). The same path serves single-prompt
  `t2i --project`, so this predates the release.
- **No MCP door.** `gflow run` is exempt in `tests/mcp/test_cli_parity.py` ("not yet
  ported") and `gflow_generate_image` takes one prompt, so neither change has an MCP twin to
  verify.

## Not verified

- **Accounts served labs.** Blocker: every profile we hold is redirected to flow.google.com.

## Pre-tag gates

| Gate | Result |
|---|---|
| `/gflow:changelog` | `[Unreleased]` → `[0.84.0] — 2026-10-12`: Added (#970, #971) |
| `/gflow:check` | on `827a0076` (tree identical to `develop@c7bc2430`, the release cut): hygiene, doc links, PII, mirror, council memory, ruff, format, pyright 0; pytest 4937 passed, 24 skipped, coverage 93% |
| SonarCloud | #970 was a fork PR (skipped); `develop` gate after its merge passed (new coverage 100%, 0 new issues). PR #971 gate passed |
| `/gflow:doc-review` | mechanical: links, PII, mirror, footer, 7 version sites green (older ledgers reachable only through INDEX's previous-chain, pre-existing). Council: Auditor 1 YELLOW (ACCOUNT_SAFETY still framed `--project` as single-prompt; `t2i --help` did not say it works with several prompts) → ACCOUNT_SAFETY updated, help now says so. Auditor 2 YELLOW (CHANGELOG cited no PR numbers; ACCOUNT_SAFETY; KNOWN_ISSUES #913 said a re-run always creates a project) → all three fixed. Auditor 3 GREEN (every claim matched to code; both options graded D4). Deferred: a missing project reports exit 23 instead of naming the project (see *Observed*). Reports local at `tmp/council/` |

## Post-tag evidence

| Check | Result |
|---|---|
| Signed tag | `v0.84.0` pushed; SSH signature present (`git cat-file -p v0.84.0` carries `BEGIN SSH SIGNATURE`) |
| Release workflow | run 38248825863: success (`build-and-publish`, `mcp-registry / publish`) |
| PyPI | `gflow-cli` 0.84.0 is the latest version on pypi.org |
| GitHub Release | `v0.84.0` published 2026-10-12T12:25:20Z, not a prerelease |
| Release PR | #972 merged into `main` (merge commit `f4a414b9`), SonarCloud gate passed |
| Back-merge | `main` → `develop` as `77df3929`; `main` is not ahead of `develop` |
