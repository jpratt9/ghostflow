# Live verification — v0.80.0

> Evidence for the user-facing changes in this release, run against real Flow on
> 2026-09-29. Where a check could not be run, the blocker is named. Each row is a run
> that someone watched, not an inference.

## Environment

| | |
|---|---|
| Profile | `ffroliva` (real-browser Chrome strategy) |
| Host Flow served | `flow.google.com` |
| Transport | `ui_automation` → migrated composer |
| Date | 2026-09-29 |
| Veo credits spent | **0**: every video check stopped before the credit-spending submit |

## Summary

| Change | Surface | Verified live? | Cost |
|---|---|---|---|
| `--resolution 360p\|720p` (#787) | CLI transport + MCP twin | ✅ Yes (stopped before submit) | $0 |
| `--model nano2-lite` (#787) | CLI transport + MCP | ✅ e2e, 2 passed | 2 images (daily quota) |
| Unported image form refused by name (#891) | CLI `gflow run`, library, MCP | ✅ e2e, 3 passed, plus before/after | 2 images |
| Lost transfer recorded as generated (#896) | Data layer | ✅ e2e_data, 2 passed; the failure path is offline-only (below) | $0 |
| Refusal read from the wire (#906/#873, #909) | image submit | ✅ at merge (PR #909): e2e on a probe profile | — |
| `auth login` stops on the `/about` re-check (#902, #904) | auth | ⚠️ Healthy arm only; the `/about` arm is **blocked** (below) | $0 |
| CVE locks: oauthlib 4.0.0, pyjwt 2.15.1 (#917) | none (transitive) | n/a: no Flow surface; imports + pip-audit clean | — |
| pytest-xdist (#905) | tests only | n/a | — |

## `--resolution` — #787

The existing e2e `test_e2e_t2v_selects_a_resolution_on_omni_flash` bills one clip. Instead,
the real settings pane was driven on `omni_flash` and the one credit-spending call,
`MigratedComposer._click(named=SUBMIT_BUTTON)`, was replaced with a raise. That proves the
selection. It does not prove the rendered resolution: that needs a paid run. The offline
suite pins the request wiring.

| Arm | Outcome | structlog |
|---|---|---|
| CLI transport, `360p` | stopped before submit | `migrated.resolution_selected resolution=360p`, then `migrated.settings_applied model=omni_flash resolution=360p` |
| CLI transport, `720p` | stopped before submit | `migrated.resolution_selected resolution=720p`, then `settings_applied … 720p` |
| **MCP twin**: `gflow_generate_video(model="omni", resolution="360p")` through the queue and in-process worker | task `failed` (the submit was refused on purpose); `params.resolution == "360p"` | `migrated.resolution_selected resolution=360p`, then `settings_applied … 360p` |

`migrated.submit_clicked` was absent from every arm, so no credit was spent.

## `--model nano2-lite` — #787

`pytest tests/e2e/test_migrated_host_e2e.py -m e2e -k nano2_lite` → **2 passed in 49.9 s**.
The picker bound the Lite row, not "Nano Banana 2", and the images landed. The model tier
cannot be read back from the image (see the 2026-09-11 nano2-lite spike), so this proves the
binding and delivery, not the tier.

## Unported image form refused by name — #891

**Baseline before the change** (`develop` 342f39df, $0, `gflow image t2i --model imagen4`):
both arms exited 36. The refusal came from the client's pre-mint guard
(`ui_driver.migrated_host_bail at=mint_recaptcha_token`), which is the step this release
deletes, so the fix had to be shown to keep exit 36.

| Arm | Before | After |
|---|---|---|
| `t2i --model imagen4 --project <id>` | exit 36, raised at the mint | exit 36, raised by the composer: *"the IMAGEN_3_5 model is not ported yet"* |
| `t2i --model imagen4` (no project) | exit 36, raised at the mint | exit 36, raised by the composer, same message |
| **`gflow run --config` `[nano2, imagen4]`** | **exit 1**: prompt 2 `RecaptchaError`, traceback, results table lost | **exit 36**: prompt 2 refused by name, "1/2 succeeded" |

e2e `tests/e2e/test_migrated_host_e2e.py -k "unported or warm_client"` → **3 passed in 53.9 s**:
- fresh client refused ($0)
- warm client after a successful image (the #891 repro)
- MCP twin ($0)

Each test spies on `FlowApiClient._mint_recaptcha_token` and asserts zero calls.

## Lost transfer recorded as generated — #896

`pytest tests/e2e/test_data_download_e2e.py -m e2e_data` → **2 passed in 22.5 s** ($0). This
exercises the recovery path the new remediation points users to.

The changed code path itself, a signed-media connection dropping on every retry after Flow
reports DONE, **cannot be provoked on a healthy CDN**. It is covered offline:
- the transport raises `MediaDownloadError` carrying the `media_id`;
- the recorder marks that asset `MEDIA_GENERATION_STATUS_SUCCESSFUL`;
- `data list videos --json` shows `status`.

## Blockers (named, not waived)

- **`/about` identity re-check arm (#902):** no profile here is currently in the re-check
  state, and the state cannot be manufactured. The healthy arm passed at merge (PR #904).
- **Accounts served labs:** `labs.google/fx/tools/flow` answers 308 on every profile here
  (2026-09-14 survey), so #891's labs arm is correct by construction but unobserved.
- **Rendered resolution:** proving the output is 360p/720p needs a billed clip. Selection
  is proven; rendering is not.

## Pre-tag gates

- **Council reviews** on each merged PR (#912, #916): YELLOW, then every finding fixed or tracked (#898), CI 16/16 including SonarCloud. #917 (CVE locks): CI 16/16.
- **`/gflow:doc-review`**: mechanical sections PASS (version sites, links, website mirror, release artifacts).
  - Council: Completeness **RED → fixed**. MCP docs did not name `nano2-lite` (tool description, docstring, `MCP.md`). Also fixed: the `--resolution` refusal behaviour (exit 11, $0) in USAGE and MCP, the `nano2-lite` caveats, the scope lists, the `gflow-cli` skill, and two stale `llms.txt` claims.
  - Council: Cross-reference **YELLOW → fixed**. The KNOWN_ISSUES #891/#673 wording, the milestone row, and CHANGELOG formatting and issue refs.
  - Council: Drift **YELLOW → fixed**. `nano2-lite` in agent docs, and the AGENTS.md module list.
  - No fictional claims were found.
- **`/gflow:check`**: see the release PR.

## Post-tag evidence

_Filled after the tag: PyPI publish, GitHub Release, back-merge._
