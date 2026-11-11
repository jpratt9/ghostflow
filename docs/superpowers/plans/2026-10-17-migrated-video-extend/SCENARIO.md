# Scenario: `gflow video extend` on flow.google.com (design B, #882 takeover)

Inputs: [PREDICT.md](PREDICT.md) (CAUTION, nine mitigations) and the
[2026-10-17 spike](../../spikes/2026-10-17-migrated-extend-ui-path.md) (rounds 1 and 2).

## Coverage map

Active: D1 (session on the editor URL), D2 (the page mints; gflow must never mint here),
D3 (structural anchors only), D5 (one Page checkout, listeners and route removed in
`finally`), D7 (exit 36 / 11 / WireFormatError), D9 (a 2xx `fZytfe` with no record, the
signed-URL download), D10 (headless runs the same driver as t2v), D11 (refusal matrix),
D12 (no request body in any log or error), D13 (MCP twin — exempt, recorded).

Skipped: D4 (single segment only — no chain, no resume on this host yet), D6 (the
started-row write is the labs path's, reused unchanged), D8 (the output path is the
existing `_write_target`).

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test category |
|---|---|---|---|---|---|
| 1 | D11 | `-n 2` / two prompts with the migrated route chosen | Critical | exit 36 "not ported to flow.google.com yet", no browser opened | Unit (CLI) |
| 2 | D11 | `--scene` / `--resume-from` on the migrated route | Critical | exit 36 before the browser opens | Unit (CLI) |
| 3 | D11 | `--seed` on the migrated route | High | exit 36 before the browser opens | Unit (CLI) |
| 4 | D11 | explicit `--aspect 9:16` on a 16:9 source | Critical | the `fZytfe` request is aborted at the route (page aspect index ≠ requested), exit 36; no credit spent; the free scene `rqZuUc` created is named in the log | Unit + E2E `e2e_auth` |
| 5 | D11 | no `--aspect` on the migrated route | High | the page's own aspect (the source clip's) is used; no refusal | Unit |
| 6 | D7 | MEDIA_ID not in `--project` (absent from `Zzl0ze`) | Critical | exit 11 naming `--project`, before any click | Unit + E2E `e2e_auth` |
| 7 | D7 | MEDIA_ID is an image | Critical | exit 11 "is an image; extend continues a video", before any click | Unit |
| 8 | D9 | `Zzl0ze` never answers within the budget | High | `TransportTimeoutError` (exit 9) naming the missing read, before any click — a transport fact, not a user error | Unit |
| 9 | D2 | `fZytfe` slot 1 ≠ the source's workflow id | Critical | aborted at the route, `WireFormatError`, nothing billed | Unit + E2E `e2e_auth` |
| 10 | D2 | `rqZuUc` does not carry MEDIA_ID | Critical | aborted at the route (no scene for the wrong clip), `WireFormatError` | Unit |
| 11 | D12 | any guard refusal | Critical | the error text and log carry ids only — never the request body or the page-minted token | Unit |
| 12 | D3 | editor URL redirected (not `/project/<pid>/edit/<media>`) | High | typed error before the extend menu is opened | Unit |
| 13 | D3 | add-clip button / Extend item / prompt box missing | High | `UiSelectorDriftError` (exit 23), nothing submitted | Unit |
| 14 | D9 | `fZytfe` 2xx with a null payload / no record | Critical | `WireFormatError` with the "may already be billed" hint (generation_record's) | Unit |
| 15 | D9 | the reply's record is the SOURCE workflow (an echo) | High | refused as a failure, never reported as the new clip | Unit |
| 16 | D9 | generation finishes with a signed URL | Critical | mp4 downloaded via the composer's signed-URL fetch (ftyp checked) to `-o` or the default output dir | Unit + E2E `e2e_video` |
| 17 | D9 | generation fails (status ≠ done) | High | non-zero exit, JSON `succeeded: false`, the billed media id still reported | Unit |
| 18 | D5 | any exception mid-run | High | request/response listeners and the route removed, Page checked in | Unit |
| 19 | D1 | `GFLOW_CLI_FLOW_HOST=labs.google` | High | labs arm unchanged (develop's behaviour) | Unit |
| 20 | D7 | `GFLOW_CLI_FLOW_HOST=flow.google.com` + unported form | Critical | exit 36 before any browser | Unit |
| 21 | D11 | `--dry-run` on the migrated route | Medium | plan printed with no exact-price claim, nothing opened | Unit (CLI) |
| 22 | D11 | `--json` | High | no human preamble on stdout; `video_result`-shaped payload (#882's fix kept) | Unit (CLI) |
| 23 | D13 | MCP twin | — | `video extend` stays in `_MCP_EXEMPT` (`tests/mcp/test_cli_parity.py`): billed, not worker-enqueued, consent prompt has no MCP equivalent (#481). The migrated arm changes none of those reasons. | Parity test (existing) |

## Must-cover before merge (Critical + High)

1–7, 9–18, 20, 22 as unit tests; 4, 6, 9 and the submit contract as the $0 `e2e_auth`
route-abort test; 16 as the opt-in `e2e_video` test (written, run only with the owner's
consent — it spends credits).

## Deferred

- Chains (`-n > 1`), extending inside an existing scene, `--resume-from`, `--seed`: each
  needs its own measurement (a second segment's source is the scene's tail).
- `Zzl0ze` paging on a large project (unmeasured).
- A portrait source / 4 s and 10 s sources (the page computes the frame window; unmeasured).

## Suggested BDD scenarios (bound from `tests/e2e/test_video_extend_migrated_e2e.py`)

```gherkin
@e2e @e2e_auth
Feature: video extend on flow.google.com — submit contract at $0
  Scenario: the page's own extend submit names the source clip
    Given a profile served flow.google.com and an 8 s clip in a project
    When gflow drives the extend UI and the fZytfe submit is aborted at the route
    Then the rqZuUc request carried the media id
    And fZytfe slot 1 carried the workflow id Zzl0ze maps that media to

  Scenario: a media id not in the project is refused before any click
    When gflow extends a random uuid in that project
    Then it exits 11 and no rqZuUc or fZytfe was sent

@e2e @e2e_video
Feature: video extend on flow.google.com — one paid segment
  Scenario: a single extend downloads an mp4
    When gflow extends the clip once with GFLOW_CLI_E2E_RUN_VIDEO=1
    Then an mp4 (ftyp) of about 8 s is written
```
