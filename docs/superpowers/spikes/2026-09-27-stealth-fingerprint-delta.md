# playwright-stealth changes no automation tell on gflow's generation context (2026-09-27)

**Question.** Issue #906 / PR #907 report that on one Ultra account Flow refuses every
Playwright-driven video submit with an "unusual activity" card, and that
`Stealth().apply_stealth_async(context)` from `playwright-stealth` makes it succeed. gflow's
generation context already drops `--enable-automation`, passes
`--disable-blink-features=AutomationControlled` and overrides `navigator.webdriver`
(`api/client.py`). What does stealth still change? A pass/fail flip can only come from that
delta.

**Answer: nothing that is an automation tell.** Three fields differ, none of them is one
Google is known to key on, and two of them stealth makes *less* consistent than the bare
context.

**Instrument.** `scripts/dev/spike_stealth_fingerprint_delta.py`, through `FlowApiClient`
(lease held, gflow's own page). Arm `bare` probes flow.google.com, then stealth is applied to
the same context and the page reloaded (arm `stealth`). `$0` — nothing submitted. Reading
pre-registered in the script docstring. Profile `ffroliva`, Windows 11, Chrome 153, headed,
window focused. Evidence: `scripts/dev/_spike_out/spike_stealth_fingerprint_delta_20260927_211739.json`
(gitignored).

## Observed

Identical in both arms: `navigator.webdriver` undefined, no `__pw*`/`cdc_`/`playwright`
globals, real `Google Chrome` brand in `userAgentData` and `sec-ch-ua`, the same
`user-agent`, `sec-ch-ua*` and `accept-language` request headers, 5 PDF plugins,
`window.chrome` = `app, csi, loadTimes`, `visibilityState=visible`, `hasFocus=true`.

| Field | bare (gflow) | stealth | Note |
|---|---|---|---|
| `navigator.languages` | `["en-US"]` | `["en-US","en"]` | cosmetic; both follow gflow's pinned `en-US` (#854) |
| `permissions.query({name:'notifications'}).state` | `prompt` | `default` | `default` is not a valid `PermissionState` — stealth's patch is the anomaly |
| WebGL unmasked vendor / renderer | `Google Inc. (Intel)` / `ANGLE (Intel … Arc … D3D11)` | `Intel Inc.` / `Intel Iris OpenGL Engine` | stealth reports a macOS GPU under a Windows UA |

## Reading

Row 1 of the pre-registered table: **stealth cannot explain a pass/fail flip on this
machine.** The tells stealth exists to hide are already hidden by gflow's own launch.

## Not measured — do not read these as answered

- **The contributor's machine.** #906 ran through a private launcher
  (`scripts/gflow-isolated.cmd`, "headed Chrome on an isolated desktop"). A hidden or
  unfocused desktop changes `visibilityState` / `hasFocus` / input events, which reCAPTCHA
  Enterprise does read. That is the leading unmeasured confound.
- **Google's reaction.** This measures the delta, not a score. No submit was made.
- **Repeatability of #906's A/B.** One run per arm; reCAPTCHA scores vary run to run.

**What would settle it:** on the affected account, run this probe *through the contributor's
launcher* (does `visibilityState`/`hasFocus` read hidden/false?), then N≥3 video submits per
arm, bare vs stealth, from a foreground desktop.
