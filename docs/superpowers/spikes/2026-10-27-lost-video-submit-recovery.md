# Spike: finding a clip after its `MZZa6b` submit reply is lost (#1112)

**Date:** 2026-10-27 · **Profile:** `ffroliva` (served flow.google.com) · **Project:** the
#723 character-matrix project (`c3d85290-…`)
· **Scripts:** [`scripts/dev/spike_migrated_queue_read.py`](../../../scripts/dev/spike_migrated_queue_read.py) ($0),
[`scripts/dev/spike_lost_submit_recovery.py`](../../../scripts/dev/spike_lost_submit_recovery.py) (paid)
· **Cost:** 24 Veo credits (two r2v clips), plus $0 reads

## Question

About 1 in 7 video submits on flow.google.com lose the `MZZa6b` reply body (3 of 21 in the
#723 matrix, CLI and MCP alike). Flow still makes and bills the clip; gflow raises a
non-retryable exit 9 (`migrated_composer.py`, `_outcome_unknown`) and the clip stays in the
project. Without the reply, gflow has no workflow or media id. Can it still identify the
clip, and from where?

## What was observed

**1. The project listing (`Zzl0ze`) holds every billed clip, with the request inside it.**
A $0 read of the matrix project listed 21 videos and 22 images: every billed clip,
including the 3 whose reply was lost. A video record carries `[0]` workflow id, `[1]` project
id, `[2]` media id, `[5][0]` creation time, `[5][8][0]` status, and at `[5][6][1]` the
submitted request: model key, reference media ids at `[1]` (`[[null, 4, "<id>"]]`) and
character entity ids at `[8]`.

**2. The uploaded reference id is an exact key.** Each run uploads its own copy of the
reference: 18 distinct reference ids across the 18 runs that had one. gflow learns that id
from the `maseQ` upload reply before it submits. The 3 runs with no reference had an
identical prompt and cast, so only "new since before the submit" separates them.

**3. Status polls name the clip after a lost reply, including a real one.** The paid probe
makes `Response.text` raise for the submit reply (gflow then fails exactly as in #1112) and
listens on the generating page.

- Run A (forced loss): 0.1 s after the lost reply, a `jwpduf` reply was readable and named
  the clip at status 2, carrying our uploaded reference id and the character id. The probe's
  copy of the real reply confirmed the ids.
- Run B: the forced loss coincided with a **real** one. The probe's own unpatched read failed
  too (`body_unreadable MZZa6b`), so a lost body is lost to every DevTools reader; another
  read API will not fix it. Two `jwpduf` replies, 5 s apart, were still readable and named
  the new clip by our reference id.

**4. Status polls also carry records that are not ours.** The same polls reported an older,
finished clip of the project (in the baseline) and the record of the uploaded reference image
(status null). Taking "the first status record" would pick the wrong one.

**5. Listing readback recovers the clip end to end.** For both runs, a later `Zzl0ze` read
listed the clip at status 3 as the only record new since the baseline, with our reference
and character ids; `recover_clip` downloaded it (2.1 MB and 2.8 MB) with no new generation.
In run A the workflow id matched the real reply.

**6. Two page-handling facts.** A `Zzl0ze` wait on gflow's first page after launch timed
out; a second tab opened after the app loaded read it every time. A second tab open during
the upload stole the focus the file chooser needs (`no file chooser within 8s`, $0, nothing
submitted), so a second tab may only open after submit.

## Reading

- Matching rule: **new since the pre-submit snapshot**, and **carrying our uploaded
  reference id** (or, without one, our character ids, prompt and model). More than one
  candidate is ambiguous and must not be guessed.
- Keeping the generating page listening identifies the clip; the listing is a working
  fallback.

## What was NOT measured

- **Whether status polls on the generating page continue to status 3 after the loss.** Both
  paid runs stopped watching early (a probe bug, fixed in the script: it now decides
  "submitted" from the outgoing request). The fix's own e2e measures this leg.
  **Since measured (2026-10-28, the fix's e2e):** yes. The adopted clip went from status 2
  to 3 on the generating page's polls and downloaded; the listing fallback was not used.
- How soon a new record appears in `Zzl0ze` after submit (it was there and done ~1 min later).
- t2v and i2v. Only r2v ran; t2v has no uploaded id, so it relies on "new since the
  baseline" alone.
- Whether any of the 3 client-minted UUIDs in the request body maps to the record. No capture
  shows Flow echoing one in a status reply.
