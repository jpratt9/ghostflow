---
name: migrated-refusal-is-a-dom-card-not-a-wire-record
description: CORRECTED 2026-09-27 — a flow.google.com refusal IS on the wire (HTTP 200, a null-payload batchexecute envelope carrying gRPC status + ErrorInfo reason); gflow used to drop it in parse_frames. Read the wire, never the grid card.
---

**The slug is historical and now wrong; it is kept because the council routing table
and `check_council_memory.py` cite it.** Until 2026-09-27 this note said a refusal on
`flow.google.com` reaches the page but not the wire. Measured that day
([spike](../spikes/2026-09-27-migrated-refusal-is-on-the-wire.md), a submit with its
reCAPTCHA token corrupted in flight), it is on the wire:

```
HTTP 200
[["wrb.fr","ogiZ0b",null,null,null,
  [7,null,[["type.googleapis.com/google.rpc.ErrorInfo",["PUBLIC_ERROR_UNUSUAL_ACTIVITY"]]]],
  "generic"], …]
```

A null payload, the gRPC status in slot 5, Google's `ErrorInfo` reason inside it.
`batchexecute.parse_frames` kept only frames whose payload is a string, so it silently
discarded this one — the "silence / never parses" shape the old note recorded was **our
parser**, not Flow. That is why the video path waited out a retryable 60 s
`TransportTimeoutError` and the image path raised `WireFormatError("no ogiZ0b frame")`
while the grid showed *"We noticed some unusual activity… You have not been charged"*.

**The fix reads the wire:** `batchexecute.rpc_errors` returns the envelopes
`parse_frames` skips, and `migrated_composer._submit_refusal` maps a REASON to a class —
`PUBLIC_ERROR_UNUSUAL_ACTIVITY` → `WafRejectionError` (the labs path's class for the same
reason), `CONTENT_SAFETY_REASONS` → `ContentPolicyError`. A bare status with no reason is
not a refusal: the #723 entity submit Flow queued and ran replies `[5]`.

**Why the grid card is the wrong source, measured the same day:** a submit aborted in
the browser (`route.abort()`, no reply, `net::ERR_FAILED`) renders the identical
`<flow-error-tile>` — same `warning`/`refresh`/`undo`/`delete_forever` ligatures, only the
copy differs. Structure cannot tell a refusal from an abort; the wire can (a reply with a
reason vs. no reply at all). This is the finding that blocked PR #873 and PR #907, both of
which scraped the tile — see [[content-policy-text-scan-false-positives-on-page-chrome]].

**"Unusual activity" is not a content verdict.** It is reCAPTCHA Enterprise scoring the
browser profile. Never route it to `ContentPolicyError`'s "rewrite the prompt"
remediation. #906 reported it on every automated submit on one account; the stealth
spike (PR #908, `2026-09-27-stealth-fingerprint-delta.md`) found
`playwright-stealth` changes no automation tell on gflow's context, so do not add a
stealth dependency on the strength of #906.

Diagnosed by an external contributor (stgmt) in #873 and #906; the diagnosis was right
from the start. See [[migrated-host-driver-wire-lessons]] for the rest of this host's
wire.
