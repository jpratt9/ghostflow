# Scenario: catalogued refs of the target project on flow.google.com (#995)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Catalog row for `U`: image, `flow_project_id=P`, caption recorded | `image i2i --ref U --project P` (CLI) | `ImageRef(U).in_project=True`; migrated host references it in place (no upload) |
| 2 | Same, via MCP `generate_image` task with `project_id=P` | worker builds the request | `ref_meta[U].flow_project_id == P` → `in_project=True` (CLI↔MCP mirror) |
| 3 | Catalog row records `flow_project_id=Q` | `--project P` | `in_project=False` → exit 36 as today |
| 4 | No `--project` (scratch project) | i2i | `in_project=False` (a new project cannot hold `U`) |
| 5 | Catalog row has no project | `--project P` | `in_project=False` |
| 6 | Catalog row is a video | `--project P` | ref untouched (existing guard) |
| 7 | Catalog row in `P` but no caption (`GFLOW_CLI_HISTORY_PROMPTS=redacted`) | i2i | `in_project=True`, but the migrated composer refuses "an image Flow returned without a caption" (exit 36, unchanged) |
| 8 | Catalog says `P`, but the tile is gone from Flow (deleted) | i2i | `await_existing_references` misses after its reload window → `ReferenceNotFoundError`, nothing generated (unchanged) |
| 9 | Unknown UUID / catalog unavailable | i2i | ref untouched → exit 36 on flow.google.com (unchanged) |
| 10 | labs.google account | i2i with a catalogued ref | no behaviour change: the labs path never reads `in_project` |
