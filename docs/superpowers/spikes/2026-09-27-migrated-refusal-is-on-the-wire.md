# A flow.google.com refusal is on the wire, and gflow was discarding it (2026-09-27)

**Question (#873, #906, #907).** On the migrated host a refused generation surfaces as a
60 s video `TransportTimeoutError` or an image `WireFormatError("returned no ogiZ0b
frame")`, while Flow's grid shows *"We noticed some unusual activity"*. Two PRs tried to
scrape that card. Is the refusal's reason in the batchexecute reply, and do we drop it?

**Answer: yes and yes.** Google replies HTTP 200 with an error envelope naming the reason;
`batchexecute.parse_frames` discards any frame whose payload is not a string.

**Instrument.** `scripts/dev/spike_migrated_refusal_envelope.py`, through
`FlowApiClient.generate_image` on profile `ci-probe` (a probe account, chosen because a
refused token can raise a profile's WAF score). One image, benign prompt. Readings were
pre-registered in the script docstring. Zero credits. Evidence:
`scripts/dev/_spike_out/spike_migrated_refusal_envelope_20260927_21{2648,2825}.json`
(gitignored).

| Arm | What left the browser | Reply | `parse_frames` | gflow raised | Grid tile |
|---|---|---|---|---|---|
| `tamper` | the `ogiZ0b` submit with its 2 425-char reCAPTCHA token corrupted (tail reversed) | **HTTP 200** at 5.2 s: `["wrb.fr","ogiZ0b",null,null,null,[7,null,[["type.googleapis.com/google.rpc.ErrorInfo",["PUBLIC_ERROR_UNUSUAL_ACTIVITY"]]]],"generic"]` | `[]` | `WireFormatError: migrated image submit returned no ogiZ0b frame` | `<flow-error-tile>` · *"We noticed some unusual activity…"* |
| `abort` | nothing — `route.abort()` | none; `requestfailed net::ERR_FAILED` | — | `TransportTimeoutError` after 180 s | `<flow-error-tile>` · *"Sorry, this image failed to generate."* |

Both tiles carry the same ligatures (`warning`, `refresh`, `undo`, `delete_forever`) and
the same custom-element structure; only the copy differs.

## Reading

1. **The refusal is on the wire.** Status 7 (`PERMISSION_DENIED`) with `ErrorInfo` reason
   `PUBLIC_ERROR_UNUSUAL_ACTIVITY` — the same reason the labs REST path returned as an
   HTTP 403 body (KNOWN_ISSUES, `WafRejectionError`).
2. **We dropped it.** `parse_frames` requires `item[2]` to be a string; the envelope's is
   `null`. Every caller therefore saw an empty reply. Root cause:
   `src/gflow_cli/api/transports/batchexecute.py` `parse_frames`, reached from both submit
   observers in `migrated_composer.py`.
3. **The DOM cannot discriminate; the wire can.** A refusal and an abort render the same
   tile. A refusal has a reply with a reason; an abort has no reply. This confirms the
   #873 re-review finding that blocked tile-scraping.

## Not measured

- **The video submit's envelope.** Measured on `ogiZ0b` (image) only, to spend no
  credits. The video observer reads the same `batchexecute` framing and is covered offline;
  a live video refusal would cost credits if the token were accepted.
- **Content-safety reasons on this host.** No `PUBLIC_ERROR_UNSAFE_*` refusal was
  provoked; the mapping to `ContentPolicyError` reuses the REST path's reason set.
- **What #906's account sees.** This provokes the refusal; it does not explain why one
  account gets it on every automated submit.
