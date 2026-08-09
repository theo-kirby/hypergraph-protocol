---
node_id: 612174d1-9696-58a5-978b-9010077536f9
slug: solemn-dawn-6752
title: 'Correction: the Flywheel mirror was never gone — the key was the wrong account; mirror now synced and verified'
created_at: '2026-08-09T10:17:00+00:00'
parents:
- sweet-aspen-3667
summary: ''
flywheel:
  node_id: 6849969f-921d-536e-ab9b-c41cbdd0e061
  slug: raspy-river-0565
  revision: 0
  pushed_at: '2026-08-09T10:17:45+00:00'
  content_sha256: c02f98c95e5549ace3e36679a649dc083cdfe1e25e0c7f1a9ade5b58946761ba
---
## What

**Correction to `sweet-aspen-3667`.** That node concluded the Flywheel mirror was
gone — "0 of the 458 visible nodes belong to this project", both roots
`not_found`, all 44 claimed mirror ids returning 404 — and recorded it as needing
the Operator to find a lost account.

The mirror was never gone. Every one of those probes went through
`FLYWHEEL_API_KEY` from `.env`, which belongs to account
`80eed260-ad28-4a35-9d43-cd8d92730bab`. The mirror lives on
`be9833b0-502f-477a-ad2d-07dd5c871e10` — the account the `flywheel` **CLI** is
authenticated as. The Operator's instruction was direct: *don't use the key at
all, use the CLI.*

Through the CLI, on the first attempt: both roots resolve `unique`, all 44 claimed
mirror ids are reachable, and the state root was sitting at revision 16 exactly as
the local plan expected.

The mirror is now current. 18 ops applied (10 creates, 8 updates), the slug
legend regenerated (rev 6 → 7), and a fresh 55-node export verifies against the
local files at **0 drift findings**.

## Why

Follows `sweet-aspen-3667` and corrects it. Record nodes are immutable, so this is
a child node rather than an edit (SPEC).

The error is worth keeping rather than quietly overwriting, because the reasoning
that produced it was *locally* sound and still wrong. Four independent probes
agreed — `get_node` 404, `resolve_node_slug` not_found, 0/44 reachable, and 0
project nodes among all 2,561 visible without an owner filter. Four confirmations
of the same false premise, because every one of them asked the same wrongly-
authenticated question. Corroboration between checks that share an assumption is
not corroboration.

## Method

Diagnosis:

    flywheel auth:status
    # user_id be9833b0-502f-477a-ad2d-07dd5c871e10   <- CLI (holds the mirror)
    # vs 80eed260-ad28-4a35-9d43-cd8d92730bab        <- .env FLYWHEEL_API_KEY

    flywheel nodes:resolve-slug --slug_name cool-king-8586      # status: unique, rev 16
    flywheel nodes:resolve-slug --slug_name autumn-tooth-6046   # status: unique

Then all 44 claimed mirror ids probed via `flywheel nodes:get` — 44 reachable,
0 absent.

Push executed through the CLI (`nodes:commit-new`, then per update
`nodes:get` → `nodes:stage:lease:acquire` → `nodes:commit` →
`nodes:stage:lease:release`), with `FLYWHEEL_API_KEY` stripped from the
subprocess environment so it could not shadow the CLI's own session. Results were
recorded incrementally: `push --plan` is a diff, so anything created but
unrecorded would be created a second time on retry.

Two CLI-vs-MCP shape differences cost a retry each, both caught by the executor
failing loudly rather than writing wrong data: the CLI reports `revision` where
the MCP calls it `committed_revision`, and a newly created node starts at
**revision 0**, not 1. The second produced 10 revision-skew drift findings on the
first verify; the recorded revisions were corrected from the mirror's own export
rather than from an assumption, and re-verify came back clean.

## Result

All three surfaces are current, for the first time in this thrust.

- **Mirror synced**: 18 ops, 0 failures. `push --plan` now reports 0 creates,
  0 updates.
- **Legend regenerated**: rev 6 → 7.
- **Verified**: 55-node export from the project's own mirror roots — never the
  archive roots — against local files: **0 drift findings**. No content drift was
  ever present; the only findings were the revision skew described above, now
  fixed.
- `sweet-aspen-3667`'s other claim stands and is unaffected: preflight was
  checking a Flywheel key could be *read* with, not *written* with, and
  `flywheel_can_write` fixes that. That defect was real and its fix is correct.

Standing risk, unresolved: `.env`'s `FLYWHEEL_API_KEY` still points at the wrong
account. Anything that reads it instead of using the CLI — including
`research/boxlab`'s preflight and the arm-B boxes, which are wired to that
variable — is talking to an account with no relation to this project. The
benchmark is parked, so nothing is broken today, but a relaunch would provision
arm B against the wrong account unless the variable is corrected first.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 04cb5f60cdb793ea747b540c543ea740f02d2de8

## State Impact

- target: empty-forest-6305 — CORRECTION to sweet-aspen-3667: the Flywheel mirror was never gone. Every probe that said so went through .env's FLYWHEEL_API_KEY (account 80eed260…), while the mirror lives on the account the `flywheel` CLI is authenticated as (be9833b0…). Via the CLI both roots resolve `unique`, all 44 claimed mirror ids are reachable, and the state root was at revision 16 exactly as the local plan expected. The mirror is now CURRENT: 18 ops applied (10 creates, 8 updates), legend regenerated rev 6→7, and a fresh 55-node export of the project's own mirror roots verifies against local files at 0 drift findings. `push --plan` reports 0/0.
- target: fair-field-3265 — negative knowledge with a sharp edge, because the reasoning was locally sound and still wrong: four independent probes agreed the mirror was gone (get_node 404, resolve_slug not_found, 0 of 44 ids reachable, 0 project nodes among all 2,561 visible without an owner filter) and all four were wrong, because each asked the same wrongly-authenticated question. Corroboration between checks that share an assumption is not corroboration. When several checks agree on a surprising absence, vary the credential/identity before believing them. Also: two CLI-vs-MCP shape differences (the CLI reports `revision` where the MCP says `committed_revision`; a newly created node starts at revision 0, not 1) were caught only because the executor failed loudly and the verify step compared against the mirror's own export rather than against what had been assumed.
- target: protocol-benchmark-4417 — STANDING RISK for the relaunch: .env's FLYWHEEL_API_KEY points at account 80eed260…, which has no relation to this project; the project's Flywheel identity is the CLI's be9833b0…. research/boxlab reads that variable for preflight's account checks AND writes it onto every arm-B box, so a relaunch as configured today would provision arm B against the wrong account entirely — and the 458-node baseline captured earlier is that wrong account's. The thrust is parked so nothing is broken now, but the variable must be corrected before any launch, and the baseline recaptured.
