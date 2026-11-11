# Live verification — v0.88.0

> Evidence for this release, gathered on 2026-10-22 (PRs #992, #1032, #1042, #1043, #1044,
> #1045). Every row below was a run someone watched, not an inference. Where a check could not
> be run, the blocker is named.

## Environment

| | |
|---|---|
| Profiles | `ffroliva` and `denon82` (real-browser Chrome strategy), `ci-probe` for the log check, `probe-1026` (bundled Chromium) for the internal login |
| Host Flow served | `flow.google.com`, classic composer |
| Transport | `ui_automation` → migrated composer / migrated upscale |
| OS | Windows 11 (Google Chrome installed) |
| Tree | release branch `chore/release-v0.88.0`, cut from `develop@f81f31db` |
| Veo credits spent | none on the release tree (video submits in the project tests are aborted; video upscale exports are $0) |

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| Browser proxy setting (#1036) | every browser launch; `gflow auth status`, `auth renew`, `image t2i` | ✅ `test_browser_proxy_e2e.py` 6 of 6 on `denon82` through a local logging CONNECT proxy: t2i, auth status and auth renew go through it; a credentialed proxy is refused at startup (exit 11); a dead proxy fails fast naming the setting (exit 11) | quota |
| Slow-link project create (#1037) | `gflow project create`, any run without `--project`, CLI and MCP | ✅ `test_project_create_slow_link_e2e.py` 3 of 3 on `ffroliva` with only Flow's create reply held back: a 40 s reply succeeds with one project; a reply past the ceiling is recovered from the navigation; no reply and no navigation ends exit 7, not retryable (and Flow did make one project). `test_project_create_e2e.py` 5 of 5 | $0 |
| A write whose reply Chrome lost is read back (#992, #1009) | upload, create, rename on flow.google.com | ✅ `test_migrated_rpc_readback_bdd.py` 1 of 1 on `ffroliva`: create, its rename and an upload recover by an independent reload of the project | $0 |
| A failed image download keeps the generation (#1035) | `gflow image t2i`, MCP `gflow_generate_image` | ✅ `test_image_download_failure_records_bdd.py` 2 of 2 on `ffroliva`: into an unwritable directory, the media id is catalogued with no local copy and exactly one FAILED operation carries the project id; the MCP reply carries both ids | quota |
| Commands print only their result (#1041) | every command | ✅ `gflow credits user --profile ci-probe` on the release tree: stdout 3 lines, no gflow log lines on stderr (4 one-time `SyntaxWarning` lines from the third-party `wmi` package on the venv's first import, gone on the next run); `GFLOW_CLI_LOG_LEVEL=INFO` restored 9 lines on the PR | $0 |
| `auth login --browser internal` (#1026) | `gflow auth login --browser internal` | ✅ on the PR branch, Windows: the maintainer signed in by hand on a fresh bundled-Chromium profile; the login ended on its own and `auth status` reported the session verified | $0 |
| Regression: credits and image upscale share the changed `_rpc_reply` / capture code | `gflow credits`, MCP credits, image upscale | ✅ `test_credits_on_flow_bdd.py` 1/1 (`ffroliva`), `test_credits_mcp_e2e.py` 3/3 (`denon82`), `test_migrated_upscale_e2e.py` image 2/2; the two video-export tests skipped (opt-in; that code is unchanged since v0.87.1, where they passed) | $0 |

## Not verified

- **A network that only reaches Google through a proxy (#1036)**: blocker, no such network here. The proxy e2e runs through a local logging proxy, which proves the browser's traffic goes through it, not that the reporter's network works. Asked the reporter to test v0.88.0.
- **A proxy that needs a password (#1036)**: refused at startup in this release. Measured: through a local Basic-auth proxy, `auth status` verified but Flow itself did not load within 45 s in either engine; `test_browser_proxy_e2e.py` re-measures it.
- **`--browser internal` login on macOS (#1026)**: blocker, no macOS host. The saved-cookie read is expected to fail there (Playwright's mock keychain vs `browser_cookie3`).
- **The real proxied throughput link of #1037**: blocker, no such network; the slow link is reproduced by holding back only Flow's create reply.
- **i2i, `image batch` and the manifest path for #1035**: covered offline only (one failure-path test each); CLI t2i and the MCP worker ran live.
- **Large projects (virtualised grid) for the #992 readback**: blocker, no account with such a project here.

## Pre-tag gates

- `/gflow:check` on the release tree: hygiene, doc links, website PII, website mirror, council
  memory, ruff, ruff format, pyright 0 errors; offline suite 5348 passed / 29 skipped on the
  bumped tree. A first run had one failure, `tests/data/test_packaging.py` (the sdist build
  failed while the release e2e was writing into the same worktree); it passes alone and on
  the re-run with nothing else writing.
- `/gflow:doc-review`:
  _Council verdict: YELLOW across all 3 auditors. No Tier 1 findings, no contradictions, no
  fictional claims. Tier 2 fixed in the release-prep commit: the USAGE doctor table (eleven
  checks, `env.browser_proxy` row), the agent skill's error table (proxy, exit 7, quieter
  output), a README pointer for proxy users, exit 7 on the USAGE i2v upload surface, "macOS
  not measured" for #1026 in PROJECT_STATUS, and the MCP generate-tool docstrings naming
  `flow_media_id`/`flow_project_id` on a failed reply. Tier 3 deferred: an INDEX routing
  question for proxies, a KNOWN_ISSUES entry for the refused credentialed proxy, a `null`
  `flow_project_id` note in MCP.md. Council reports at `tmp/council/0{1,2,3}-*.md`
  (local-only)._
