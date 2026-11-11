# Plan: catalogued refs of the target project referenced in place (#995)

- [x] Red: CLI `_enrich_uuid_refs` project-scope tests (scenarios 1, 3–6).
- [x] Red: MCP `_resolve_payload_refs` records `flow_project_id` in `ref_meta` (scenario 2).
- [x] Red: worker `build_image_request` sets `in_project` from `ref_meta` + `project_id` (scenario 2–5).
- [x] Red: CLI passes the resolved project to the enrichment (`--project` → `project_id`).
- [x] Green: `api.image.recorded_in_project`; wire it into `cli_image._enrich_uuid_refs`, `mcp.tools._ref_meta_entry`, `worker.codec.build_image_request`.
- [x] Docs: REFERENCE_STRATEGIES (flow.google.com section), USAGE (i2i on the migrated host), KNOWN_ISSUES (#639 entry), CHANGELOG.
- [x] Gates: ruff check + format check, pyright, pytest with coverage, CLI↔MCP parity tests, repo hygiene / doc links / website docs checks.
- [x] Live: one `image i2i --ref <uuid-from-earlier-t2i> --project P` on a flow.google.com account (no credits). Not run by the author. Run in the takeover (#1001): see `docs/superpowers/spikes/2026-10-19-earlier-run-ref-in-place.md` and `tests/e2e/test_earlier_run_ref_in_place_bdd.py`.
