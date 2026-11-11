# Spike: the `SPrCad` reply body Chrome loses during a 2K image upscale (#1027)

**Date:** 2026-10-22 · **Profile:** `ffroliva` (served flow.google.com)
· **Script:** [`scripts/dev/spike_upscale_lost_body.py`](../../../scripts/dev/spike_upscale_lost_body.py)
· **Cost:** $0 (2K image upscale only)

## Question

`upscale_image_migrated` fails with `Failed to parse SPrCad response: Response.text: Protocol
error (Network.getResponseBody): No data found for resource with given identifier`. Unlike
the video export (#1014), the lost body is the payload: the upscaled image travels base64
inside it. Is the image anywhere else we can read without resending anything?

## Method

One page, one image (the profile's newest catalogued one), 12 upscales back to back. Per
run: whether DevTools could read the `SPrCad` body, and the SHA-256 of the image in it; the
anchors the app tried to `click()` (the shipped code already stubs that click so nothing
lands in Downloads); and every blob over 1 KB passed to `URL.createObjectURL`, with its
size, MIME, first bytes and SHA-256 computed in page JS.

The first attempt read the anchor's `blob:` `href` back after the click. That fetch failed
(`TypeError: Failed to fetch`): the app revokes the URL straight away. The script then hooked
`URL.createObjectURL` instead, as `migrated_video_upscale` already does for exports.

## Observed (`_spike_out/spike_upscale_lost_body_20261022_170113.json`)

Run as `uv run python scripts/dev/spike_upscale_lost_body.py ffroliva --runs 12`.

| | Runs |
|---|---|
| DevTools read of the `SPrCad` body failed with `No data found` | **6 of 12** (runs 1, 3, 5, 8, 10, 11) |
| an `image/jpeg` blob of 3,143,496 bytes reached `createObjectURL`, the only blob over 1 KB in each run | **12 of 12** |
| blob SHA-256 equals the DevTools image's SHA-256 (readable runs) | 6 of 6 |
| blob SHA-256 identical across all 12 runs, failed reads included | yes |
| anchors clicked per run | 1 (`blob:`, `download` = `<prompt>_2K_<timestamp>.jpg`) |

Each upscale took about 4 s. The reply was about 4.2 MB of text.

## Reading

The app reads the reply with `fetch` and builds the download blob from it, and a DevTools
eviction does not touch either. The blob is a faithful second carrier, and it was there on
every run where the body was lost. Fix: take the image from whichever arrives first, the
readable reply or the blob, and stop treating an unreadable body as a failure. A readable
`SPrCad` refusal still fails the run. The hook is the one `migrated_video_upscale` already
installs, now shared from `migrated_upscale`.

## Not measured

- The cause of the eviction. Here it hit half the runs on a single page, far above the rate
  #1009 saw for small upload replies; reply size is consistent with it but not shown to be
  the cause.
- 4K (the account offers no 4K) and any account other than `ffroliva`.
