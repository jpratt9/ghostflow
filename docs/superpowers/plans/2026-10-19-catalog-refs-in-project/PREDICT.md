# Predict: reference a catalogued image of the target project in place on flow.google.com (#995)

**Proposal.** `ImageRef.in_project` is today set only for images produced in the current
process (#913). Also set it when the local catalog records the `--ref <uuid>` image in the
**same Flow project** the generation targets, on the CLI (`_enrich_uuid_refs`) and the
MCP/worker path (`ref_meta.flow_project_id` → `worker.codec.build_image_request`). No
transport change: the migrated composer's existing in-place path (`reference_existing`)
does the work.

## Verdict: GO (with the evidence caveat below)
**Confidence:** 7/10.

## Persona signals

| Persona | Signal | Key point |
|---|---|---|
| Architect | GO | One predicate (`api.image.recorded_in_project`) shared by both surfaces; no new transport branch, no new selector. The routing decision stays at the request boundary, where #913 put it. |
| Security / account safety | GO | Nothing new reaches Flow: the same `@` picker search, the same `/asb/<token>` identity match against `img[data-media-id]`, the same `_image_body_problem` submit check. The catalog is only a routing hint; a stale or wrong catalog row still fails loud (`ReferenceNotFoundError`) instead of attaching the wrong image. Removes an upload, so it also avoids the account-level upload-terms dialog (exit 27) for a pure t2i → i2i flow. |
| Performance | GO | Saves an upload per reused reference. The grid may not list a just-generated tile until a reload; `reference_existing` already reloads within `EXISTING_REF_WAIT_S`. |
| CLI / MCP UX | GO | Same behaviour on both surfaces (CLI↔MCP mirror). Refusals unchanged for refs without a recorded caption (`history_prompts=redacted`) or from another project: exit 36 as today. Docs: REFERENCE_STRATEGIES, USAGE, KNOWN_ISSUES, CHANGELOG. |
| Devil's Advocate | CAUTION | The in-place path has only been exercised live for images of the **current** run (#913). An image from an earlier run should be identical to Flow (same project grid, same picker), but that is an inference until one live i2i proves it. |

## Required before merge
1. A maintainer-run (or contributor-run) live `image i2i --ref <uuid> --project P` on flow.google.com where `<uuid>` came from an earlier `image t2i --project P`: expect `migrated.existing_references_attached` and no upload. Images spend no credits. **Not run by the author** (see the PR's verification section).
