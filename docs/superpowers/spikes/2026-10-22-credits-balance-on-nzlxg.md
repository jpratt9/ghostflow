# Credits on flow.google.com: the balance is in the `nzlxg` reply on page load

**Date:** 2026-10-22 · **Cost:** $0 (two navigations, opening and closing the account menu;
nothing typed, selected, submitted, created or deleted); one veo-lite generation (10 credits) for the follow-up · **Issue:** #795
**Script:** [`scripts/dev/spike_credits_balance_carrier.py`](../../../scripts/dev/spike_credits_balance_carrier.py)
**Run:** `python scripts/dev/spike_credits_balance_carrier.py --profile denon82 --runs 2`
**Evidence:** `scripts/dev/_spike_out/spike_credits_balance_carrier_<UTC timestamp>.json` +
one screenshot per run (gitignored; they carry the account email and session values)
**Design:** 1 profile × 2 fresh page loads. The readings were pre-registered in the script
docstring and committed (`4a64768f`) before the first run.

**Question.** Since 2026-10-22 `labs.google/fx/api/auth/session` answers 410 to every account
([spike](2026-10-22-labs-session-oracle-gone.md)), so `gflow credits` cannot get the labs access
token it sends to aisandbox-pa `routes.CREDITS`. Where does the app served from `flow.google.com`
get the balance it shows? The [2026-09-14 spike](2026-09-14-credits-on-migrated-host.md) did not
find it. It never opened the account menu, and it scanned only for credit-shaped *key names*,
which positional `batchexecute` payloads do not have.

## What was observed

| | Run 1 | Run 2 |
|---|---|---|
| Host served | `flow.google.com/` (the app, not `/about`) | same |
| Account menu opened (profile photo `img[src*="googleusercontent"]` in the top bar) | yes | yes |
| Balance shown in the menu | a 2-digit number in `flow-account-panel … span.credits-count` | the same number |
| That number on the wire | **`nzlxg` reply, positions `[0]` and `[5]`**, phase = page load | same, same positions |
| Anywhere else (other replies, `WIZ_global_data` integers) | nowhere | nowhere |
| Daily refresh time in the menu (`span.refresh-daily-label`) vs `nzlxg[6]` | `nzlxg[6][0]`, as local time, equals the menu's HH:MM | equal |
| Page sent a Bearer to aisandbox-pa | **no** | no |

**1. The carrier is `nzlxg`, and the app fetches it on load without any user action.** The
request has no arguments:

```
POST https://flow.google.com/…/data/batchexecute?rpcids=nzlxg
f.req=[[["nzlxg","[]",null,"generic"]]]&at=<XSRF token>
```

The decoded reply has this shape (digits masked):

```
[##, #, #, #, null, ##, [##########, #########]]
  [0]  the balance shown in the menu
  [1..3] small integers, meaning not established (3, 8, 1 on this account)
  [5]  equal to [0] in both runs (see "Not measured")
  [6]  [seconds, nanos]: the next daily refresh. It matches the menu's refresh time and was
       about 15 h ahead at measurement
```

The number matched in 2/2 runs. Opening the menu fired only `LPzVkd` (reply `[]`) and `ve2Lsc`
(a region code). Neither carries the number, so the menu renders the value it got from `nzlxg`
at load. The 2026-09-05 wire spike saw `nzlxg` "burst right after submit", which is consistent
with the app re-reading the balance after a spend. That reading comes from an older capture and
was not re-measured today.

**2. No token for the aisandbox-pa route is obtainable from this page.** In both loads the
page sent no request to aisandbox-pa carrying an `Authorization: Bearer`. The labs-token route
has no replacement token on this host. The balance lives on the host's own `batchexecute`.

**3. DOM anchors are structural.** The custom element `flow-account-panel` (in
`.cdk-overlay-pane.flow-account-panel-overlay`) holds `span.credits-count` and
`span.refresh-daily-label`. The menu text on this profile was Portuguese, so the anchors were
picked by element and class, never by text. The wire value needs no click and is the better
source.

## Follow-up: one paid generation (same day, owner-granted spend)

To separate `[0]` from `[5]`, `nzlxg` was read, then **one** `gflow video t2v --model veo-lite`
(Flow's default length, a fresh project titled `spike-795-credits`) ran and succeeded, and
`nzlxg` was read again. A first attempt with `--duration 4` was refused before submit (exit 11,
no duration control on this account for that model) and spent nothing.

| Reading | `[0]` vs the menu | `[0] - [5]` | `[0]` change since the first read |
|---|---|---|---|
| 17:01 run 1 + run 2 (above) | equal, equal | 0, 0 | baseline, 0 |
| 17:13, before the generation | equal | 0 | 0 |
| 17:14, after the refused `--duration 4` attempt | equal | 0 | 0 (the refusal spent nothing, as it claims) |
| 17:15, after the veo-lite generation | equal | 0 | **-10** |

**Both `[0]` and `[5]` dropped by 10**, which is veo-lite's price, and the menu dropped with them.
They still could not be told apart: they moved together and stayed equal. `[0]` matched the menu
in **5/5** reads, so it is the index to read. What `[5]` means when it differs from `[0]` is still
unmeasured (it may be a different credit bucket on a paid plan). `[1..3]` and `[6]` did not change.

## Readings against the pre-registered table

- "avatar menu shows an integer AND the same integer sits at one rpcid + path in N/N runs"
  → **CARRIER FOUND for this profile**: `nzlxg`, `[0]` (and `[5]`), 2/2.
- "the page never sent a Bearer to aisandbox-pa" → no token from this page state.

## What this means for #795

`gflow credits` can be ported off labs.google by reading `nzlxg` on flow.google.com: wait for
the app's own `rpcids=nzlxg` response after opening the app (no click), parse it with the
existing `batchexecute.parse_frames`, and report `[0]` plus the refresh time from `[6]`. The
aisandbox-pa `routes.CREDITS` call and its labs token have no source on this host.

**This is one account.** It does not show that every account served flow.google.com gets
`nzlxg`, or that `[0]` is the balance on a paid plan. A second account (ideally a paid tier with
a non-zero Veo balance) is needed before the parser can be called general.

## Not measured

- **What `[5]` means when it differs from `[0]`.** A spend moved both by the same amount (see
  the follow-up), so on this account they cannot be told apart. A second account, ideally on a
  paid plan, is the next place to look.
- `[1]..[3]` (perhaps a tier or plan code). Not interpreted.
- A second profile. `ffroliva` was in use by another agent and was not opened.
- Whether a direct HTTP replay of `nzlxg` (cookies + `at` token, no browser) is accepted. Only
  the app's own request was observed.
- Whether `nzlxg` fires on a project page as well as the root (only the root was loaded).
- The `a.credits-link` target (the plan / top-up page) was not followed.
- `gflow auth status --profile denon82` reported "signed in to Google, but not to the Flow app"
  minutes before this run, while the browser reached the app in both loads. That disagreement
  is outside this spike's question and is recorded here, not explained.
