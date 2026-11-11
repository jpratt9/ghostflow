# Live verification — v0.89.0

> Evidence for this release, gathered on 2026-10-23 (PRs #1047–#1069). Every row below was a
> run someone watched, not an inference. Where a check could not be run, the blocker is named.

## Environment

| | |
|---|---|
| Profiles | `ffroliva` and `denon82` (real-browser Chrome strategy), `ci-probe` for the held-profile checks |
| Host Flow served | `flow.google.com`, classic composer |
| Transport | `ui_automation` → migrated composer / migrated upscale / migrated extend |
| OS | Windows 11 (Google Chrome installed) |
| Tree | release branch `chore/release-v0.89.0`, cut from `develop@f56f94ec` |
| Veo credits spent | none (video submits in the frame test are aborted before they leave the page; video exports are $0). Image daily quota: about 6 images |

## Release e2e on the release tree

One batch, `-m e2e` on `ffroliva`, project `c59b5464-…`: **20 cases, 19 passed first time, 1 passed
on re-run** (`test_e2e_mcp_image_generates_into_the_pinned_project` first hit Flow's "ogiZ0b submit
reply body unreadable", the #1010 case; re-run alone it passed in 30 s).

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| `gflow models` shows Flow's names; `nano2.1` alias (#1038) | `gflow models`, `--model`, MCP `model` | ✅ `test_e2e_mcp_t2i_accepts_the_nano2_1_alias` 1/1 (the picker chose the "2.1" entry for `NARWHAL`); CLI `image t2i --model nano2.1 --json` → `status: ok` on the PR branch | 1 image |
| MCP `gflow_list_models` (#883) | MCP | ✅ in CI on every PR: the live-serve smoke calls it over Streamable HTTP against a spawned `gflow serve` and compares it with `build_catalog()` | $0 |
| `GFLOW_CLI_PROJECT` default project (#1039) | `image t2i/i2i`, `video t2v/i2v/r2v`, `gflow run`, MCP generate tools | ✅ `test_default_project_e2e.py` 2/2 on the release tree: CLI t2i (stderr names the pin, every catalogued image in the pinned project) and the MCP image tool | 2 images |
| A `--project` Flow will not open → exit 11 (#974, #1053) | generation, `gflow run`, image/video upscale, video extend, MCP | ✅ `test_missing_project_e2e.py` 2/2 (CLI exit 11 in 15.8 s, was exit 23 after 40 s on develop) and `test_missing_project_upscale_extend_e2e.py` 4/4 | $0 |
| A profile open in your own Chrome → exit 11 (#984, #1059) | credits, generation, `auth login` | ✅ on the PR branches, `ci-probe` held by a plain `chrome.exe --user-data-dir=<profile>` (stopped by PID afterwards): `credits user` exit 11 (was 1), MCP `profile-locked`, `auth login --browser internal` exit 11 (was 1), `--browser chrome` exit 11 (was 8) | $0 |
| Cloud storage + local-file options refused before billing (#1008) | `video -o`, `video chain`, `movie run --stitch`, MCP `output` | offline only: the refusal runs before any browser and tests show no client is constructed. No bucket is configured here | $0 |
| Billed downloads not `retryable` (#941 part 1) | `--json`, MCP, worker | offline only: needs a CDN reset on every attempt, which cannot be produced on demand | $0 |
| Diagnostics privacy (#890, #1062) | migrated submit gate, debug screenshots, recovery errors | ✅ CLI `image t2i` through the changed submit-gate JS on the PR branch: `status: ok`, no `ui-failures/` directory. Real-Chromium unit test shows the email no longer reaches the error text | 1 image |
| Warm-client upscale after an image run (#914) | `FlowApiClient` reuse | ✅ `test_warm_client_upscale_e2e.py` 1/1 on the release tree (62 s); on develop the same sequence failed with `RecaptchaError` | 1 image |
| Pre-submit gate on the real editor (#892) | migrated image submit | ✅ `test_migrated_presubmit_gate_e2e.py` 1/1 on the release tree and on `denon82` (PR); cookie bar absent both times, so the dismissal branch itself was not exercised | $0 |
| Standalone launch window position (#927) | `UiAutomationTransport.setup(page=None)` | ✅ `test_standalone_window_position_e2e.py` 2/2: default lands at `-21845,-21845` (Windows' clamp), `0,0` at `0,0` | $0 |
| Video export e2e skips on a capability refusal (#967) | test | ✅ 1080p and 270p GIF 2/2 on the release tree (`ffroliva` offers them); on `denon82` the 1080p arm skipped after 3 clips were refused | $0 |
| Frame binding on flow.google.com (#860, closed) | `video i2v` local frames | ✅ `test_e2e_end_frame_binds_the_second_chip_and_submits_interpolation` 1/1 on the release tree (submit aborted, body asserted) | $0 |
| `image batch` manifest errors exit 11 (#935) | `gflow image batch` | offline only: the refusal happens before any browser (tests assert no client); exit-code plumbing | $0 |
| Media id checked before it becomes a filename (#1004) | clip saver, `data download` recovery | offline only: hardening, an unsafe id never comes from Flow's UUID-shaped replies; unit tests on both sites | $0 |
| Exit 22 title is media-neutral (#966) | `video upscale` / `image upscale` errors | offline only: error text; no Flow surface touched | $0 |
| A rejected upload writes an incident bundle (#770) | uploads on flow.google.com | offline only: needs Flow to raise an unexpected dialog during upload, which cannot be produced on demand | $0 |
| Regression: session checks | `auth status` | ✅ `test_auth_verification_e2e.py` 4/4 on the release tree | $0 |

## Not verified

- **#1008 with a real `s3://`/`gs://` bucket**: blocker, no bucket configured here; the refusal is
  pre-browser and covered offline.
- **#941's exhausted-download path**: blocker, a connection reset on all three attempts cannot be
  produced on demand against live Flow.
- **#892's dismissal branch**: Flow showed no cookie bar on either account today; the test asserts
  the invariant, so a run where the bar appears covers it unchanged.
- **#984/#1059 on macOS, and a read-only profile outside Windows**: blocker, no macOS host.
- **#770 live**: blocker, the exit-27 dialog cannot be raised on demand; the capture trigger is unit-tested.
- **#1062's labs count-panel path**: blocker, labs.google 308s to flow.google.com for every account
  we hold.

## Observed, not changed

- Flow's "ogiZ0b submit reply body unreadable" (#1010) hit 3 of about 9 image submits on
  `ffroliva` today. gflow reports it correctly (exit 9, not retryable, "check the project before
  re-running"); the rate is Flow-side.
- An upscale immediately after generating can miss the brand-new tile (exit 23): filed as #1067.
