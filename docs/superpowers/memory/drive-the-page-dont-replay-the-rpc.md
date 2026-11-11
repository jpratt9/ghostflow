---
name: drive-the-page-dont-replay-the-rpc
description: Port a BILLED flow.google.com action by driving Flow's own UI (the page mints its own reCAPTCHA and builds the payload), guarded by a page.route that aborts a wrong target before Flow bills — not by replaying the rpc with a gflow-minted token
---

**Lesson (#882 takeover, `gflow video extend` on flow.google.com, 2026-10-17).**
The first port replayed `fZytfe` from gflow: it minted the reCAPTCHA token itself and
built the request body. That needed four guesses nobody had measured — the mint
**action** name, a relaxed mint guard, payload fields copied from one capture, and a
request that Flow could tell apart from its own page's. Design B instead drives the
page: `goto /project/<pid>/edit/<media>`, add-clip → Extend → type → submit. The page
mints its own token with the right action and builds its own payload; gflow only
clicks and observes. That is how every other migrated port works
([[migrated-host-driver-wire-lessons]]).

**Pair it with a route guard.** Driving the page gives up control of the payload, so
inspect it instead: a `page.route` on `batchexecute` reads the page's OWN billed
request (`rqZuUc` scene create, `fZytfe` extend) and `route.abort()`s it before Flow
sees it when it targets the wrong clip/workflow. It is the paid-run counterpart of
[[credit-free-route-abort-verification]] — same abort, used as a guard instead of a
probe. Two traps it must cover (#882 council):

- **Batched requests.** `rpcids=uwAyfb,fZytfe` — reading only the first id lets a
  wrong `fZytfe` ride through. Judge every id in `rpcids=` AND every `f.req` frame.
- **Double billing.** Abort any second `fZytfe` after the first one was released.

**How to apply:** for a new billed migrated surface, try the UI path first; replay an
rpc only when no UI path exists, and then measure the mint action and every payload
field before relying on them. Code: `src/gflow_cli/api/transports/migrated_extend.py`.
