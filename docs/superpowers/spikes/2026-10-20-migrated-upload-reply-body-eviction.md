# Spike: the `maseQ` reply body that Chrome will not give back (#1009)

**Date:** 2026-10-20 · **Profile:** `ffroliva` (served flow.google.com, uploads already consented)
· **Script:** [`scripts/dev/spike_migrated_upload_body_eviction.py`](../../../scripts/dev/spike_migrated_upload_body_eviction.py)
· **Cost:** $0 (uploads and project creation only, no submit)

## Question

#1009 reports exit 27 *"maseQ answered 200 without a media id"* on uploads that succeeded.
`response.text()` raises `Network.getResponseBody: No data found for resource with given
identifier`, and `_upload_via_toolbar` swallows that error as an empty body. Does it reproduce
on our account? Does the reporter's `page.route` + `route.fetch` + `route.fulfill` workaround
prevent it? Is there a way to get the media id that does not depend on the DevTools copy of
the body?

## Method

The script drives the real `_upload_via_toolbar` with 2 MB incompressible PNGs, uploaded back
to back in pairs like the reporter's two references. It uses one fresh project per run and
alternates two arms, A B A B, so that project fill is spread over both:

- `baseline`: the shipped path.
- `route`: the reporter's workaround.

On every upload it records three things:

- whether the DevTools body read succeeded;
- a page-JS read: an init script wraps `window.fetch` and `XMLHttpRequest` and keeps
  `clone().text()` for `rpcids=maseQ`;
- whether any later `batchexecute` reply names the upload's run-unique display name.

## Observed

| Run | Uploads | `baseline` unreadable | `route` unreadable | page-JS read with ids |
|---|---|---|---|---|
| 1 (`_spike_out/…_101406.json`) | 16 | 0/8 | **2/8** | not yet instrumented |
| 2 (`_spike_out/…_101834.json`) | 24 | 0/12 | 0/12 | 24/24 |
| 3 (`_spike_out/…_102427.json`) | 5 valid of 32 | 0/2 | 0/3 | 5/5 |

Run 3 measured almost nothing about #1009. Its 6th upload hit an unrelated one-off failure,
`UiSelectorDriftError` "the upload entry opened no file chooser within 8s". The toolbar menu
it left open then blocked every later click on `+`, and the page's response count froze at
151. That was an instrument defect: the spike never closed the menu after a failure. The
script now presses Escape after a failed attempt. Shipped callers stop at the first failure,
so they cannot wedge this way.

- **The exact error reproduces on our account.** The text is `Response.text: Protocol error
  (Network.getResponseBody): No data found for resource with given identifier`. The driver
  reported it as `MediaUploadRejectedError` "answered 200 without a media id". That is the
  misreport in #1009, confirmed live.
- **The write persisted every time the body was lost.** A fresh load of run 1's project, with
  no hover, read 16 tiles for 16 uploads, each with a name and an `img[data-media-id]`. Both
  uploads whose body was unreadable were there, with media ids: `ref_p0_route_2-…` and
  `ref_p2_route_1-…`. So the old "answered 200 without a media id" hid a successful upload.
  It was not a refusal.
- **The workaround did not prevent it here.** Both failures happened under `route`. With 2
  events in 40 uploads, this does not show that the workaround makes things worse. It does
  show that the workaround is not a fix.
- **Buffer pressure does not explain it.** The failures came at 14 MB and 33 MB of response
  bytes seen by the page, while reads succeeded up to 75 MB. The upload index does not
  explain it either: one failure was the 1st upload of its pair and one was the 2nd.
- **The app reads the reply with `fetch`, not XHR.** The hook captured the body through its
  `fetch` branch every time. The body starts with `)]}'` and is about 650 B with 6 UUIDs, the
  same as the DevTools copy.
- **Option (b) has no carrier on the wire.** After the timing fix in run 2, no later
  `batchexecute` reply carried an upload's display name. Non-`batchexecute` traffic was not
  checked.

## Not measured

- **Whether the page-JS read still succeeds at the moment the DevTools read fails.** The two
  have not failed in the same run yet. Run 1 had no hook, and runs 2 and 3 had no failures:
  2 failures in 45 valid uploads, about 4%. That rate needs on the order of 100 uploads to
  catch even one failure with the hook installed. A fix must therefore stay correct if the
  hook also fails: keep the DevTools read first, use the page-JS copy as a fallback, and
  report "reply body unavailable" when both miss. Never report that case as a refusal.
- **The reporter's failure rate.** They saw 0 of 6 runs pass; we saw 2 failures in 40. Their
  setup differs: Windows, Playwright 1.61.0, a project holding dozens of media.
- **The cause of the eviction.**

## Reading

The defect is real: an unreadable body is reported as a refusal. The cheapest correct change
reports it as its own failure. This note only tested recovery mechanisms that read the
reply. One of them is a page-JS read, which patches `window.fetch` inside Flow's page, so
the app can detect it. `/gflow:predict` (2026-10-20, CAUTION) preferred a recovery that does
not read the reply at all.

**PR #992** (opened 2026-10-18, before this note) already does that. It reads the project
back in a second tab and matches the upload by its run-unique name to a tile's
`img[data-media-id]`. That needs no page patch and resends nothing. Its own note is
`2026-10-18-rpc-response-body-readback.md` (on the #992 branch). Take
this note as independent evidence for #992's premise. It does not compete with #992's
design.
