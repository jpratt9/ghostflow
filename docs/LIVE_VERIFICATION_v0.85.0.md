# Live verification — v0.85.0

> Evidence for this release, gathered on 2026-10-14 (PRs #979, #976). Each row is a run
> someone watched, not an inference. Where a check could not be run, the blocker is named.

## Environment

| | |
|---|---|
| Profile | `ffroliva` (real-browser Chrome strategy) |
| Host Flow served | `flow.google.com` |
| Transport | `ui_automation` → migrated composer |
| OS | Windows 11 (Google Chrome installed) |
| Tree | release branch `chore/release-v0.85.0`, cut from `develop@26b65f48` |
| Veo credits spent | 0 (images only, daily image quota) |

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| `@Character` in an image prompt attaches the Flow character through the `@` picker (#723, #979) | `gflow image t2i "@Kael …" --project` | ✅ e2e `test_the_cli_binds_the_character_not_a_media_asset_sharing_its_name` passed on the release tree. The contributor ran the same suite on their own account (character "Sussy") | quota only |
| The MCP twin takes the same path through the worker queue | `gflow_generate_image(prompt="@Kael …", wait=True)` | ✅ e2e `test_the_mcp_image_tool_binds_the_same_character_through_the_queue` passed | quota only |
| A character next to an uploaded reference image | `gflow image i2i "@Kael …" --ref <local.png>` | ✅ e2e `test_the_cli_binds_the_character_next_to_an_uploaded_reference_image` passed: guard `body_media=1, body_characters=1` | quota only |
| A `--reference-entity` id without a name is refused, not dropped (council finding on #979) | `gflow image t2i … --reference-entity <id>` | ✅ e2e `test_a_character_given_only_by_entity_id_is_refused_before_submit` passed: exit 36, "a character given by entity id without a name", no image written | $0 (refused before submit) |
| Multi-prompt `t2i --project-name` titles the new project (#975) | `gflow image t2i "a" "b" --project-name X` | ✅ e2e `test_multi_prompt_t2i_titles_its_new_project_with_project_name` passed on the release tree | quota only |

Run: `GFLOW_CLI_E2E_PROFILE=ffroliva GFLOW_CLI_E2E_PROJECT=<project> GFLOW_CLI_E2E_CHARACTER=Kael
uv run pytest -m e2e_image tests/e2e/test_migrated_image_character_mention_bdd.py
tests/e2e/test_t2i_batch_project_e2e.py::test_multi_prompt_t2i_titles_its_new_project_with_project_name`
→ **5 passed in 246 s**.

## 5-layer ledger

| Layer | Character e2e (4 scenarios) | `t2i --project-name` e2e |
|---|---|---|
| File count | ≥ 1 image in `--out` (CLI) / `result["files"]` (MCP), asserted; the refusal writes none, asserted | 2 prompts, a saved image each, asserted |
| Magic bytes | not asserted; size > 10 kB asserted | not asserted; size > 10 kB asserted |
| Dimensions | not asserted | not asserted |
| structlog | `migrated.character_entities_attached` carries one non-empty entity id; `migrated.image_submit_guarded` `outcome=passed`, `(body_media, body_characters)` = `(0, 1)` (t2i, MCP) / `(1, 1)` (i2i), asserted | CLI exit 0, asserted |
| User-confirmable artifact | the guard reads the actual `ogiZ0b` body Flow received: exactly the requested references and nothing else | catalog holds exactly one project with the given title |

## Observed, not changed

- **`gflow character create` / `character list` fail on this host.** Both use labs routes
  (`createEntity`, `projectInitialData`) that now answer 404 "Flow RPCs have been
  deprecated". The e2e therefore used a character created earlier (Kael). This is the gap
  #723's by-name fallback exists for. Tracked under #639.
- **A video `@Name` on this host exits 29, not 36.** Run on the release tree:
  `gflow video t2v "@Kael walks through a quiet library" --project <project>` →
  `MentionIndexUnavailableError` (exit 29), "the character source is unavailable",
  before any browser submit, so no credits were spent. The video path still fails closed
  on an unreadable catalog; only images fall back to a by-name character.
- **First-word names only without the catalog.** A multi-word character name still needs
  the catalog, which this host cannot read today.

## Not verified

- **Accounts served labs.** Blocker: every profile we hold is redirected to
  flow.google.com. The labs arm's new refusal (a by-name character with no id → exit 29) is
  unit-tested only (`test_by_name_character_without_an_id_is_refused`).
- **Video characters on flow.google.com.** Not in this release: `--reference-entity` exits 36, a video `@Name` exits 29 (#723
  stays open).

## Pre-tag gates

| Gate | Result |
|---|---|
| `/gflow:changelog` | `[Unreleased]` → `[0.85.0] — 2026-10-14`: Added (#723), Fixed (#975) |
| `/gflow:check` | on the release tree (`develop@26b65f48`): hygiene, doc links, PII, mirror, council memory, ruff, format, pyright 0; pytest 4964 passed, 24 skipped, coverage 93% |
| Council review | #979: 10-dimension council YELLOW at `5f82efc5`; every must-fix fixed in `e87c9de7` and `59bb751b`, then CI green on the head |
| SonarCloud | #979 was a fork PR (skipped); `develop` gate after its merge (`26b65f48`, CI success) passed: new coverage 91.9%, 0 new issues, hotspots 100% reviewed |
| `/gflow:doc-review` | mechanical: doc links (220 files), PII, mirror in sync, CHANGELOG footer, 7 version sites, release artifacts green; older ledgers reachable only through INDEX's previous-chain (pre-existing). Council: Auditor 1 **RED** (the gflow-cli skill and `llms.txt` still said image `@Name` exits 36; the exit 29/32 rows and REFERENCE_STRATEGIES lacked the new character remediations; `--project-name` was missing from the USAGE t2i options), Auditor 2 YELLOW (CONFIGURATION/KNOWN_ISSUES/MCP did not say an id needs a name), Auditor 3 YELLOW (a video `@Name` exits 29, not 36, confirmed live; `character create` now exits 7; AGENTS.md capability list). All findings fixed in the release-prep commit; reports in `tmp-council/` (local-only) |

## Post-tag evidence

| Check | Result |
|---|---|
| Signed tag | `v0.85.0` pushed; SSH signature present (`git cat-file -p v0.85.0` carries `BEGIN SSH SIGNATURE`) |
| Release workflow | run 38582576870: success (`build-and-publish`, `mcp-registry / publish`) |
| PyPI | `gflow-cli` 0.85.0 is the latest version on pypi.org (wheel and sdist) |
| GitHub Release | `v0.85.0` published 2026-10-14T14:41:07Z, not a prerelease |
| Release PR | #980 merged into `main` (merge commit `31b6e139`), SonarCloud gate passed |
| Back-merge | `main` → `develop` as `451a8c23`; `main` is not ahead of `develop` |
