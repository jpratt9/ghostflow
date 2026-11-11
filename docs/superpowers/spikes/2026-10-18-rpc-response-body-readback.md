# Response-body loss after a migrated-host write

The zero-generation production-driver probe observed three distinct outcomes:
normal `wrb.fr` replies; HTTP 200 replies for which Playwright raised
`Response.text: Protocol error (Network.getResponseBody): No data found for
resource with given identifier`; and renaming to the saved title, which emitted
no rename RPC. Captures live under the gitignored `scripts/dev/_spike_out/`.

Independent project reloads showed that a rename and an upload whose response
body was unavailable had nevertheless persisted. The uploaded tile retained its
run-unique filename and a media UUID. Response-body loss therefore cannot be
classified as a rejected file, an unwritten operation, or a safe write retry.
The initial capture conflated the exception class `Error` with a response body;
separate body-error fields corrected that reading. No Google plaintext `Error`
response was established by this probe.

The fix reads project state in a separate tab, preserving the caller's composer
and image settings. Create uses the newly navigated project UUID, rename requires
the exact saved title, and upload requires exactly one tile whose filename equals
the generated unique filename and whose media ID is a UUID. No write is repeated.
Unproven outcomes raise `RpcResponseUnavailableError`; it is not automatically
retryable. A same-title rename returns without waiting for a nonexistent RPC.

Review constraints: no transport replay, no credential/log payload changes, no
new CLI/MCP options, no generation quota, and no selector based on translated
prose. CLI and MCP call the same modified transport. The readback deadline is
bounded, and the temporary tab is closed on all outcomes. No claim is made that
this fixes Chrome's underlying protocol fault.

Offline regressions cover body loss, unique/absent/ambiguous upload matches,
verified/unverified titles, creation on an already navigated project, and no-op
rename. The BDD e2e binds `migrated_rpc_readback.feature`: real Flow writes and
real independent readback, with only the response-body failure injected. The
live reproduction and injected-failure verification are different evidence.

Maintainer addendum (2026-10-22). Body loss was observed directly on `maseQ` uploads (2 of
45, spike `2026-10-20-migrated-upload-reply-body-eviction.md`) and on a rename; it was not
observed on a create, whose recovery is built on the same reasoning. The readback's real
ceiling is about two minutes (tab load 45 s, title anchor 15 s, tile polling 15 s, plus
reloads), not 15 s. It polls until the tile carries both the run's file name and a UUID
media id, because the name can render first. A project with dozens of media (a virtualised
grid) is unmeasured.
