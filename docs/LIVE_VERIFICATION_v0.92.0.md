# Live verification — v0.92.0

> Evidence for this release, gathered on 2026-10-29 (PR #1117 for #1114, PR #1118 for
> GHSA-hqfj-4jww-76f2). Every row below was a run someone watched, not an inference. Where
> a check could not be run, the reason is named.

## Environment

| | |
|---|---|
| Profile | `ffroliva` (real-browser Chrome strategy) |
| Host Flow served | `flow.google.com` |
| Transport | `ui_automation` → migrated composer; MCP tool functions called in-process |
| OS | Windows 11 (Google Chrome installed); Linux via Docker (`python:3.12-slim`) for #1114 |
| Tree | `develop@204b8b61` (#1118 merged); the release commit adds only MCP tool docstrings and a recovery hint on the `Invalid Output` message (doc-review findings), re-tested offline below |
| Veo credits spent | 0. Image daily quota: about 4 images across the PR and release runs |

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| MCP `output` confined to the output dir (GHSA-hqfj-4jww-76f2) | `gflow_generate_image` / `gflow_generate_video` | ✅ On `develop` before the fix, a relative `output` that climbed out of the output dir wrote the generated image outside it (the file was deleted after the run). On `develop@204b8b61`: the same call returns 400 `Invalid Output` and nothing is written outside; an `output` inside the output dir lands there (JPEG, 1024×1024, magic `ffd8ff`) | 2 images |
| MCP `profile` must be a plain name (same advisory, found in review) | every tool that opens a profile, e.g. `gflow_get_credits` | ✅ Before the fix, a path-shaped `profile` naming an existing directory outside gflow's home made Chrome fill it with a user-data-dir (`Default/`, `Local State`, …) and gflow's ACL marker. On `develop@204b8b61`: 400 `Invalid Profile`, no browser starts, the directory stays empty | $0 |
| MCP `out_dir` confined (same advisory) | `gflow_download_media`, `gflow_upscale_image`, `gflow_upscale_video` | ✅ `test_mcp_upscale_image_2k_e2e` on `ffroliva` with `out_dir` inside the output dir: passed (upscaled file larger than its source). The refusals happen before any Flow call and are covered by `tests/mcp/test_output_confinement.py` | $0 |
| Existing e2e kept meaningful under the new boundary | `test_image_download_failure_records_bdd.py` (#1035) | ✅ CLI + MCP scenarios, 2 passed: the MCP arm still reaches the unwritable directory it tests (exit-11 envelope) instead of being refused at the boundary | 2 images |
| A `-o` video across filesystems (#1114) | `video` `-o` (CLI) and the MCP worker's `output_file` | ✅ on real mounts, spike [`2026-10-29-cross-device-relocate`](superpowers/spikes/2026-10-29-cross-device-relocate.md): Linux tmpfs → disk and Windows `C:` → SMB share. The pre-fix `Path.replace` raised errno 18 on both; the CLI relocation and `FlowWorker.process_task` landed the clip and removed the source; overwrite kept working. The generation client was a stub ($0) | $0 |

## Not verified

- **#1114 with a real Veo generation onto a second volume.** The relocation runs after the
  download, on bytes already on disk; the spike ran the production relocation code on real
  mounts, but not after a real billed generation. Not run to avoid spending Veo credits on
  a path whose Flow side the change does not touch.

## Pre-tag gates

- `926498c6` (content-identical to `develop@204b8b61`): the six `scripts/ci` gates, ruff,
  format and `pyright src` green; full offline suite `-n 8`: **5603 passed, 29 skipped**.
- Release tree (docstring + message changes on top): `tests/mcp` **324 passed**; the full Impeccable Routine re-run green, offline suite **5603 passed, 29 skipped**. Doc-review council: completeness RED (MCP `output` undocumented in the generate tools' Args), cross-reference GREEN, drift YELLOW (profile rule overstated); all findings fixed in the release commit.
- PR #1118: all 17 checks green, including SonarCloud and the test matrix on 3.11–3.13
  (Ubuntu runs the symlink arm of the link-escape test; Windows ran the junction arm locally).

## Post-tag evidence

Filled after the tag push: the `Release` workflow run, the PyPI upload of `gflow-cli==0.92.0`,
and publication of GHSA-hqfj-4jww-76f2 with patched version `0.92.0`.
