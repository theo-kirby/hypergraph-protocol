---
node_id: 735d59c9-2dd6-57da-a981-03a285079c0a
slug: witty-chart-7035
title: 'U3: sync and hwm under test end to end; hwm --tips'
created_at: '2026-08-18T11:52:21+00:00'
parents:
- falling-snow-3475
summary: ''
flywheel:
  node_id: 8c11b7a0-33a3-54ce-bb97-f5a4e6f7456b
  slug: orange-tooth-8541
  revision: 0
  pushed_at: '2026-08-18T11:52:24+00:00'
  content_sha256: ee1980af045962783a7a18da80462fe600e31e808dfec878ae73fa182ac1e8b8
  parents_sha256: 8c004f9f0a269b97e6be6be98c941cb10cf6002228bc0a8c8c41b5167f4c6b96
  parents:
  - 5d2c9096-1fbd-5d20-85d2-578505175e58
---
## What

U3 of the 0.1.0 gate: `sync` — the one verb every skill tells an agent to run — and the `hwm` CLI get end-to-end tests, and `hwm --tips` lands as the reconcile skill's forward-looking frontier query.

## Why

The audit found `sync` had zero test coverage: the violation gate ("check failed → do not publish"), the no-mirror stand-down, and the hand-built push Namespace in `cmd_sync` were all held by prose. The Namespace is the sharpest risk — a new `push` flag that `sync` forgets to forward fails silently at the next release. Separately, the reconcile skill needed a mechanical answer to "what frontier do I write after folding everything"; pointing it at `hwm --suggest` was considered and rejected during design, because `suggest_frontier` is timestamp-cutoff semantics and would re-teach the wall-clock rule I5 forbids.

## Method

- `FakeTransport`, the fake-host root ids and `config_for` moved from `tests/test_mirror.py` to `tests/graph_fixtures.py` (mirror tests import them; 81 mirror tests unchanged).
- New `tests/test_sync.py`, all through `hg.main(["sync", …])`: (1) offline sync writes both exports and STATE.md, exit 0, with `hg._mirror` monkeypatched to raise — proving the mirror module is never touched; (2) an injected I6 violation exits 1 with "not publishing" and `make_transport` monkeypatched to raise — zero transport construction; (3) a configured mirror publishes all 5 fixture nodes through FakeTransport and stamps `flywheel:` frontmatter; (4) `--no-push` stops after check with `cmd_push` rigged to raise; (5) the parity pin — `build_parser()` extracted from `main()` (pure refactor), and the test asserts the Namespace `cmd_sync` hand-builds covers every `push` subparser option dest.
- `hwm` CLI tests: report mode prints the frontier and unreconciled count; an unresolvable mark exits 1; `--suggest` prints an adoptable `high_water_mark:` line.
- `hwm --tips` (~10 lines in `cmd_hwm`): prints the maximal (childless) nodes of the whole record graph — reachability semantics. Verified live: it prints the 7-tip frontier this repo's next reconcile should write.

## Result

9 new tests; suite 318 → 327 passed, 2 skipped. `sync` on the live graph: 0 violations, `push --verify` 0 drift. Reconcile pass #1 follows this node.

## Repo

- repo: git@github.com:theo-kirby/hypergraph-protocol.git
- branch: main
- commit: 141f3734db301cad7cf42f83dc204fb4497a4ba2

## State Impact

- target: wandering-sun-8831 — sync's violation gate, no-mirror stand-down, publish path and push-Namespace parity are test-held; hwm --tips gives reconcile a reachability-semantics frontier query
