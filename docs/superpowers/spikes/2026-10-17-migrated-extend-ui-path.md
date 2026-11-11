# flow.google.com: `video extend` IS reachable through the UI, and the page mints its own token

**Date:** 2026-10-17 · **Issues:** #882 (fork PR, extend port), #639 · **Cost:** $0 — every
generation/extend rpc aborted at the route; one free scene created (see Side effects)
**Probe:** [`scripts/dev/spike_migrated_extend_ui_path.py`](../../../scripts/dev/spike_migrated_extend_ui_path.py)
**Captures:** `scripts/dev/_spike_out/extend_ui_path_20261017_22*.json` + `.png` (gitignored)
**Profile / target:** `ffroliva`, project `95763401…`, media `648d2a96…` (8 s, 16:9 clip)

## Question

PR #882 ports extend to flow.google.com by **minting** a reCAPTCHA token in gflow and
replaying batchexecute `fZytfe` with `page.request.post`. Develop refuses to mint on that
host (`client.py` `raise_if_migrated(page, at="mint_recaptcha_token")`), and every other
migrated port (composer, upscale, characters) drives the Angular UI and watches the wire.
Can extend be driven the same way?

## Method

`--step` actions walked the path one run at a time, inventorying custom-element tags,
`mat-icon` ligatures, roles and visible buttons (with their custom-element ancestors)
before and after each click, plus a screenshot. Aria-labels and text were recorded, never
used as anchors. A context-level `route` on `batchexecute` aborted `fZytfe`, `YhhmEf`,
`eb1hJf`, `MZZa6b`, `nprQif` always, and — once the walk began — any rpcid not seen during
the passive project load unless named with `--allow-rpc`. Seven runs; each unknown rpc was
read from its aborted body before being allowed on the next run.

## Pre-registered readings (script docstring, written before the first run)

- A1 path found → record it; not found after a full inventory → "unmeasured", never "unsupported".
- A2 `rqZuUc` before Extend is reachable → "reaching extend creates a scene".
- A3 `fZytfe` captured with a long string in `inner[1][10][0]` → "UI-driven port viable; the PAGE mints".
- A4 a `Zzl0ze` record with `[2] == media` → its `[0]` is the workflow id.

## Observations

### A1 — the structural click path (en-GB account; all anchors are tags / classes / ligatures)

| # | Action | Anchor | Result |
|---|---|---|---|
| 1 | click the clip tile | `flow-video-tile` | URL → `/project/<pid>/edit/<media_id>`; page is `flow-scene-builder` (with `flow-scene-timeline`, `flow-extend-menu`, `flow-edit-video-prompt-box`) |
| 2 | click the timeline `+` | `flow-scene-timeline button.add-clip-button` (ligature `add`) | one `.cdk-overlay-pane` with two `flow-menu-item` → `button[role=menuitem]`, ligatures `add` and `keyboard_double_arrow_right` |
| 3 | click Extend | `.cdk-overlay-pane [role='menuitem']:has(mat-icon:text-is('keyboard_double_arrow_right'))` | timeline gains a "prompt to extend" slot; prompt box shows `button.extend-mode-chip` (ligature `close`); `flow-generate-icon-button button` is **disabled** until text is typed |
| 4 | type prompt | `flow-edit-video-prompt-box .ProseMirror` | generate button enabled |
| 5 | submit | `flow-edit-video-prompt-box flow-generate-icon-button button` (ligature `arrow_forward`) | `rqZuUc` → `uwAyfb` → `fZytfe` (aborted); URL → `/project/<pid>/scene/<scene_id>` |

Steps 1–4 fire **no** new rpc (only `as29s` status reads). The add-clip button keeps the
`add-clip-button` class but its ligature becomes `keyboard_double_arrow_right` once extend
mode is on.

### A2 — the scene is created at SUBMIT, not to reach Extend

No `rqZuUc` while walking steps 1–4. On submit the page sends, in order:

1. `rqZuUc` — `["projects/<pid>", ["<MEDIA id>"], null, null, 2]` from source-path
   `/project/<pid>/edit/<media_id>`. Note slot 1 carries the **media** id, not a workflow id.
   Reply: a scene record `[scene_id, "Untitled Scene <timestamp>", …]` with one clip entry.
2. `uwAyfb` — `[scene_id, project_id]`, a scene read (reply lists the scene's clips and
   the project's generation records). It is **required**: with it aborted (run 6) the UI
   showed a "failed to create scene" snackbar and never sent `fZytfe`.
3. `fZytfe` — the extend submit, source-path `/project/<pid>/scene/<scene_id>`.

### A3 — the captured `fZytfe` (aborted, redacted)

```
[[[[null, "<source WORKFLOW id>", 169, 192],
   [null, null, [[["<prompt>"]]]],
   "veo_3_1_extension_lite", 2, null,
   ["<scene_id>", null, null, null, "<UUID-A>", "<UUID-B>"]]],
 [null, 22, null, null, null, "<project_id>", null, null, null, null, ["<redacted:2489>", 1]],
 ["<UUID-C>", 1, null, ["<scene_id>", 1]]]
```

- Slot one = `a469dbf6…`, the **workflow** id (== `Zzl0ze` `rec[0]` below), confirming #882's invariant.
- Frame window `[169, 192]` for an 8 s clip — matches #882's `duration*24-23 … duration*24`.
- Model key `veo_3_1_extension_lite` (UI chip "Extend (Veo 3.1 - Lite)"); aspect index `2` (16:9).
- `inner[1][10] = [<2489-char string>, 1]`: a reCAPTCHA token **the page minted itself** —
  `/recaptcha/enterprise/reload` and `/recaptcha/enterprise/clr` were requested only around the submit.
- **Differs from #882's doc:** `inner[2]` is `[uuid, 1, null, [scene_id, 1]]` here; #882
  documents `[uuid3, 2, null, [scene_id, 2]]`. Unmeasured which the server needs; the
  page's own value is `1` on this account today.

### A4 — workflow id from the passive project read

`Zzl0ze` (fired on every project load, no click) carries a record of length 8 with
`rec[0] = a469dbf6-…` (workflow id), `rec[1] = <project_id>`, `rec[2] = 648d2a96-…`
(media id). So media → workflow is a free, passive lookup; no extra request.

## Verdict

**UI-driven port viable** (pre-registered A3 reading met). On `ffroliva`, Extend is
reachable through four structural clicks from the clip tile, and Flow's own page composes
`fZytfe` — workflow-id slot, frame window, model key and a **page-minted** reCAPTCHA token
included — exactly the way the other migrated ports already work: drive the UI, observe
the wire. gflow does not need to mint, so `raise_if_migrated(..., "mint_recaptcha_token")`
can stay.

## Side effects left in Flow

- Scene `80df52ec-b2f6-4b3b-89e0-622cdafb41e5` ("Untitled Scene …", run 7), project `95763401…`.
- Probably scene `adbda9dd-b763-4aa8-a117-b679b0b9e53c` (run 6: `rqZuUc` went through, the
  follow-up read was aborted; the id is taken from that read's body — existence unverified).
- Six more empty "Untitled Scene" entries from the `e2e_auth` runs of
  `tests/e2e/test_video_extend_migrated_e2e.py` (each contract / aspect test lets the free
  `rqZuUc` through; ids not recorded). No `fZytfe` reached Flow in any run.
- No scene delete was attempted (gflow has no scene-delete surface); delete both from the
  Scenes tab by hand if wanted. Credits: none — no `fZytfe` reached Flow.

## Round 2 — editor URL, tile identity, record kind (#882 takeover, task 1)

Same probe, `--direct-editor` added; two runs (`extend_ui_path_20261017_230618.json`,
`…_230635.json`), readings B1–B4 pre-registered in the script docstring. Cost: $0 — no rpc
was aborted in either run because none beyond the passive load fired; no scene created.

- **B1 — a direct `goto` reaches the extend-capable editor.** `page.goto` of
  `/project/<pid>/edit/<media>` as the *first* navigation kept that URL and rendered
  `flow-scene-builder`, `flow-scene-timeline button.add-clip-button`, `flow-extend-menu` and
  `flow-edit-video-prompt-box`. The two clicks after it (add-clip, then the
  `keyboard_double_arrow_right` menu item) switched extend mode on: `button.extend-mode-chip`
  appeared and `flow-generate-icon-button button` (ligature `arrow_forward`) was disabled
  until a prompt is typed — the same state as round 1's grid walk. **The goto replaces the
  grid walk.**
- **B2 — a `flow-video-tile` carries no media id.** Its only descendant with a `src` is an
  `img.thumbnail` whose URL is an opaque `/asb/…` token; no attribute names the media.
  (`flow-image-tile img` does carry `data-media-id`.) So the grid walk could only pick a
  video tile by position — another reason to use the editor URL.
- **B3 — the passive `Zzl0ze` record tells a video from an image.** Records are
  `[workflow, project, media, …]` (len 8). A video record has a media-info list at `rec[7][0]`
  (signed URL at `[8]`, model key at `[12]`, e.g. `veo_3_1_i2v_s`) and `rec[7][1] = [null,
  null, [8]]` (8 = the clip's seconds). The image record has `rec[7][0] = null` and
  `rec[7][1] = [null, null, null, <url>, 0, null, "image/jpeg"]`, with `[1376, 768]` at
  `rec[7][2]`. Kind therefore = image when `rec[7][1][6]` is an `image/*` mime, video when
  `rec[7][0]` is a list. A trailing `2` at `rec[7][0][16]` *may* be the aspect index; only a
  landscape clip was sampled, so it is **not** used — the aspect is read from the page's own
  `fZytfe` body instead.
- **B4 — the editor URL fires `Zzl0ze` on its own.** The direct load's passive set included
  `Zzl0ze` (with the media's record, workflow `a469dbf6…`), so media → workflow + kind needs
  no project-page visit first.

Still not measured: whether `Zzl0ze` pages on a large project (a media missing from it would
then be misreported as "not in this project").

## Not measured

- Whether the server accepts the UI's request (it was aborted by design; #882's live run is
  the only evidence that `fZytfe` produces a video).
- A portrait clip (aspect idx 1), a 4 s / 10 s source (frame window), other locales, other
  accounts or tiers (`veo_3_1_extension_lite` may be tier-dependent).
- Whether extending from an existing scene (rather than the clip view) skips `rqZuUc`.
