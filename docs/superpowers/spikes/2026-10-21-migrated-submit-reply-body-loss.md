# Spike: a lost SUBMIT reply body on flow.google.com (#1010)

**Date:** 2026-10-21 · **Profile:** `ffroliva` (served flow.google.com) · **Version:** 0.86.0 (`develop` 04b98afa)
· **Script:** [`scripts/dev/spike_migrated_submit_body_loss.py`](../../../scripts/dev/spike_migrated_submit_body_loss.py)
· **Cost:** one veo-lite clip (credits) and 5 images (quota)

## Question

#1009 showed that Chrome sometimes refuses to return a reply body:
`Network.getResponseBody: No data found for resource with given identifier`. It happened on
2 of 45 `maseQ` uploads ([spike](2026-10-20-migrated-upload-reply-body-eviction.md)), and both
uploads had saved. #1010 asks what happens when the same loss hits a generation **submit**
reply. Does gflow report an accepted, billed job as a retryable failure, inviting a second
billed submit?

## Method

The script patches Playwright's `Response.text` and drives the production path, `gflow …
--json` in-process. The pre-registered readings are in the script's docstring.

- **inject-image:** `gflow image t2i --count 1`. The first `ogiZ0b` reply raises the exact
  #1009 error text.
- **inject-video:** `gflow video t2v --model veo-lite`. The first reply on any submit rpc
  raises the same error.
- **count:** 10 natural t2i runs in one warm client, with no injection. It counts every
  unreadable `batchexecute` body that gflow reads.

Each inject arm then reloads the project and looks at what Flow actually made.

## Observed

### Image: gflow submits a second time on its own, and reports success

| | |
|---|---|
| Injected | 1 × `ogiZ0b` |
| CLI | **exit 0**, `"status": "ok"`, 1 image reported (`51d23de1…`) |
| Log | `migrated.navigate` → `image_settings_applied` → `prompt_typed` **twice**, 15 s apart |
| Project afterwards | **2 images**: `51d23de1…` (reported) and `d89b35ce…` (never reported, downloaded or catalogued) |

The cause is `client.py::_drive_images_generation`. It wraps the billed
`transport.generate_images()` call in `post_with_retry()`, and `_retry.py::_make_retrying`
retries any Playwright `Error` or `TimeoutError` up to 3 times. The image listener
(`migrated_composer.py::submit_images_and_observe`, the `on_response` `try`) hands the raw
Playwright error from `response.text()` to the result future. So the whole submit runs again:
navigate, settings, prompt, click.

This is **worse than #1010 predicted**. Nothing has to retry on `retryable: true`, because
gflow has already re-submitted before it reports anything. An image costs quota, not credits.
The first image is still lost to the user.

### Video: an accepted clip is reported as a retryable timeout

| | |
|---|---|
| Injected | 1 × `YhhmEf` |
| CLI | **exit 9** `TransportTimeoutError`, **`retryable: true`**, after 71.5 s |
| Detail | `no YhhmEf/eb1hJf/MZZa6b/nprQif reply within 60s of clicking submit (rpcs seen: WuwhI, YhhmEf, as29s, jwpduf, ngNC2)` |
| Project afterwards | **1 finished clip** ("Teal origami cr…"): Flow made it and billed it |

This matches #1010 exactly. The video listener (`submit_and_observe`, `except Exception:
return`) drops the lost reply. The workflow id is therefore never learned, so the status
replies that did arrive (`as29s`, `jwpduf`) are ignored as well. The video path has no
client-level retry, so there is one clip and nothing automatic. But the error tells an agent
to retry, and a retry bills a second clip.

Two problems in the error text itself:

- **The detail contradicts itself.** It says "no YhhmEf reply", then lists `YhhmEf` under rpcs
  seen. The reply arrived; its body did not.
- **The remediation is wrong.** "A single API call exceeded the 30 s deadline" is the class's
  default hint. The budget here is 60 s, and the advice does not fit.

### Natural rate: count arm

The count arm planned 10 runs and completed 3. The evidence is in
`_spike_out/…_count_20261021_233516.json`.

| Run | `ogiZ0b` body | Outcome | In the project |
|---|---|---|---|
| 1 | read, 1218 B | ok `b8b42276…` | yes |
| 2 | read, 1217 B | ok `8070613a…` | yes |
| 3 | **no `ogiZ0b` reply was read at all** | exit 9 `TransportTimeoutError` after 180 s, `retryable: true` | **yes**: `ce47fb86…` ("Study 3") |
| 4–10 | not run | `BrowserSessionClosedError`: the warm client did not survive run 3's failure | n/a |

- **No `No data found` occurred naturally** in 2 readable submits. That is far too few to give
  a rate. Reading: *unmeasured*.
- **Run 3 is a natural instance of the same outcome by another route.** Flow made the image.
  gflow never read an `ogiZ0b` reply and reported a retryable timeout. Whether the response
  event never fired or fired on a URL the listener does not match was not instrumented.
  Either way, an accepted generation is reported as `retryable: true`.
- **Runs 4–10 are an instrument limit, not a finding.** A warm-client loop has to rebuild the
  client after a failure. The script does not do that yet.

## Instrument error, corrected

The first video-arm tile check reported `{"ids": [], "videos": 0}` after 7 minutes, which
reads as "no clip". It was wrong. A finished video tile has no `data-media-id` and no
`<video>` element until it is hovered. A DOM probe plus a screenshot of the same project found
the clip. The check now also counts content poster images.

## Not measured

- **Labs path.** `post_with_retry()` wraps `generate_images` for every transport. Any
  Playwright error raised after the submit click on the labs UI path would also re-submit.
  This comes from reading the code and was not run, because no profile here is served labs.
- **Whether Chrome's own page-JS copy survives** when the DevTools read fails. Same gap as
  #1009.
- **The cause of the eviction.**

## What the fix needs (input to the Bug Lane, not a design)

1. Never retry a page-owned, billed submit at the client layer. A retry is only safe before
   the click.
2. Image: an unreadable `ogiZ0b` body must not surface as a raw Playwright error.
3. Video: an unreadable submit body must not become a retryable timeout. The status rpcs can
   still settle the run, or the run must report "submitted, outcome unknown" with
   `retryable: false`.
4. Both: a timeout **after** the submit click is "outcome unknown", not "retry". Run 3 got
   there without any lost body. The same reclassification covers the inject arms and the
   natural case.
