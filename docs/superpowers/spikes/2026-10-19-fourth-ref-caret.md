# #997 — where the caret lands before the 4th `@` on flow.google.com

**Question.** Issue #997 (external reporter, gflow 0.83.1, macOS, headed Chrome) says the
4th and later references never attach on the migrated composer: chips 1–3 land, the 4th
`@` opens no picker and its query lands as plain text. The claimed cause is the composer
click in `MigratedComposer._mention_by_token` / `_mention_by_name`: Playwright clicks the
centre of the editor, which (once line 1 fills) puts the caret directly behind chip 3.

**Script.** [`scripts/dev/spike_997_fourth_ref_caret.py`](../../../scripts/dev/spike_997_fourth_ref_caret.py)
(reading pre-registered in its docstring, commit `cdf757b7`, before the first run; the
method amendment and the `--send-prompt` reading were added in `83e4ebae`, before any run
that used them. Two earlier runs with a hand-rolled commit gesture attached nothing,
not even mention 1, so they measured the spike rather than #997, and they are discarded).
Profile `denon82` (classic composer, served flow.google.com), project `2ddc3a33…` (8
images), viewport 1280×720 (gflow's own), Windows 11. Each mention calls production
`_mention_by_token` **unchanged**; `page.keyboard.type` is wrapped so a hook runs after
production's composer click and before its `@`, records the selection, and — in the fix
arms only — moves the caret. Targets are 5 grid images queried by their picker caption
(the in-place path). **$0: nothing was submitted**; every run ends with
`clear_composer` and the next starts with a reload.

## Code under test (develop @ `aee3c6a8`)

| Site | Line |
|---|---|
| `_mention_by_token` — composer click, then `@` | `src/gflow_cli/api/transports/migrated_composer.py:2355-2356` |
| `_mention_character` — same click, then `@` (not named in the issue) | `migrated_composer.py:2516-2518` |
| `_mention_by_name` — same click, then `@` | `migrated_composer.py:2606-2612` |
| `_mention_by_name` retry backspaces `len(name)+1` keys at the caret | `migrated_composer.py:2632-2643` |
| a chip is accepted by **count** (+ last chip's kind), not by position or identity | `migrated_composer.py:2369-2371`, `2619-2620` |

`COMPOSER = "[contenteditable='true']"` (`:115`); `.click()` on it targets the box centre.

## Observed (capture `_spike_out/spike_997_fourth_ref_caret_20261019_170715.json`, 3 runs × 4 arms, interleaved)

| Arm | References attached | Picker opened | Mentions whose `@` was typed with a chip AFTER the caret |
|---|---|---|---|
| `click` (production, the control) | **5/5 in 3/3 runs** | 15/15 | **1 per run (mention 4), 3/3** |
| `range_end` (the reporter's fix) | 5/5 in 3/3 | 15/15 | 0 |
| `end_key` | 5/5 in 3/3 | 15/15 | 0 |
| `ctrl_end` | 5/5 in 3/3 | 15/15 | 0 |

Plus a single-arm validation run before the matrix (`…_170534.json`): identical, 5/5.

What the control arm does, identically in every run (caret read after production's click,
before its `@`; `cb/ca` = chips before / after the caret):

| Mention | Click point (`elementFromPoint` at the box centre) | `cb/ca` | Node before the caret | Chip lines |
|---|---|---|---|---|
| 1 | `<p>` | 0/0 | — | 0 |
| 2 | `<p>` | 1/0 | text `" "` | 1 |
| 3 | **`span.mention-chip`** (chip 2) | 2/0 | **chip 2** (the trailing spaces are *after* the caret) | 1 |
| 4 | **`span.mention-chip`** | **2/1** | **chip 2** — chip 3 is after the caret | 1 |
| 5 | `<p>` (composer grew to 2 lines, centre moved) | 4/0 | text `" "` | 2 |

So with three chips on the line, the centre of the composer is **on a chip**, and the click
leaves the caret directly behind chip 2. Mention 4 is then inserted **between chip 2 and
chip 3**: the prompt's chip order becomes 1, 2, 4, 3. Every fix arm moves the caret to
3/0 before the `@`, and the order stays 1, 2, 3, 4.

## Verdict, as observed

1. **The caret mechanism is real and stable (3/3).** Production's composer click
   (`migrated_composer.py:2355`, same gesture at `:2516` and `:2606`) lands on a chip once
   three are on the line and leaves the caret wedged behind an earlier chip, not at the end
   of the document. This part of the reporter's root cause holds.
2. **The reporter's failure did not reproduce here (0/3).** The picker opened for every
   `@` (60/60 mentions), including the ones typed directly behind a chip, and all 5
   references attached in every run. On this setup the wedged caret is *silent*: the
   reference lands, out of order. Per the pre-registered reading this **settles nothing**
   about the reporter's symptom — it is equally consistent with a layout/platform
   difference (macOS, their window width; mention 4 here was still on one line, so the
   "line 1 full, trailing space wraps" precondition the reporter describes was never met
   at 1280×720) or with a Flow-side difference in when the mention plugin opens.
3. **"A chip directly before the caret blocks the picker" is refuted as a general rule.**
   Mentions 3 and 4 of every control run had a chip immediately before the caret and the
   picker opened.
4. **The proposed fix (DOM Range collapsed to the end) works on the axis measured:** 3/3,
   caret at the end, chips in order, picker open. `End` and `Control+End` did the same
   here — but only because every chip was still on one visual line at mention 4, so this
   does **not** test the reporter's claim that `End` fails once the line wraps.
5. **Nothing guards the order.** `_mention_by_token` accepts a mention when the chip
   **count** rises and the *last DOM* chip is media (`:2369-2371`); `_mention_by_name`
   checks count only (`:2619-2620`). Neither notices a chip landing in the middle.

### Chip order and prompt placement, by identity (`…_172021.json`, `--send-prompt`, 4 refs, 2 runs × 2 arms)

After the four mentions the probe calls production `send_prompt(append=True)` with a
marker and reads the composer's document order, mapping each chip's caption back to
the order it was requested in:

| Arm | Run 1 | Run 2 |
|---|---|---|
| `click` (production) | `1, 2, 4, 3, PROMPT` | `1, 2, 4, 3, PROMPT` |
| `range_end` (fix) | `1, 2, 3, 4, PROMPT` | `1, 2, 3, 4, PROMPT` |

This confirms by chip identity, not by count, that production puts reference 4 **before**
reference 3, every time. The pre-registered prompt question came back negative: the
prompt landed last in both arms, so no split prompt was observed.

## Surfaces

All three mention gestures share the click, and every caller reaches them:
`attach_existing_references` → `_mention_by_token` (in-place refs, image path `:3625`);
`attach_references` → `_mention_by_name` (uploaded `--ref` files: image `:3629`, r2v video
`:3530`); `attach_character_entities` → `_mention_character` (`:3535`, `:3643`). The MCP
tools route `reference_images` into the same request fields (`mcp/tools.py:665-687`), so
CLI and MCP reach identical transport code — one fix in `migrated_composer.py` covers both.

## Not measured

- **macOS, or any viewport but 1280×720.** The reporter's exact symptom (no picker, query
  as plain text) needs their platform/width; nothing here can say whether a wrapped line
  changes the picker's behaviour.
- **The uploaded (`_mention_by_name`) and character (`_mention_character`) paths live.**
  Same click; only the in-place path was driven. The reporter's "3 chip(s) before, 0
  after" is consistent with the retry's `len(name)+1` Backspaces (`:2632`) running at a
  wedged caret, but that was not reproduced.
- **More than 5 references**, and whether Flow reads reference order from the prompt's
  chip order (an out-of-order chip may or may not change the output; the submit guard
  `_image_body_problem` checks the reference *set*, `:1026-1040`).
- **Labs host.** The ref-cap e2e (`tests/e2e/test_image_i2i_ref_cap_e2e.py`, 10 refs) was
  not run (it bills image quota) and has no recorded run on a flow.google.com profile.
