# None of our classifiable profiles is in the agent-only composer cohort

**Date:** 2026-10-17 · **Issues:** #824, #799 · **Cost:** $0 (navigation + DOM reads; no clicks)
**Probe:** [`scripts/dev/spike_agent_only_cohort_profiles.py`](../../../scripts/dev/spike_agent_only_cohort_profiles.py)
**Captures:** `scripts/dev/_spike_out/agent_only_cohort_profiles_20261017_*.json`, `run_b1.log`, `run_b2.log` (gitignored)

## Question

#824 can be live-verified only on a profile Google has put on the agent-only composer
(develop's `MigratedComposer._is_agent_only_composer`: `.settings-trigger-button` in the DOM
but hidden, and no `button.agent-mode-chip` at all). Which of our saved profiles is one?

## Method

Per profile: open `labs.google/fx/tools/flow`, record the host served, follow the first
`a[href*='/project/']` the page renders (no project created), wait for the trigger to be
*attached*, then read trigger visibility, chip presence/pressed state, and call develop's own
`_is_agent_only_composer(page, trigger)`. A batchexecute route aborted any submit rpc.

## Pre-registered reading

≥1 `agent_only` → #824 can be live-verified on that profile. 0 → named external blocker
"no agent-only account held". A profile not classified (locked, no project link) settles
nothing about that profile.

## Observations

| Profile | Host served | Landing | Trigger visible | Chip (any / pressed) | develop probe | Composer |
|---|---|---|---|---|---|---|
| denon82 | flow.google.com | `/` → project | yes | 1 / 0 | false | classic |
| ffroliva | flow.google.com | `/` → project | yes | 1 / 0 | false | classic |
| ci-probe | flow.google.com | `/` → project | yes | 1 / 0 | false | classic |
| flavio.oliva | flow.google.com | `/about` | — | — | — | unclassified (no project link) |
| test_acc | flow.google.com | `/about` | — | — | — | unclassified (no project link) |
| promo-denon82 | flow.google.com | `/about` | — | — | — | unclassified (no project link) |
| gflowclireview | flow.google.com | `/unavailable` | — | — | — | unclassified (no project link) |

No profile was locked. `/about` is **not** proof of a logged-out session (the hop is
client-side; see memory `about-render-is-not-logged-out`), so those three are unclassified,
not "logged out". `/unavailable` is Flow's no-access landing for that account.

## Verdict

**0 agent_only among the 3 classifiable profiles** → named external blocker for #824:
**"no agent-only account held"**. All three classifiable profiles show the classic
composer with an un-pressed agent-mode chip, the healthy state the develop probe expects.

## Not measured

- The four unclassified profiles: an `/about` or `/unavailable` landing never reached an
  editor, so their composer is unknown. Re-login (`gflow auth login --profile <name>
  --browser chrome`) and re-run to classify them.
- Cohort assignment can change server-side; this is a 2026-10-17 snapshot, one run each.
