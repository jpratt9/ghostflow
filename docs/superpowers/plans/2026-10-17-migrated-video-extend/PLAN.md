# `gflow video extend` on flow.google.com Implementation Plan

> **For agentic workers:** Run `/gflow:status --feature migrated-video-extend` to find the
> next unchecked task. One task at a time; `/gflow:check` before every commit.

**Goal:** a single-segment `gflow video extend` runs on accounts Flow serves
flow.google.com, by driving Flow's own extend UI (design B), with #882's design A removed.

**Architecture:** new `api/transports/migrated_extend.py` drives the clip editor
(`/project/<pid>/edit/<media>`), reads media → workflow + kind from the passive `Zzl0ze`
reply, guards `rqZuUc` / `fZytfe` at the route, and reuses `MigratedComposer.submit_and_observe`
(parametrised by `submit_rpcs`, `submit_selector`, `request_check`) and the composer's
signed-URL fetch (renamed public `fetch_mp4`). `FlowApiClient.extend_video_migrated` is the
thin host-checked entry; `cli_video._run_extend` picks the arm before any browser opens.
The labs arm and `extend_chain` are develop's, unchanged.

**Predict verdict:** CAUTION — 7/10 ([PREDICT.md](PREDICT.md)); scenarios in [SCENARIO.md](SCENARIO.md).

**Risk register:**

| Severity | Risk | Mitigation (PREDICT #) |
|---|---|---|
| Critical | wrong clip billed | Zzl0ze guard (2) + route guard (3) |
| Critical | gflow mints on flow.google.com | design A deleted, develop's mint guard restored (6) |
| High | an unported form silently runs | refusal matrix before the browser (1) |
| High | 2xx with no record reported as success | generation_record raises; echo refused (5) |
| Medium | plan screen quotes a price this host never gave | cost line reworded (7) |

---

## Task 1 — $0 spike: editor URL, tile identity, record kind  ✅

- [x] `scripts/dev/spike_migrated_extend_ui_path.py --direct-editor` (+ tile and record dumps)
- [x] B1 direct goto reaches the extend-capable editor → replaces the grid walk
- [x] B2 `flow-video-tile` carries no media id
- [x] B3 `Zzl0ze` kind: video = media-info list at `rec[7][0]`; image = `image/*` mime at `rec[7][1][6]`
- [x] B4 the editor URL fires `Zzl0ze` itself
- [x] findings appended to the 2026-10-17 spike doc; no scene created

## Task 2 — delete design A (mitigation 6)

**Files:** `api/client.py`, `api/video_extend.py`, `api/extend_chain.py`, their tests,
`tests/api/test_client_migrated_mint.py`, the CLI fake.

- [x] restore develop's `client.py`, `video_extend.py`, `extend_chain.py` (mint guard byte-identical)
- [x] restore develop's `test_client_extend.py`, `test_video_extend.py`, `test_client_migrated_mint.py`
- [x] CLI calls `create_scene` again; drop `create_scene_for_extend` from the fake
- [x] keep #882's host-independent CLI fixes and their tests (JSON `video_result`, no plan
      preamble under `--json`, single-segment direct download)

## Task 3 — `migrated_extend.py` pure helpers (red → green)

**Tests:** `tests/api/transports/test_migrated_extend.py`
- [x] `unported_extend_form`: segments > 1, scene, seed → noun; single → None (mitigation 1)
- [x] `source_record`: Zzl0ze payload → (workflow id, kind) / None (mitigation 2)
- [x] `extend_request_problem`: rqZuUc without media, fZytfe slot1 ≠ workflow, aspect
      mismatch (FlowHostMigratedError), unreadable body; error text never carries the token (mitigation 3)

## Task 4 — composer parametrisation (mitigation 5)

- [x] `submit_and_observe(submit_rpcs=, submit_selector=, request_check=)`; defaults keep every caller byte-identical
- [x] `_fetch_mp4` → `fetch_mp4` (rename, update `test_signed_media_retry.py`)
- [x] test: a `request_check` error raises before the reply; `submit_rpcs` routes fZytfe replies

## Task 5 — `run_extend` driver (mitigations 2–5)

- [x] goto editor URL, await Zzl0ze record, refuse absent (exit 11) / image (exit 11)
- [x] confirm `/project/<pid>/edit/<media>` before opening the menu
- [x] add-clip → Extend → prompt; route guard on rqZuUc/fZytfe; observe; refuse an echo
- [x] listeners + route removed in `finally`

## Task 6 — client entry + CLI arm (mitigations 1, 7)

- [x] `FlowApiClient.extend_video_migrated` (kill switch → exit 36; one checkout)
- [x] `_run_extend`: route chosen before the browser; unported form on the migrated route → exit 36
- [x] `--aspect` default None (labs arm keeps 9:16); plan screen makes no price claim on migrated
- [x] CLI tests for the refusal matrix, the migrated dispatch and `--json`

## Task 7 — MCP surface mirror

- [x] no new surface: `video extend` stays in `_MCP_EXEMPT`; the reason text is still true
      (billed, not worker-enqueued, consent prompt has no MCP equivalent). Recorded in SCENARIO #23.

## Task 8 — e2e (mitigation 9)

- [x] `tests/e2e/test_video_extend_migrated_e2e.py`: `e2e_auth` route-abort contract + unknown-media refusal (run, $0)
- [x] `e2e_video` single paid segment (written, NOT run — owner consent required)

## Task 9 — docs (mitigation 8)

- [x] CHANGELOG [Unreleased] (credit @stgmt), USAGE extend section, KNOWN_ISSUES, `--help`,
      llms.txt line 3, skills/gflow-cli/SKILL.md, regenerate website docs + plugin skills

## Task 10 — gates

- [x] the AGENTS.md gate list, all green; MCP parity tests (5062 passed, 24 skipped)

---

## Definition of done

- [x] all tasks checked; gates green
- [x] the $0 `e2e_auth` test run and its result recorded
- [x] the paid `e2e_video` run left for the owner, with the exact command
