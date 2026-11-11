# Spike: labs.google's session URL is gone; what still tells a signed-in session? (#1023)

**Date:** 2026-10-22 · **Profile:** `ffroliva` (served flow.google.com) · **Version:** 0.86.0 (`develop` 04b98afa)
· **Script:** [`scripts/dev/spike_session_oracle.py`](../../../scripts/dev/spike_session_oracle.py)
· **Cost:** $0 (page loads only)

## Question

#1023 reports that `gflow auth login` fails on every account since 2026-10-22:
`https://labs.google/fx/api/auth/session` answers **HTTP 410 Gone**. That URL is gflow's
only session oracle (`auth/verification.py::SESSION_API_URL`). Is that true here, and
which signal still separates a signed-in Flow session from a signed-out one?

The [2026-09-06 spike](2026-09-06-labs-vs-migrated-session-credential.md) predicted this
failure (its Q4: "a re-login loop that the user cannot escape"). Its predict verdict
deferred a fallback for `VERIFICATION_ERROR` because the state had never been observed.
It is observed now.

## Method

Two arms, readings pre-registered in the script docstring:

- **profile**: the real profile, through gflow's own `FlowApiClient` (real Chrome).
- **anonymous**: a fresh bundled-Chromium context with no cookies (the control).

Each arm loads `flow.google.com/`, then records where it lands, the avatar count, whether
the profile's recorded account email appears (a bool, never the value), which
`batchexecute` replies carry that email, and `request.get` probes of the candidate session
URLs (status, content type, top-level JSON keys only).

## Observed

| Signal | profile (4 runs) | anonymous (3 runs) |
|---|---|---|
| `labs.google/fx/api/auth/session` | **410**, JSON `{"error"}` | **410**, JSON `{"error"}` |
| `flow.google.com/fx/api/auth/session` | 200, `text/html` (the app shell) | 200, `text/html` |
| `flow.google.com/api/auth/session` | 200, `text/html` | 200, `text/html` |
| `flow.google.com/` lands on | `/` (the app), avatar 1 | `/about` (marketing), avatar 0 |
| account email in the rendered DOM | yes | no |
| account email in the un-rendered shell | yes, under `WIZ_global_data` key **`oPEP7c`** (1 run) | no |
| `batchexecute` reply carrying the email | **`o30O0e`** (1 of 1 runs that recorded rpcids) | none |

`gflow auth status --profile ffroliva` on the same profile: exit 1, `status_code=410`,
"Could not verify the Flow session", while image generation on the same profile
succeeded 40 minutes earlier (#1010's e2e).

- **#1023 is confirmed and account-independent.** The labs URL answers 410 with and
  without cookies.
- **flow.google.com has no NextAuth JSON route.** Both candidate paths serve the app shell.
- **flow.google.com itself separates the states**, three independent ways: the landing
  path, the shell's `oPEP7c`, and the `o30O0e` reply.

## What gflow already had

`_verify_migrated_host_fallback` (#791) is a server-attested oracle that does not use labs:
it needs the SSO + flow.google.com session cookie pair, then reads
`myaccount.google.com`, where a dead session cannot stay. It ran only when labs said
`GOOGLE_SESSION_ONLY`. A 410 is `VERIFICATION_ERROR`, so it never ran.

The fix reads a 410 as labs' own "no user" answer, since no labs session exists any more.
The existing Google-cookie split then decides: no `SAPISID` is `NO_SESSION` (sign in), and
`SAPISID` is `GOOGLE_SESSION_ONLY`, which runs the server-attested fallback. A transient
status (5xx, 429) keeps its `VERIFICATION_ERROR` and does not launch a browser.
`auth renew`'s labs refresh step treats 410 as "nothing left to refresh" for the same
reason, so the verdict comes from the verifier.

Measured after the fix on the same profile: `gflow auth status` exit 0, "Flow session
verified"; `test_auth_verification_e2e.py` 4/4 (3/4 failed on `develop`), the new MCP
twin e2e passed.

## Not measured

- **The `oPEP7c` and `o30O0e` readings are 1 run each** on one profile. They are recorded
  as candidates for a host-native oracle, not used.
- **A profile with Google cookies whose fallback probe fails for a non-session reason**
  (browser launch error) is reported `GOOGLE_SESSION_ONLY` ("sign in again"). Before labs
  went, the same profile got the same answer whenever labs said "no user".
- **The access-token consumers** (`client._fetch_access_token`, the agentic driver,
  `credits`) also read the labs URL, and no account can get a token from it now. Measured:
  `credits.inspect_profile` on `ffroliva` raises `AisandboxAuthError` "no access_token in
  /fx/api/auth/session". Credits on flow.google.com need their own port (#795); not fixed here.
- **Linux.** The reporter is on Linux; this ran on Windows.
