# The image pre-mint fails on a warm client's parked page (2026-09-20, #891)

**Question.** #781 argued that a redundant client-side reCAPTCHA mint on a migrated run
is harmless "because the page mints its own". Does that hold on the page the run actually
leaves behind?

**Answer: no.** After a successful image run, the transport parks pool page 0 on
`about:blank`. A later client mint there raises `RecaptchaError`, and the migration
guard stays silent because `about:blank` carries no host. An unported form on that warm
client therefore failed with "the Flow editor page may have failed to load" instead of
exit 36.

## Instruments

| Script | Cost | What it measured |
|---|---|---|
| `scripts/dev/spike_mint_on_about_blank.py` | $0, any Chromium | `flow_host_kind("about:blank")` is `None`; `raise_if_migrated` returns; `TokenMinter.mint` raises `RecaptchaError` in 0.01 s |
| `scripts/dev/spike_warm_client_unported_form.py` | One image of the daily cap | Live on `ffroliva`: call 1 `SUCCEEDED`, `url_after_call1 = about:blank`, call 2 (UUID ref) `RecaptchaError` |

Output lands in the gitignored `scripts/dev/_spike_out/`.

## Mechanism

- The pool page is the transport's page at the default concurrency of 1 (`client.py:783`, `:1182`).
- The success path parks the page on `about:blank`. The failure path defers the park (#792).

So the defect only followed a **success**. A fresh client, or one whose previous run
failed, still got exit 36.

## What the fix rests on (2026-09-29)

- **The token was dead weight for the UI transport.** Nothing in `ui_automation.py`,
  `drivers/` or `migrated_composer.py` reads `recaptcha_token`, and `git log -S` shows it
  never did. Flow's page mints its own on click.
- **Baseline before the fix** (`develop` 342f39df, `ffroliva`, `t2i --model imagen4`, $0):
  - Both arms exited 36, with and without `--project`.
  - The refusal came from **the client's mint guard** (`ui_driver.migrated_host_bail at=mint_recaptcha_token`), so removing the mint had to be proven to keep exit 36.
- **After the fix:**
  - The same two commands exit 36, raised by the composer, with the message "the IMAGEN_3_5 model is not ported yet".
  - The client no longer mints.

## Not measured

- **An account served labs.** Labs answers 308 on every profile here (2026-09-14
  survey). The fix is correct there by construction, since the token was never sent, but
  it was not observed.
- **Callers that genuinely send the token:** `upscale_image` and `extend_video`, and
  the experimental HTTP image transports. The upscale/extend mints should hit the same
  `about:blank` failure on a warm client. That is inferred, not run, and tracked separately.

## Reachability

**Corrected 2026-09-29 by the #916 council (D6).** `gflow run --config` runs every prompt
through one client (`run_image_batch`) and accepts a per-prompt `model`, so
`[nano2, imagen4]` is the #891 repro. Measured on `ffroliva`:

| | exit | prompt 2 |
|---|---|---|
| `develop` 342f39df | 1 — traceback, results table lost | `RecaptchaError` |
| fix branch | 36 — table printed, "1/2 succeeded" | `FlowHostMigratedError`, "the IMAGEN_3_5 model is not ported yet" |

The scenario's reachability sweep had covered `t2i` multi-prompt (one shared model), `image
batch` (refused on flow.google.com), MCP (fresh client per task) and `movie`, and missed
`gflow run`. Lesson: enumerate callers of `generate_image` by *runner*, not by command
name — `run_sequential_batch` has two front doors.
